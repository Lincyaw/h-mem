"""LLM client for intelligent text processing tasks.

Provides simple methods for different LLM operations:
- summarize: Summarize conversation messages
- filter_relevant_memories: Filter memories by relevance to query
- extract_feedback_signals: Extract feedback from conversation

Note: Structured knowledge extraction is now handled by the
skill-aware ReAct agent in hmem.agents.react.extraction_agent

LLM Logging (inspired by LangSmith trace format):
- Set HMEM_LLM_LOG=1 to enable LLM call logging to .hmem/llm.jsonl
- Each call is a "run" with trace_id linking related calls
- Format: {"trace_id", "run_id", "parent_run_id", "type", "name", "inputs", "outputs", "start_time", "end_time"}
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)


# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger()

# Enable LLM call logging to JSONL file when HMEM_LLM_LOG=1
LLM_LOG_ENABLED = os.environ.get("HMEM_LLM_LOG", "0") == "1"
LLM_LOG_DIR = Path(os.environ.get("HMEM_LLM_LOG_DIR", ".hmem"))

# Current trace context (set by start_trace, used by nested calls)
_current_trace_id: str | None = None
_current_parent_run_id: str | None = None


def start_trace(trace_id: str | None = None) -> str:
    """Start a new trace for grouping related LLM calls.

    Args:
        trace_id: Optional trace ID, generates new one if not provided

    Returns:
        The trace ID being used
    """
    global _current_trace_id, _current_parent_run_id
    _current_trace_id = trace_id or str(uuid4())[:8]
    _current_parent_run_id = None
    return _current_trace_id


def end_trace() -> None:
    """End the current trace."""
    global _current_trace_id, _current_parent_run_id
    _current_trace_id = None
    _current_parent_run_id = None


def _write_llm_log(entry: dict[str, Any]) -> None:
    """Write a single LLM call entry to the JSONL log file."""
    if not LLM_LOG_ENABLED:
        return

    try:
        LLM_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LLM_LOG_DIR / "llm.jsonl"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("llm_log_write_failed", error=str(e))


class LLMClient:
    """Simple LLM client for text processing operations.

    This is a lightweight wrapper around LangChain chat models,
    providing domain-specific methods for memory system tasks.

    Example:
        >>> client = LLMClient()
        >>> knowledge = client.extract_structured_knowledge("User prefers dark mode")
        >>> principle = client.reflect(episodes)
    """

    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.1,
    ) -> None:
        """Initialize LLM client.

        Args:
            model: Model identifier in format 'provider:model_name'
                   e.g., 'openai:gpt-4o-mini', 'openai:ep-xxx-endpoint-id'
                   If None, uses default from LLMConfig.
            temperature: Sampling temperature
        """
        from hmem.config import LLMConfig

        # Use default from config if not provided
        if model is None:
            model = LLMConfig().model

        # Configure OpenAI-compatible base URL from environment
        api_base = os.getenv("OPENAI_API_BASE")
        if api_base:
            os.environ["OPENAI_BASE_URL"] = api_base

        self.llm: BaseChatModel = init_chat_model(model, temperature=temperature)
        self.logger = logger.bind(component="llm_client")

    def _extract_text(self, content: Any) -> str:
        """Extract text from LLM response content.

        Handles both string and list (multimodal) response formats.

        Args:
            content: Response content from LLM

        Returns:
            Extracted text as string
        """
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
            return "".join(text_parts).strip()
        return str(content).strip()

    def call(
        self,
        messages: list[dict[str, str]],
        *,
        operation: str = "llm_call",
    ) -> str:
        """Invoke LLM with messages and log input/output.

        This is the central entry point for all LLM calls. It handles:
        - Converting dict messages to LangChain format
        - Logging to JSONL file in trace format (if HMEM_LLM_LOG=1)
        - Extracting text from response

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            operation: Name of the operation for logging context

        Returns:
            Extracted text response from LLM
        """
        global _current_parent_run_id

        run_id = str(uuid4())[:8]
        start_time = datetime.now(timezone.utc)

        # Convert to LangChain format (content as list of dicts per CLAUDE.md)
        lc_messages: list[BaseMessage] = []
        for msg in messages:
            content = [{"type": "text", "text": msg["content"]}]
            role = msg["role"]
            if role == "system":
                lc_messages.append(SystemMessage(content=content))  # type: ignore
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))  # type: ignore
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))  # type: ignore

        # Invoke LLM
        response = self.llm.invoke(lc_messages)
        result = self._extract_text(response.content)

        end_time = datetime.now(timezone.utc)

        # Write trace-style log entry
        _write_llm_log(
            {
                "trace_id": _current_trace_id or "standalone",
                "run_id": run_id,
                "parent_run_id": _current_parent_run_id,
                "type": "llm",
                "name": operation,
                "inputs": {"messages": messages},
                "outputs": {"content": result},
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "latency_ms": int((end_time - start_time).total_seconds() * 1000),
            }
        )

        # Update parent for next call in this trace
        _current_parent_run_id = run_id

        return result

    def summarize(self, messages: list[dict[str, str]]) -> str:
        """Summarize conversation messages.

        Args:
            messages: List of conversation messages

        Returns:
            Summary text
        """
        try:
            conversation_text = "\n".join(
                [f"{msg['role']}: {msg['content']}" for msg in messages]
            )

            llm_messages = [
                {
                    "role": "system",
                    "content": "Summarize the following conversation concisely, preserving key information.",
                },
                {"role": "user", "content": conversation_text},
            ]
            return self.call(llm_messages, operation="summarize")
        except Exception as e:
            raise MemoryError(f"LLM summarization failed: {e}") from e

    def filter_relevant_memories(
        self, query: str, memories: list[dict[str, str]], min_relevance: float = 0.5
    ) -> list[dict[str, Any]]:
        """Filter memories by relevance to query.

        Args:
            query: Query text
            memories: List of memory dicts with 'id' and 'content' keys
            min_relevance: Minimum relevance score (0-1)

        Returns:
            List of relevant memory dicts with 'id', 'content', 'relevance' keys
        """
        if not memories:
            return []

        try:
            memories_text = "\n".join(
                [f"[{m.get('id', 'unknown')}] {m.get('content', '')}" for m in memories]
            )

            llm_messages = [
                {
                    "role": "system",
                    "content": f"""Rate the relevance of each memory to the query on a scale of 0-1.
