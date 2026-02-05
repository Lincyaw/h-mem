"""Event Log - Append-only source of truth for all memory operations.

Following Event Sourcing pattern: all changes are immutable events.
ChromaDB and SemanticGraph are derived views that can be rebuilt from this log.
"""

from datetime import datetime
from pathlib import Path
from typing import Any
import uuid
import structlog

from hmem.models import Event, Conversation

logger = structlog.get_logger()


class EventLogEntry:
    """Internal representation of an event log entry."""

    def __init__(
        self,
        entry_id: str,
        event_type: str,
        payload: dict[str, Any],
        timestamp: datetime,
        processed: bool = False,
        session_id: str | None = None,
        sequence_num: int = 0,
    ):
        self.entry_id = entry_id
        self.event_type = event_type
        self.payload = payload
        self.timestamp = timestamp
        self.processed = processed
        self.session_id = session_id
        self.sequence_num = sequence_num


class EventLog:
    """Append-only event store (single source of truth).

    All memory modifications flow through here first.
    Projections (vector/graph DBs) are rebuilt from this log.

    Event Types:
    - 'conversation': Raw conversation ingested
    - 'event': Extracted episodic event
    - 'fact': Extracted semantic fact
    - 'principle': Induced principle

    Storage: In-memory (Phase 1) -> SQLite (Phase 2)

    Example:
        >>> log = EventLog()
        >>> log.append(conversation)
        >>> events = log.get_session_events("session_123")
        >>> unprocessed = log.get_unprocessed(limit=100)
        >>> log.mark_processed(event_id)
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize event log.

        Args:
            db_path: Path to SQLite database file (None = in-memory)
        """
        self.db_path = db_path
        self._initialized = False
        self._entries: dict[str, EventLogEntry] = {}  # entry_id -> entry
        self._sessions: dict[str, list[str]] = {}  # session_id -> entry_ids
        self._next_seq = 0

    def append(self, conversation: Conversation) -> str:
        """Append conversation to log.

        Args:
            conversation: Conversation to log

        Returns:
            Unique entry ID
        """
        entry_id = f"log_{uuid.uuid4().hex[:12]}"
        session_id = conversation.session_id

        entry = EventLogEntry(
            entry_id=entry_id,
            event_type="conversation",
            payload={
                "conversation_id": conversation.id,
                "session_id": session_id,
                "messages": [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp.isoformat(),
                    }
                    for msg in conversation.messages
                ],
                "metadata": conversation.metadata,
            },
            timestamp=datetime.now(),
            processed=False,
            session_id=session_id,
            sequence_num=self._next_seq,
        )

        self._entries[entry_id] = entry

        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append(entry_id)

        self._next_seq += 1

        logger.debug(
            "event_log_append",
            entry_id=entry_id,
            event_type="conversation",
            session_id=session_id,
        )

        return entry_id

    def append_event(self, event: Event, session_id: str) -> str:
        """Append an extracted event to the log.

        Args:
            event: Extracted event
            session_id: Associated session ID

        Returns:
            Unique entry ID
        """
        entry_id = f"log_{uuid.uuid4().hex[:12]}"

        entry = EventLogEntry(
            entry_id=entry_id,
            event_type="event",
            payload={
                "event_id": event.id,
                "content": event.content,
                "outcome": event.outcome,
                "tags": event.tags,
                "timestamp": event.timestamp.isoformat(),
                "metadata": event.metadata,
                "parent_ids": event.parent_ids,
                "derivation_type": event.derivation_type,
            },
            timestamp=datetime.now(),
            processed=False,
            session_id=session_id,
        )

        self._entries[entry_id] = entry

        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append(entry_id)

        return entry_id

    def _entry_to_event(self, entry: EventLogEntry) -> Event | None:
        """Convert a log entry to an Event object.

        Args:
            entry: Log entry to convert

        Returns:
            Event if conversion successful, None otherwise
        """
        if entry.event_type == "event":
            payload = entry.payload
            return Event(
                id=payload.get("event_id", entry.entry_id),
                content=payload.get("content", ""),
                outcome=payload.get("outcome", "unknown"),
                tags=payload.get("tags", []),
                timestamp=datetime.fromisoformat(payload.get("timestamp", "")),
                metadata=payload.get("metadata", {}),
                parent_ids=payload.get("parent_ids", []),
                derivation_type=payload.get("derivation_type", "extraction"),
            )
        elif entry.event_type == "conversation":
            messages = entry.payload.get("messages", [])
            content = " ".join(msg.get("content", "") for msg in messages)
            return Event(
                id=entry.entry_id,
                content=content,
                outcome="unknown",
                tags=[],
                timestamp=entry.timestamp,
                metadata=entry.payload.get("metadata", {}),
                parent_ids=[entry.payload.get("conversation_id", "")],
                derivation_type="extraction",
            )
        return None

    def get_session_events(self, session_id: str) -> list[Event]:
        """Get all events for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of events from this session
        """
        entry_ids = self._sessions.get(session_id, [])
        events = []

        for entry_id in entry_ids:
            entry = self._entries.get(entry_id)
            if entry:
                event = self._entry_to_event(entry)
                if event:
                    events.append(event)

        return events

    def get_unprocessed(self, limit: int = 100) -> list[Event]:
        """Get unprocessed events for projection.

        Args:
            limit: Maximum events to fetch

        Returns:
            List of events where processed=False
        """
        unprocessed = []

        for entry in self._entries.values():
            if not entry.processed and entry.event_type == "event":
                event = self._entry_to_event(entry)
                if event and event.metadata:
                    event.metadata["_log_entry_id"] = entry.entry_id
                    unprocessed.append(event)

                if len(unprocessed) >= limit:
                    break

        return unprocessed

    def mark_processed(self, entry_id: str) -> bool:
        """Mark event as successfully projected.

        Args:
            entry_id: ID of entry to mark

        Returns:
            True if marked, False if not found
        """
        if entry_id in self._entries:
            self._entries[entry_id].processed = True
            logger.debug("event_log_processed", entry_id=entry_id)
            return True
        return False

    def replay(self, from_time: datetime | None = None) -> list[Event]:
        """Replay events for rebuilding derived views.

        This is the core of event sourcing - any derived view can be
        rebuilt by replaying the event log from a given point in time.

        Args:
            from_time: Optional start time (None = all events)

        Returns:
            All events since from_time, ordered by timestamp
        """
        events = []

        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: e.timestamp,
        )

        for entry in sorted_entries:
            if from_time and entry.timestamp < from_time:
                continue

            event = self._entry_to_event(entry)
            if event:
                events.append(event)

        logger.info(
            "event_log_replay",
            from_time=from_time.isoformat() if from_time else "beginning",
            events_count=len(events),
        )

        return events

    def get_all_sessions(self) -> list[str]:
        """Get all session IDs.

        Returns:
            List of session identifiers
        """
        return list(self._sessions.keys())

    def get_entry(self, entry_id: str) -> EventLogEntry | None:
        """Get a specific log entry.

        Args:
            entry_id: Entry identifier

        Returns:
            EventLogEntry if found
        """
        return self._entries.get(entry_id)

    def count(self) -> dict[str, int]:
        """Get log statistics.

        Returns:
            Dictionary with counts
        """
        total = len(self._entries)
        processed = sum(1 for e in self._entries.values() if e.processed)
        unprocessed = total - processed

        return {
            "total_entries": total,
            "processed": processed,
            "unprocessed": unprocessed,
            "sessions": len(self._sessions),
        }

    def clear(self) -> int:
        """Clear all entries (for testing).

        Returns:
            Number of entries cleared
        """
        count = len(self._entries)
        self._entries.clear()
        self._sessions.clear()
        self._next_seq = 0
        return count

    def get_unprocessed_conversations(
        self, limit: int = 100
    ) -> list[tuple[str, Conversation]]:
        """Get unprocessed conversation entries for incremental processing.

        Args:
            limit: Maximum conversations to fetch

        Returns:
            List of (entry_id, Conversation) tuples, ordered by sequence number
        """
        unprocessed = []
        for entry in sorted(self._entries.values(), key=lambda e: e.sequence_num):
            if not entry.processed and entry.event_type == "conversation":
                conv = self._entry_to_conversation(entry)
                if conv:
                    unprocessed.append((entry.entry_id, conv))
            if len(unprocessed) >= limit:
                break
        return unprocessed

    def _entry_to_conversation(self, entry: EventLogEntry) -> Conversation | None:
        """Convert a conversation log entry back to a Conversation object.

        Args:
            entry: Log entry to convert

        Returns:
            Conversation if conversion successful, None otherwise
        """
        if entry.event_type != "conversation":
            return None

        from hmem.models import Message

        payload = entry.payload
        messages = []

        for msg_data in payload.get("messages", []):
            try:
                timestamp_str = msg_data.get("timestamp", "")
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str)
                else:
                    timestamp = entry.timestamp
                messages.append(
                    Message(
                        role=msg_data.get("role", "user"),
                        content=msg_data.get("content", ""),
                        timestamp=timestamp,
                    )
                )
            except Exception as e:
                logger.warning(
                    "event_log_message_conversion_failed",
                    entry_id=entry.entry_id,
                    error=str(e),
                )
                continue

        if not messages:
            return None

        return Conversation(
            id=payload.get("conversation_id", entry.entry_id),
            session_id=payload.get("session_id", entry.session_id or ""),
            messages=messages,
            metadata=payload.get("metadata", {}),
        )
