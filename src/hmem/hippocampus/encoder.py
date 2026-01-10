"""Memory Encoder - Converts unstructured dialogue to structured data."""

from datetime import datetime

from hmem.models import Event, Conversation


class MemoryEncoder:
    """Extracts structured information from raw conversations.

    Two extraction modes:
    1. Fact extraction: Entity-Relation triples (User -> Prefers -> DarkMode)
    2. Event extraction: Task-Action-Result chains

    Uses simple heuristics (Phase 1) -> LLM with structured output (Phase 2)

    Example:
        >>> encoder = MemoryEncoder()
        >>> conversation = Conversation(...)
        >>> events = encoder.extract_events(conversation)
    """

    def __init__(self) -> None:
        """Initialize memory encoder."""
        pass

    def extract_facts(self, text: str) -> list[dict[str, str]]:
        """Extract entity-relation triples.

        Args:
            text: Raw conversation text

        Returns:
            List of (subject, predicate, object) triples
        """
        raise NotImplementedError("Phase 2 implementation")

    def extract_events(self, conversation: Conversation) -> list[Event]:
        """Extract events from conversation.

        Args:
            conversation: Conversation to process

        Returns:
            List of structured events
        """
        # Phase 1: Simple extraction - one event per conversation
        # Extract content from messages
        messages_content = []
        for msg in conversation.messages:
            messages_content.append(f"{msg.role}: {msg.content}")
        
        combined_content = "\n".join(messages_content)
        
        # Determine outcome based on keywords (simple heuristic)
        outcome = "unknown"
        lower_content = combined_content.lower()
        if any(word in lower_content for word in ["success", "worked", "fixed", "solved"]):
            outcome = "success"
        elif any(word in lower_content for word in ["failed", "error", "broken", "wrong"]):
            outcome = "failure"
        
        # Extract tags from content (simple keyword extraction)
        tags = []
        tag_keywords = ["python", "web", "scraping", "data", "analysis", "debugging"]
        for keyword in tag_keywords:
            if keyword in lower_content:
                tags.append(keyword)
        
        # Create event
        event = Event(
            content=combined_content,
            outcome=outcome,
            tags=tags,
            timestamp=datetime.now(),
            metadata={
                "session_id": conversation.session_id,
                "message_count": len(conversation.messages),
                **conversation.metadata,
            },
        )
        
        return [event]
