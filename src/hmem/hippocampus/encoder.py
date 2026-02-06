"""Memory Encoder - Converts unstructured dialogue to structured data with provenance.

Key design:
- Uses skill-aware ReAct agent for extraction (not hardcoded prompts)
- Single extraction per conversation (not per message) to avoid duplication
- Sliding window + folding for long conversations to avoid truncation
- No Event nodes - Fact/Process link directly to Conversation for provenance
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import structlog

from hmem.models import Conversation, Entity, Message, Process

if TYPE_CHECKING:
    from hmem.agents.react.extraction_agent import ExtractionAgent
    from hmem.config import AgentConfig
    from hmem.skills.manager import SkillManager
    from hmem.storage.neo4j_unified import Neo4jUnifiedStore

logger = structlog.get_logger()

# Approximate token count (rough: 1 token ≈ 4 chars for English, ~2 chars for Chinese)
DEFAULT_MAX_TOKENS = 32000  # Max tokens per extraction window
CHARS_PER_TOKEN = 4  # Conservative estimate for mixed content


class SummarizerProtocol(Protocol):
    """Protocol for conversation summarization."""

    def summarize(self, messages: list[dict[str, str]]) -> str: ...


class MemoryEncoder:
    """Extracts structured information from raw conversations with provenance tracking.

    Key design decisions:
    1. SINGLE extraction per conversation (not per message) - avoids duplication
    2. Uses skill-aware ReAct agent for extraction
    3. Agent can load knowledge-extraction skill for guidance
    4. Session-scoped data filtered out by agent
    5. Non-generalizable processes filtered out by agent
    6. SLIDING WINDOW + FOLDING for long conversations
    7. No Event nodes - provenance links directly to Conversation

    Extracts:
    - Entities (with aliases for resolution)
    - Attributes (entity-slot-value with cardinality and scope)
    - Processes (trigger-action-outcome, generalizable only)

    All derived memories maintain links to their source Conversation
    to support the hierarchical semantic graph.

    Example:
        >>> encoder = MemoryEncoder(store=store, skill_manager=manager)
        >>> conversation = Conversation(...)
        >>> result = encoder.encode_conversation(conversation)
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore | None = None,
        skill_manager: SkillManager | None = None,
        extraction_agent: ExtractionAgent | None = None,
        summarizer: SummarizerProtocol | None = None,
        agent_config: AgentConfig | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        """Initialize memory encoder.

        Args:
            store: Neo4j unified store (required if extraction_agent not provided)
            skill_manager: Skill manager (required if extraction_agent not provided)
            extraction_agent: Pre-configured extraction agent (optional)
            summarizer: Summarizer for folding (uses LLMClient if not provided)
            agent_config: Agent configuration
            max_tokens: Maximum tokens per extraction window
        """
        self._store = store
        self._skill_manager = skill_manager
        self._extraction_agent = extraction_agent
        self._summarizer = summarizer
        self._agent_config = agent_config
        self.max_tokens = max_tokens
        self.max_chars = max_tokens * CHARS_PER_TOKEN

    @property
    def extraction_agent(self) -> ExtractionAgent:
        """Lazy initialization of extraction agent."""
        if self._extraction_agent is None:
            if self._store is None or self._skill_manager is None:
                raise ValueError(
                    "Either extraction_agent or both store and skill_manager required"
                )
            from hmem.agents.react.extraction_agent import create_extraction_agent

            self._extraction_agent = create_extraction_agent(
                store=self._store,
                skill_manager=self._skill_manager,
                config=self._agent_config,
            )
        return self._extraction_agent

    @property
    def summarizer(self) -> SummarizerProtocol:
        """Lazy initialization of summarizer."""
        if self._summarizer is None:
            from hmem.agents.llm import LLMClient

            self._summarizer = LLMClient()
        return self._summarizer

    def encode_conversation(self, conversation: Conversation) -> dict[str, Any]:
        """Encode conversation into entity-centric structure.

        For short conversations: extracts in ONE agent call.
        For long conversations: uses sliding window + folding to process
        in chunks, preserving context via summarization.

        The extraction agent will:
        1. Search for and load the knowledge-extraction skill
        2. Follow the skill's guidance for extraction
        3. Check for duplicate entities and facts
        4. Return structured knowledge with proper scope classification

        Args:
            conversation: Conversation to encode

        Returns:
            Dict with entities, attributes, processes, conversation_id
        """
        all_entities: list[Entity] = []
        all_attributes: list[dict] = []  # {attribute: Attribute, entity_name: str}
        all_processes: list[Process] = []

        # Ensure conversation has an ID
        conv_id = conversation.id or ""

        # Extract entities/attributes/processes
        # Use sliding window if conversation is too long
        full_text = self._build_conversation_text(conversation.messages)
        estimated_tokens = len(full_text) // CHARS_PER_TOKEN

        if estimated_tokens <= self.max_tokens:
            logger.debug(
                "single_extraction",
                conv_id=conv_id,
                estimated_tokens=estimated_tokens,
            )
            extracted = self._extract_single(full_text, conv_id)
            all_entities = extracted["entities"]
            all_attributes = extracted["attributes"]
            all_processes = extracted["processes"]
        else:
            logger.info(
                "sliding_window_extraction",
                conv_id=conv_id,
                estimated_tokens=estimated_tokens,
                max_tokens=self.max_tokens,
            )
            extracted = self._extract_with_sliding_window(
                conversation.messages, conv_id
            )
            all_entities = extracted["entities"]
            all_attributes = extracted["attributes"]
            all_processes = extracted["processes"]

        logger.info(
            "conversation_encoded",
            session_id=conversation.session_id,
            conversation_id=conv_id,
            entities=len(all_entities),
            attributes=len(all_attributes),
            processes=len(all_processes),
        )

        return {
            "entities": all_entities,
            "attributes": all_attributes,
            "processes": all_processes,
            "conversation_id": conv_id,
        }

    def _extract_single(self, content: str, conv_id: str) -> dict[str, Any]:
        """Extract from a single chunk of content using the agent.

        Args:
            content: Conversation text
            conv_id: Conversation ID for provenance

        Returns:
            Dict with entities, attributes, processes lists
        """
        try:
            # Use the skill-aware extraction agent
            result = self.extraction_agent.extract(
                conversation_text=content,
                conv_id=conv_id,
            )

            return {
                "entities": result.entities,
                "attributes": result.attributes,
                "processes": result.processes,
            }

        except Exception as e:
            logger.warning(
                "extraction_agent_failed",
                conv_id=conv_id,
                error=str(e),
                exc_info=True,
            )
            return {
                "entities": [],
                "attributes": [],
                "processes": [],
            }

    def _extract_with_sliding_window(
        self, messages: list[Message], conv_id: str
    ) -> dict[str, Any]:
        """Extract from long conversation using sliding window + folding.

        Strategy:
        1. Split messages into windows that fit within token limit
        2. For first window: extract directly
        3. For subsequent windows: summarize previous content + extract current
        4. Merge and deduplicate results across all windows

        Args:
            messages: Full list of conversation messages
            conv_id: Conversation ID for provenance

        Returns:
            Dict with merged entities, attributes, processes
        """
        all_entities: list[Entity] = []
        all_attributes: list[dict] = []
        all_processes: list[Process] = []

        windows = self._split_into_windows(messages)
        logger.debug(
            "windows_created",
            conv_id=conv_id,
            num_windows=len(windows),
        )

        previous_summary = ""

        for window_idx, window_messages in enumerate(windows):
            window_text = self._build_conversation_text(window_messages)

            if previous_summary:
                context_text = (
                    f"[PREVIOUS CONTEXT SUMMARY]\n{previous_summary}\n\n"
                    f"[CURRENT WINDOW]\n{window_text}"
                )
            else:
                context_text = window_text

            logger.debug(
                "processing_window",
                conv_id=conv_id,
                window_idx=window_idx,
                messages_in_window=len(window_messages),
                has_previous_summary=bool(previous_summary),
            )

            extracted = self._extract_single(context_text, conv_id)

            all_entities = self._merge_entities(all_entities, extracted["entities"])
            all_attributes = self._merge_attributes(
                all_attributes, extracted["attributes"]
            )
            all_processes = self._merge_processes(all_processes, extracted["processes"])

            if window_idx < len(windows) - 1:
                previous_summary = self._summarize_for_folding(
                    previous_summary, window_messages, extracted
                )

        return {
            "entities": all_entities,
            "attributes": all_attributes,
            "processes": all_processes,
        }

    def _split_into_windows(self, messages: list[Message]) -> list[list[Message]]:
        """Split messages into windows that fit within token limit.

        Args:
            messages: Full list of messages

        Returns:
            List of message windows
        """
        windows: list[list[Message]] = []
        current_window: list[Message] = []
        current_chars = 0

        for msg in messages:
            msg_chars = len(msg.content)

            if msg_chars > self.max_chars:
                if current_window:
                    windows.append(current_window)
                    current_window = []
                    current_chars = 0
                windows.append([msg])
                continue

            if current_chars + msg_chars > self.max_chars:
                if current_window:
                    windows.append(current_window)
                current_window = [msg]
                current_chars = msg_chars
            else:
                current_window.append(msg)
                current_chars += msg_chars

        if current_window:
            windows.append(current_window)

        return windows

    def _summarize_for_folding(
        self,
        previous_summary: str,
        window_messages: list[Message],
        extracted: dict[str, Any],
    ) -> str:
        """Create a summary of processed content for folding into next window.

        Args:
            previous_summary: Summary from previous windows
            window_messages: Messages in current window
            extracted: Extraction results from current window

        Returns:
            Combined summary for next window's context
        """
        try:
            messages_for_summary = [
                {"role": msg.role, "content": msg.content[:500]}
                for msg in window_messages
            ]
            conversation_summary = self.summarizer.summarize(messages_for_summary)

            extracted_parts = []
            if extracted["entities"]:
                entity_names = [e.canonical_name for e in extracted["entities"][:5]]
                extracted_parts.append(f"Entities: {', '.join(entity_names)}")
            if extracted["attributes"]:
                attr_summaries = [
                    f"{a['entity_name']}.{a['attribute'].slot}={a['attribute'].value}"
                    for a in extracted["attributes"][:5]
                ]
                extracted_parts.append(f"Facts: {'; '.join(attr_summaries)}")
            if extracted["processes"]:
                proc_summaries = [p.trigger for p in extracted["processes"][:3]]
                extracted_parts.append(f"Processes: {'; '.join(proc_summaries)}")

            extracted_summary = "\n".join(extracted_parts) if extracted_parts else ""

            if previous_summary:
                return (
                    f"{previous_summary}\n\n"
                    f"[Window Content]: {conversation_summary}\n"
                    f"{extracted_summary}"
                )
            else:
                return f"[Window Content]: {conversation_summary}\n{extracted_summary}"

        except Exception as e:
            logger.warning("folding_summarize_failed", error=str(e))
            return previous_summary

    def _merge_entities(
        self, existing: list[Entity], new: list[Entity]
    ) -> list[Entity]:
        """Merge entity lists with deduplication by canonical_name."""
        existing_names = {e.canonical_name.lower() for e in existing}
        result = list(existing)

        for entity in new:
            if entity.canonical_name.lower() not in existing_names:
                result.append(entity)
                existing_names.add(entity.canonical_name.lower())

        return result

    def _merge_attributes(self, existing: list[dict], new: list[dict]) -> list[dict]:
        """Merge attribute lists with deduplication by (entity_name, slot, value)."""

        def attr_key(attr_dict: dict) -> tuple:
            attr = attr_dict["attribute"]
            return (
                attr_dict["entity_name"].lower(),
                attr.slot.lower(),
                attr.value.lower(),
            )

        existing_keys = {attr_key(a) for a in existing}
        result = list(existing)

        for attr_dict in new:
            key = attr_key(attr_dict)
            if key not in existing_keys:
                result.append(attr_dict)
                existing_keys.add(key)

        return result

    def _merge_processes(
        self, existing: list[Process], new: list[Process]
    ) -> list[Process]:
        """Merge process lists with deduplication by trigger similarity."""
        existing_triggers = {p.trigger.lower().strip() for p in existing}
        result = list(existing)

        for proc in new:
            if proc.trigger.lower().strip() not in existing_triggers:
                result.append(proc)
                existing_triggers.add(proc.trigger.lower().strip())

        return result

    def _build_conversation_text(self, messages: list[Message]) -> str:
        """Build formatted conversation text for extraction."""
        parts = []
        for msg in messages:
            role_label = msg.role.upper()
            content = msg.content[:5000] if len(msg.content) > 5000 else msg.content
            parts.append(f"[{role_label}] {content}")

        return "\n\n".join(parts)
