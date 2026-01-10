"""Event Sourcing infrastructure - Single source of truth.

Solves dual-write consistency between ChromaDB and SQLite by using
append-only event log as the primary store. Vector/graph stores become
derived views that can be rebuilt from events.
"""

from datetime import datetime
from pathlib import Path

from hmem.models import Event


class EventLog:
    """Append-only event log for memory events.

    This is the single source of truth. All other stores (ChromaDB, SQLite)
    are derived views that can be reconstructed by replaying events.

    Schema:
        - id: Auto-increment primary key
        - event_type: 'interaction' | 'consolidation' | 'reflection'
        - content: JSON serialized event data
        - timestamp: Event creation time
        - processed: Whether event has been projected to derived views

    Benefits:
        - Write only succeeds if event log append succeeds
        - Derived views can fail without data loss
        - Full audit trail and time-travel capability
        - Zero-risk data migration (replay events)
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize event log.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._initialized = False

    def append(self, event: Event) -> int:
        """Append new event to log.

        Args:
            event: Event to append

        Returns:
            Event ID (auto-incremented)

        Raises:
            MemoryError: If append fails
        """
        raise NotImplementedError("Phase 1 implementation pending")

    def get_unprocessed(self, limit: int = 100) -> list[Event]:
        """Get unprocessed events for projection.

        Args:
            limit: Maximum events to fetch

        Returns:
            List of events where processed=False
        """
        raise NotImplementedError("Phase 1 implementation pending")

    def mark_processed(self, event_id: int) -> None:
        """Mark event as successfully projected.

        Args:
            event_id: ID of event to mark
        """
        raise NotImplementedError("Phase 1 implementation pending")

    def replay(self, from_time: datetime | None = None) -> list[Event]:
        """Replay events for rebuilding derived views.

        Args:
            from_time: Optional start time (None = all events)

        Returns:
            All events since from_time
        """
        raise NotImplementedError("Phase 1 implementation pending")
