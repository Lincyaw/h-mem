from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from hmem.models import Conversation, Message

if TYPE_CHECKING:
    from hmem.core.conversation_processor import ConversationProcessor, BatchResult

logger = structlog.get_logger()


@dataclass
class ImportResult:
    """Result of importing conversations."""

    total_files: int = 0
    total_conversations: int = 0
    total_messages: int = 0
    errors: list[str] = field(default_factory=list)
    batch_result: BatchResult | None = None


class ClaudeCodeImporter:
    """Import conversations from Claude Code JSONL log files.

    Claude Code stores conversation logs as JSONL files in:
        ~/.claude/projects/<project-hash>/

    Each line is a JSON object with fields:
        - type: "human" | "assistant" | "summary" | etc.
        - message: {role: str, content: str|list}
        - sessionId: str
        - timestamp: str (ISO format)

    This importer:
    1. Parses JSONL files
    2. Groups messages by sessionId
    3. Converts to Conversation objects
    4. Passes to ConversationProcessor for indexing
    """

    def __init__(self, processor: ConversationProcessor) -> None:
        """Initialize the importer.

        Args:
            processor: ConversationProcessor instance for indexing conversations
        """
        self.processor = processor
        self._log = logger.bind(component="importer")

    def _extract_text_content(self, content: str | list[dict[str, Any]]) -> str:
        """Extract text content from message content field.

        Args:
            content: Either a plain string or a list of content blocks

        Returns:
            Extracted text content
        """
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        text_parts.append(text)
            return "\n".join(text_parts)

        return ""

    def _parse_timestamp(self, timestamp_str: str | None) -> datetime:
        """Parse ISO format timestamp string.

        Args:
            timestamp_str: ISO format timestamp string

        Returns:
            Parsed datetime object, or current time if parsing fails
        """
        if not timestamp_str:
            return datetime.now()

        try:
            # Handle ISO format with milliseconds and Z timezone
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            self._log.warning(
                "failed_to_parse_timestamp", timestamp=timestamp_str, error=str(e)
            )
            return datetime.now()

    def parse_jsonl(self, path: Path) -> list[Conversation]:
        """Parse a JSONL file and extract conversations.

        Args:
            path: Path to JSONL file

        Returns:
            List of Conversation objects
        """
        self._log.info("parsing_jsonl", path=str(path))

        # Group messages by session_id
        sessions: dict[str, list[dict[str, Any]]] = {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        self._log.warning(
                            "malformed_json",
                            path=str(path),
                            line=line_num,
                            error=str(e),
                        )
                        continue

                    # Filter for relevant message types
                    msg_type = data.get("type", "")
                    if msg_type not in ("human", "assistant"):
                        continue

                    # Extract session ID
                    session_id = data.get("sessionId")
                    if not session_id:
                        self._log.warning(
                            "missing_session_id", path=str(path), line=line_num
                        )
                        continue

                    # Extract message content
                    message_obj = data.get("message", {})
                    content = message_obj.get("content", "")

                    # Skip empty messages
                    text_content = self._extract_text_content(content)
                    if not text_content:
                        continue

                    # Map role: "human" -> "user", "assistant" -> "assistant"
                    role = "user" if msg_type == "human" else "assistant"

                    # Extract timestamp
                    timestamp_str = data.get("timestamp")
                    timestamp = self._parse_timestamp(timestamp_str)

                    # Store parsed message
                    if session_id not in sessions:
                        sessions[session_id] = []

                    sessions[session_id].append(
                        {
                            "role": role,
                            "content": text_content,
                            "timestamp": timestamp,
                        }
                    )

        except OSError as e:
            self._log.error("failed_to_read_file", path=str(path), error=str(e))
            raise

        # Convert to Conversation objects
        conversations = []
        for session_id, messages_data in sessions.items():
            # Sort messages by timestamp
            messages_data.sort(key=lambda m: m["timestamp"])

            # Create Message objects
            messages = [
                Message(
                    role=msg["role"],
                    content=msg["content"],
                    timestamp=msg["timestamp"],
                )
                for msg in messages_data
            ]

            # Skip conversations with no valid messages
            if not messages:
                continue

            # Create Conversation object
            conversation = Conversation(
                id=f"conv_{session_id[:12]}",
                session_id=session_id,
                messages=messages,
                timestamp=messages[0].timestamp,  # Use earliest message timestamp
            )
            conversations.append(conversation)

        # Sort conversations by timestamp
        conversations.sort(key=lambda c: c.timestamp)

        self._log.info(
            "parsed_jsonl",
            path=str(path),
            conversations=len(conversations),
            total_messages=sum(len(c.messages) for c in conversations),
        )

        return conversations

    def import_project(
        self, project_dir: Path, on_progress: Callable[[int, int], None] | None = None
    ) -> ImportResult:
        """Import all conversations from a project directory.

        Args:
            project_dir: Path to project directory containing JSONL files
            on_progress: Optional callback (current, total) for progress tracking

        Returns:
            ImportResult with statistics and batch processing result
        """
        self._log.info("importing_project", path=str(project_dir))

        result = ImportResult()

        # Find all JSONL files
        jsonl_files = list(project_dir.glob("*.jsonl"))
        result.total_files = len(jsonl_files)

        if not jsonl_files:
            self._log.warning("no_jsonl_files_found", path=str(project_dir))
            return result

        # Parse all files
        all_conversations: dict[str, Conversation] = {}

        for idx, jsonl_path in enumerate(jsonl_files, start=1):
            if on_progress:
                on_progress(idx, result.total_files)

            try:
                conversations = self.parse_jsonl(jsonl_path)

                # Deduplicate by session_id (keep latest version)
                for conv in conversations:
                    session_id = conv.session_id
                    if session_id in all_conversations:
                        # Keep the one with more messages or later timestamp
                        existing = all_conversations[session_id]
                        if len(conv.messages) > len(existing.messages):
                            all_conversations[session_id] = conv
                        elif (
                            len(conv.messages) == len(existing.messages)
                            and conv.timestamp > existing.timestamp
                        ):
                            all_conversations[session_id] = conv
                    else:
                        all_conversations[session_id] = conv

            except Exception as e:
                error_msg = f"Failed to parse {jsonl_path}: {e}"
                self._log.error("parse_error", path=str(jsonl_path), error=str(e))
                result.errors.append(error_msg)

        # Convert to list and sort by timestamp
        conversations_list = sorted(
            all_conversations.values(), key=lambda c: c.timestamp
        )

        result.total_conversations = len(conversations_list)
        result.total_messages = sum(len(c.messages) for c in conversations_list)

        # Process batch if we have conversations
        if conversations_list:
            try:
                batch_result = self.processor.process_batch(conversations_list)
                result.batch_result = batch_result

                self._log.info(
                    "project_imported",
                    path=str(project_dir),
                    conversations=result.total_conversations,
                    messages=result.total_messages,
                    events=batch_result.total_events,
                    facts=batch_result.total_facts,
                    principles=batch_result.principles_induced,
                )
            except Exception as e:
                error_msg = f"Failed to process batch: {e}"
                self._log.error("batch_processing_error", error=str(e))
                result.errors.append(error_msg)

        return result

    def import_all(
        self,
        projects_dir: Path,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> ImportResult:
        """Import conversations from all projects in the projects directory.

        Args:
            projects_dir: Path to projects directory (e.g., ~/.claude/projects)
            on_progress: Optional callback (project_name, current, total)

        Returns:
            Aggregated ImportResult from all projects
        """
        self._log.info("importing_all_projects", path=str(projects_dir))

        aggregated_result = ImportResult()

        # Find all project directories
        project_dirs = [d for d in projects_dir.iterdir() if d.is_dir()]
        total_projects = len(project_dirs)

        if not project_dirs:
            self._log.warning("no_project_directories_found", path=str(projects_dir))
            return aggregated_result

        for idx, project_dir in enumerate(project_dirs, start=1):
            project_name = project_dir.name

            if on_progress:
                on_progress(project_name, idx, total_projects)

            try:
                result = self.import_project(project_dir)

                # Aggregate results
                aggregated_result.total_files += result.total_files
                aggregated_result.total_conversations += result.total_conversations
                aggregated_result.total_messages += result.total_messages
                aggregated_result.errors.extend(result.errors)

                # Note: batch_result is not aggregated - would need custom logic

            except Exception as e:
                error_msg = f"Failed to import project {project_name}: {e}"
                self._log.error(
                    "project_import_error", project=project_name, error=str(e)
                )
                aggregated_result.errors.append(error_msg)

        self._log.info(
            "all_projects_imported",
            projects=total_projects,
            total_conversations=aggregated_result.total_conversations,
            total_messages=aggregated_result.total_messages,
            errors=len(aggregated_result.errors),
        )

        return aggregated_result
