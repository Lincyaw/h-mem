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
    def infer_outcome(
        self, content: str
    ) -> Literal["success", "failure", "unknown"]: ...
    def extract_tags(self, content: str, max_tags: int = 5) -> list[str]: ...


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
        """Infer outcome from content using LLM with keyword fallback.

        Args:
            content: Message content

        Returns:
            Inferred outcome
        """
        # Try LLM-based inference first
        try:
            outcome = self.llm_client.infer_outcome(content)
            if outcome in ("success", "failure"):
                return outcome
        except Exception as e:
            logger.warning("llm_outcome_inference_failed", error=str(e))

        # Fallback to keyword matching
        return self._infer_outcome_keywords(content)

    def _infer_outcome_keywords(
        self, content: str
    ) -> Literal["success", "failure", "unknown"]:
        """Fallback keyword-based outcome inference.

        Args:
            content: Message content

        Returns:
            Inferred outcome based on keywords
        """
        content_lower = content.lower()

        success_keywords = [
            "success",
            "succeeded",
            "successful",
            "worked",
            "works",
            "working",
            "fixed",
            "resolved",
            "solved",
            "completed",
            "done",
            "finished",
            "correct",
            "achieved",
            "accomplished",
            "perfect",
            "great",
        ]
        failure_keywords = [
            "failed",
            "failure",
            "fail",
            "error",
            "exception",
            "broken",
            "crash",
            "bug",
            "issue",
            "problem",
            "wrong",
            "incorrect",
            "doesn't work",
            "didn't work",
            "not working",
            "unable",
            "cannot",
        ]

        if any(kw in content_lower for kw in success_keywords):
            return "success"
        elif any(kw in content_lower for kw in failure_keywords):
            return "failure"
        else:
            return "unknown"

    def _extract_tags(self, content: str) -> list[str]:
        """Extract tags from content using LLM with keyword fallback.

        Args:
            content: Message content

        Returns:
            List of tags
        """
        # Try LLM-based extraction first
        try:
            tags = self.llm_client.extract_tags(content, max_tags=5)
            if tags:
                return tags
        except Exception as e:
            logger.warning("llm_tag_extraction_failed", error=str(e))

        # Fallback to keyword matching
        return self._extract_tags_keywords(content)

    def _extract_tags_keywords(self, content: str) -> list[str]:
        """Fallback keyword-based tag extraction.

        Args:
            content: Message content

        Returns:
            List of tags based on keyword matching
        """
        content_lower = content.lower()

        keywords = {
            "python": "python",
            "javascript": "javascript",
            "typescript": "typescript",
            "java": "java",
            "rust": "rust",
            "go": "golang",
            "scraping": "web_scraping",
            "scrape": "web_scraping",
            "crawl": "web_scraping",
            "api": "api_integration",
            "rest": "api_integration",
            "database": "database",
            "sql": "database",
            "debug": "debugging",
            "error": "error_handling",
            "exception": "error_handling",
            "test": "testing",
            "unittest": "testing",
            "pytest": "testing",
            "deploy": "deployment",
            "docker": "containerization",
            "kubernetes": "containerization",
            "git": "version_control",
            "auth": "authentication",
            "security": "security",
            "performance": "performance",
            "optimize": "performance",
            "refactor": "refactoring",
            "learn": "learning",
        }

        tags = []
        for keyword, tag in keywords.items():
            if keyword in content_lower:
                tags.append(tag)

        return list(set(tags)) if tags else ["general"]
