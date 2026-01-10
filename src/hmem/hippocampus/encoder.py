"""Memory Encoder - Converts unstructured dialogue to structured data (Phase 2)."""

from datetime import datetime
from typing import Literal

from hmem.models import Event, Conversation, SemanticTriple
from hmem.utils.llm import LLMClient
import structlog

logger = structlog.get_logger()


class MemoryEncoder:
    """Extracts structured information from raw conversations.

    Two extraction modes:
    1. Fact extraction: Entity-Relation triples (User -> Prefers -> DarkMode)
    2. Event extraction: Task-Action-Result chains

    Phase 2 implementation uses LLM for better extraction.

    Example:
        >>> encoder = MemoryEncoder()
        >>> conversation = Conversation(...)
        >>> events, facts = encoder.encode_conversation(conversation)
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """Initialize memory encoder.
        
        Args:
            llm_client: LLM client for fact extraction
        """
        self.llm_client = llm_client or LLMClient(use_mock=True)

    def extract_facts(self, text: str) -> list[SemanticTriple]:
        """Extract entity-relation triples using LLM.

        Args:
            text: Raw conversation text

        Returns:
            List of semantic triples
        """
        return self.llm_client.extract_facts(text)

    def extract_events(self, conversation: Conversation) -> list[Event]:
        """Extract events from conversation.

        Args:
            conversation: Conversation to process

        Returns:
            List of structured events
        """
        events, _ = self.encode_conversation(conversation)
        return events
    
    def encode_conversation(
        self,
        conversation: Conversation
    ) -> tuple[list[Event], list[SemanticTriple]]:
        """Encode conversation into events and facts.
        
        Args:
            conversation: Conversation to encode
            
        Returns:
            Tuple of (events, semantic_facts)
        """
        events = []
        all_facts = []
        
        for i, message in enumerate(conversation.messages):
            if message.role == "user":
                event = self._message_to_event(message, conversation.session_id, i)
                events.append(event)
            
            facts = self.llm_client.extract_facts(message.content)
            all_facts.extend(facts)
        
        logger.info(
            "conversation_encoded",
            session_id=conversation.session_id,
            events=len(events),
            facts=len(all_facts)
        )
        
        return events, all_facts
    
    def _message_to_event(
        self,
        message,
        session_id: str,
        index: int
    ) -> Event:
        """Convert a message to an event.
        
        Args:
            message: Message to convert
            session_id: Session identifier
            index: Message index in conversation
            
        Returns:
            Event object
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
                "role": message.role
            }
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
            "learn": "learning"
        }
        
        tags = []
        for keyword, tag in keywords.items():
            if keyword in content_lower:
                tags.append(tag)
        
        return list(set(tags)) if tags else ["general"]