Return ONLY a JSON array of objects with 'id' and 'relevance' keys.
Only include memories with relevance >= {min_relevance}.
Example: [{{"id": "mem_123", "relevance": 0.8}}]""",
                },
                {
                    "role": "user",
                    "content": f"Query: {query}\n\nMemories:\n{memories_text}",
                },
            ]
            response_text = self.call(
                llm_messages, operation="filter_relevant_memories"
            )

            # Parse JSON response
            import json

            # Try to extract JSON from response
            json_start = response_text.find("[")
            json_end = response_text.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                relevant_ids = json.loads(json_str)
            else:
                return []

            # Build result with original memory content
            memory_map = {m.get("id", ""): m for m in memories}
            result = []
            for item in relevant_ids:
                mem_id = item.get("id", "")
                if mem_id in memory_map:
                    result.append(
                        {
                            **memory_map[mem_id],
                            "relevance": item.get("relevance", 0.5),
                        }
                    )
            return result

        except Exception as e:
            self.logger.warning("filter_relevant_memories_failed", error=str(e))
            # Return all memories if filtering fails
            return [
                {
                    "id": m.get("id", ""),
                    "content": m.get("content", ""),
                    "relevance": 0.5,
                }
                for m in memories
            ]

    def extract_feedback_signals(
        self, conversation_text: str, memory_ids: list[str]
    ) -> list[dict[str, str]]:
        """Extract feedback signals from conversation about recalled memories.

        Analyzes conversation to determine if recalled memories were helpful.

        Args:
            conversation_text: Full conversation text
            memory_ids: IDs of memories that were recalled

        Returns:
            List of feedback dicts with 'memory_id' and 'outcome' keys
        """
        if not memory_ids:
            return []

        try:
            llm_messages = [
                {
                    "role": "system",
                    "content": """Analyze whether the recalled memories (marked with XML tags) were helpful.
Return a JSON array of objects with 'memory_id' and 'outcome' keys.
outcome must be 'success' (memory was helpful) or 'failure' (memory was not helpful or misleading).
Only include memories you can clearly assess. Example: [{"memory_id": "mem_123", "outcome": "success"}]""",
                },
                {
                    "role": "user",
                    "content": f"Memory IDs: {memory_ids}\n\nConversation:\n{conversation_text}",
                },
            ]
            response_text = self.call(
                llm_messages, operation="extract_feedback_signals"
            )

            # Parse JSON response
            import json

            json_start = response_text.find("[")
            json_end = response_text.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            return []

        except Exception as e:
            self.logger.warning("extract_feedback_signals_failed", error=str(e))
            return []
