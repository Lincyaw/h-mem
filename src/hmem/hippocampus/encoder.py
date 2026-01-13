"""Memory Encoder - Converts unstructured dialogue to structured data with provenance."""

from datetime import datetime
from typing import Literal, Protocol
import uuid

from hmem.models import Event, Conversation, SemanticTriple, Message
import structlog
from hmem.agents.llm import LLMClient

logger = structlog.get_logger()


class LLMClientProtocol(Protocol):
    def extract_facts(self, content: str) -> list[SemanticTriple]: ...


class MemoryEncoder:
    """Extracts structured information from raw conversations with provenance tracking.

    Two extraction modes:
    1. Fact extraction: Entity-Relation triples (User -> Prefers -> DarkMode)
    2. Event extraction: Task-Action-Result chains

    All derived memories maintain links to their source (parent_ids)
    to support the hierarchical semantic graph.

    Example:
        >>> encoder = MemoryEncoder()
        >>> conversation = Conversation(...)
        >>> events, facts = encoder.encode_conversation(conversation)
        >>> # events[0].parent_ids contains the conversation ID
    """

    def __init__(self, llm_client: LLMClientProtocol | None = None) -> None:
        """Initialize memory encoder.

        Args:
            llm_client: LLM client for fact extraction
        """
        if llm_client is None:
            llm_client = LLMClient()
        self.llm_client = llm_client

    def extract_facts(
        self, text: str, parent_ids: list[str] | None = None
    ) -> list[SemanticTriple]:
        """Extract entity-relation triples using LLM with provenance.

        Args:
            text: Raw conversation text
            parent_ids: IDs of source memories for provenance

        Returns:
            List of semantic triples with parent_ids set
        """
        facts = self.llm_client.extract_facts(text)

        # Set provenance for each fact
        if parent_ids:
            for fact in facts:
                fact.parent_ids = parent_ids
                fact.derivation_type = "extraction"

        return facts

    def extract_events(self, conversation: Conversation) -> list[Event]:
        """Extract events from conversation with provenance.

        Args:
            conversation: Conversation to process

        Returns:
            List of structured events with parent_ids linking to conversation
        """
        events, _ = self.encode_conversation(conversation)
        return events

    def encode_conversation(
        self, conversation: Conversation
    ) -> tuple[list[Event], list[SemanticTriple]]:
        """Encode conversation into events and facts with provenance tracking.

        Each derived event/fact maintains a link to the source conversation
        through the parent_ids field.

        Args:
            conversation: Conversation to encode

        Returns:
            Tuple of (events, semantic_facts) with provenance set
        """
        events = []
        all_facts = []

        # Ensure conversation has an ID
        conv_id = conversation.id or f"conv_{uuid.uuid4().hex[:12]}"

        for i, message in enumerate(conversation.messages):
            if message.role == "user":
                event = self._message_to_event(
                    message, conversation.session_id, i, conv_id
                )
                events.append(event)

            # Extract facts with provenance linking to conversation
            facts = self.llm_client.extract_facts(message.content)
            for fact in facts:
                fact.parent_ids = [conv_id]
                fact.derivation_type = "extraction"
            all_facts.extend(facts)

        logger.info(
            "conversation_encoded",
            session_id=conversation.session_id,
            conversation_id=conv_id,
            events=len(events),
            facts=len(all_facts),
        )

        return events, all_facts

    def _message_to_event(
        self, message: Message, session_id: str, index: int, conversation_id: str
    ) -> Event:
        """Convert a message to an event with provenance.

        Args:
            message: Message to convert
            session_id: Session identifier
            index: Message index in conversation
            conversation_id: ID of the source conversation

        Returns:
            Event object with parent_ids set to the conversation
        """
        outcome = self._infer_outcome(message.content)
        tags = self._extract_tags(message.content)

        return Event(
            content=message.content,
            outcome=outcome,
            tags=tags,
            timestamp=datetime.now(),
            metadata={
                "session_id": session_id,
                "message_index": index,
                "role": message.role,
            },
            parent_ids=[conversation_id],
            derivation_type="extraction",
        )

    def _infer_outcome(self, content: str) -> Literal["success", "failure", "unknown"]:
        """Infer outcome from content (simple heuristic).

        Args:
            content: Message content

        Returns:
            Inferred outcome
        """
        content_lower = content.lower()

        success_keywords = ["success", "worked", "fixed", "solved", "completed"]
        failure_keywords = ["failed", "error", "broken", "crash", "bug"]

        if any(kw in content_lower for kw in success_keywords):
            return "success"
        elif any(kw in content_lower for kw in failure_keywords):
            return "failure"
        else:
            return "unknown"

    def _extract_tags(self, content: str) -> list[str]:
        """Extract tags from content (simple keyword matching).

        Args:
            content: Message content

        Returns:
            List of tags
        """
        content_lower = content.lower()

        keywords = {
            "python": "python",
            "scraping": "web_scraping",
            "scrape": "web_scraping",
            "debug": "debugging",
            "error": "error_handling",
            "test": "testing",
            "learn": "learning",
        }

        tags = []
        for keyword, tag in keywords.items():
            if keyword in content_lower:
                tags.append(tag)

        return list(set(tags)) if tags else ["general"]
