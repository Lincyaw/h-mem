"""Event Log - Append-only source of truth for all memory operations.

Following Event Sourcing pattern: all changes are immutable events.
"""

from datetime import datetime
from pathlib import Path

from hmem.models import Event, Conversation


class EventLog:
    """Append-only event store (single source of truth).

    All memory modifications flow through here first.
    Projections (vector/graph DBs) are rebuilt from this log.

    Storage: Simple in-memory (Phase 1) -> SQLite (Phase 2)

    Example:
        >>> log = EventLog()
        >>> log.append(conversation)
        >>> events = log.get_session_events("session_123")
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize event log.

        Args:
            db_path: Path to SQLite database file (None = in-memory)
        """
        self.db_path = db_path
        self._initialized = False
        self._events: dict[str, list[Conversation]] = {}  # In-memory for Phase 1

    def append(self, conversation: Conversation) -> None:
        """Append conversation to log.

        Args:
            conversation: Conversation to log
        """
        session_id = conversation.session_id
        if session_id not in self._events:
            self._events[session_id] = []
        self._events[session_id].append(conversation)

    def get_session_events(self, session_id: str) -> list[Event]:
        """Get all events for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of events from this session
        """
        conversations = self._events.get(session_id, [])
        
        # Convert conversations to events (simplified for Phase 1)
        events = []
        for conv in conversations:
            # Create an event from the conversation
            content = " ".join(msg.content for msg in conv.messages)
            event = Event(
                content=content,
                outcome="unknown",
                tags=[],
                timestamp=datetime.now(),
                metadata={"session_id": session_id},
            )
            events.append(event)
        
        return events

    def get_unprocessed(self, limit: int = 100) -> list[Event]:
        """Get unprocessed events for projection.

        Args:
            limit: Maximum events to fetch

        Returns:
            List of events where processed=False
        """
        raise NotImplementedError("Phase 2 implementation")

    def mark_processed(self, event_id: int) -> None:
        """Mark event as successfully projected.

        Args:
            event_id: ID of event to mark
        """
        raise NotImplementedError("Phase 2 implementation")

    def replay(self, from_time: datetime | None = None) -> list[Event]:
        """Replay events for rebuilding derived views.

        Args:
            from_time: Optional start time (None = all events)

        Returns:
            All events since from_time
        """
        raise NotImplementedError("Phase 2 implementation")
    
    def get_all_sessions(self) -> list[str]:
        """Get all session IDs.

        Returns:
            List of session identifiers
        """
        return list(self._events.keys())
