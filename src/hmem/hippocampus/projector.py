"""Event Projector - Projects events from log to derived views.

Implements the projection layer of Event Sourcing architecture.
Handles asynchronous projection with retry logic.
"""

import asyncio
from datetime import datetime
from typing import Protocol, Any
import structlog

from hmem.models import Event, SemanticTriple
from hmem.exceptions import ConsolidationError

logger = structlog.get_logger()


class EpisodicStoreProtocol(Protocol):
    """Protocol for episodic store implementations."""

    def add_event(self, event: Event) -> str:
        """Add event to store."""
        ...


class SemanticStoreProtocol(Protocol):
    """Protocol for semantic store implementations."""

    def add_or_update(
        self, triple: SemanticTriple, parent_ids: list[str] | None = None
    ) -> tuple[bool, int]:
        """Add or update triple."""
        ...

    def check_conflict(
        self, subject: str, predicate: str, new_object: str
    ) -> tuple[bool, list[Any]]:
        """Check for conflicts."""
        ...

    def resolve_conflict(
        self,
        subject: str,
        predicate: str,
        old_object: str,
        new_object: str,
        new_parent_ids: list[str] | None = None,
    ) -> int:
        """Resolve conflict."""
        ...


class EventLogProtocol(Protocol):
    """Protocol for event log implementations."""

    def get_unprocessed(self, limit: int = 100) -> list[Event]:
        """Get unprocessed events."""
        ...

    def mark_processed(self, entry_id: str) -> bool:
        """Mark entry as processed."""
        ...

    def replay(self, from_time: datetime | None = None) -> list[Event]:
        """Replay events from a point in time."""
        ...


class EventProjector:
    """Projects events from event log to derived views.

    Responsibilities:
    1. Read unprocessed events from event log
    2. Project to episodic store (vector DB)
    3. Project to semantic store (graph DB)
    4. Mark events as processed
    5. Handle failures with retry logic

    Example:
        >>> projector = EventProjector(event_log, episodic_store, semantic_store)
        >>> result = projector.project_all()
        >>> print(result)  # {'projected': 10, 'failed': 0}
    """

    def __init__(
        self,
        event_log: EventLogProtocol,
        episodic_store: EpisodicStoreProtocol,
        semantic_store: SemanticStoreProtocol | None = None,
        encoder: Any = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """Initialize event projector.

        Args:
            event_log: Source event log
            episodic_store: Target episodic store
            semantic_store: Target semantic store (optional)
            encoder: Memory encoder for fact extraction
            max_retries: Maximum retry attempts
            retry_delay: Base delay between retries
        """
        self.event_log = event_log
        self.episodic_store = episodic_store
        self.semantic_store = semantic_store
        self.encoder = encoder
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def project_all(self, batch_size: int = 100) -> dict[str, int]:
        """Project all unprocessed events to derived views.

        Args:
            batch_size: Number of events to process in one batch

        Returns:
            Statistics: {'projected': N, 'failed': M}
        """
        unprocessed = self.event_log.get_unprocessed(limit=batch_size)

        projected = 0
        failed = 0

        for event in unprocessed:
            try:
                self._project_event(event)
                entry_id = event.metadata.get("_log_entry_id", event.id)
                if entry_id:
                    self.event_log.mark_processed(entry_id)
                projected += 1
            except Exception as e:
                logger.error(
                    "projection_failed",
                    event_id=event.id,
                    error=str(e),
                )
                failed += 1

        logger.info(
            "projection_batch_complete",
            projected=projected,
            failed=failed,
            remaining=len(unprocessed) - projected,
        )

        return {"projected": projected, "failed": failed}

    def project_batch(self, events: list[Event]) -> dict[str, int]:
        """Project batch of events to all views.

        Args:
            events: Events to project

        Returns:
            Statistics: {"vector_updates": N, "graph_updates": M}
        """
        vector_updates = 0
        graph_updates = 0

        for event in events:
            try:
                self._project_to_episodic(event)
                vector_updates += 1

                if self.semantic_store and self.encoder:
                    graph_updates += self._project_to_semantic(event)
            except Exception as e:
                logger.error("batch_projection_failed", event_id=event.id, error=str(e))

        return {"vector_updates": vector_updates, "graph_updates": graph_updates}

    def _project_event(self, event: Event) -> None:
        """Project single event to all stores.

        Args:
            event: Event to project

        Raises:
            ConsolidationError: If projection fails after retries
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # Project to episodic store
                self._project_to_episodic(event)

                # Project to semantic store (if available and encoder present)
                if self.semantic_store and self.encoder:
                    self._project_to_semantic(event)

                return

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)
                    logger.warning(
                        "projection_retry",
                        event_id=event.id,
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    import time

                    time.sleep(delay)

        raise ConsolidationError(
            f"Failed to project event {event.id} after {self.max_retries} attempts"
        ) from last_error

    def _project_to_episodic(self, event: Event) -> str:
        """Project event to episodic store.

        Args:
            event: Event to project

        Returns:
            Event ID in episodic store
        """
        return self.episodic_store.add_event(event)

    def project_to_vector_store(self, events: list[Event]) -> int:
        """Project to vector store (ChromaDB).

        Args:
            events: Events to project

        Returns:
            Number of vectors added
        """
        count = 0
        for event in events:
            try:
                self._project_to_episodic(event)
                count += 1
            except Exception as e:
                logger.error(
                    "vector_projection_failed", event_id=event.id, error=str(e)
                )
        return count

    def _project_to_semantic(self, event: Event) -> int:
        """Project event to semantic store.

        Extracts facts from event content and adds them to semantic store.

        Args:
            event: Event to project

        Returns:
            Number of facts added
        """
        if not self.encoder or not self.semantic_store:
            return 0

        # Extract facts from event content
        facts = self.encoder.llm_client.extract_facts(event.content)

        added = 0
        for fact in facts:
            # Set provenance
            fact.parent_ids = (event.parent_ids or []) + (
                [event.id] if event.id else []
            )
            fact.derivation_type = "derivation"

            # Check for conflicts
            has_conflict, conflicting = self.semantic_store.check_conflict(
                fact.subject, fact.predicate, fact.object
            )

            if has_conflict and conflicting:
                # Resolve conflict by superseding old fact
                # check_conflict returns list[SemanticTriple], so .object is always available
                for old_triple in conflicting:
                    self.semantic_store.resolve_conflict(
                        fact.subject,
                        fact.predicate,
                        old_triple.object,
                        fact.object,
                        fact.parent_ids,
                    )
            else:
                # Add new fact
                self.semantic_store.add_or_update(fact, fact.parent_ids)

            added += 1

        return added

    def project_to_semantic_graph(self, events: list[Event]) -> int:
        """Project to semantic graph.

        Args:
            events: Events to project

        Returns:
            Number of triples updated
        """
        count = 0
        for event in events:
            count += self._project_to_semantic(event)
        return count

    def rebuild_from_log(self, from_time: datetime | None = None) -> dict[str, int]:
        """Rebuild derived views by replaying event log.

        This is the recovery mechanism for event sourcing.
        Used when derived views are corrupted or need migration.

        Args:
            from_time: Start time for replay (None = all events)

        Returns:
            Statistics: {'replayed': N, 'failed': M}
        """
        events = self.event_log.replay(from_time)

        replayed = 0
        failed = 0

        for event in events:
            try:
                self._project_event(event)
                replayed += 1
            except Exception as e:
                logger.error(
                    "replay_projection_failed",
                    event_id=event.id,
                    error=str(e),
                )
                failed += 1

        logger.info(
            "rebuild_complete",
            from_time=from_time.isoformat() if from_time else "beginning",
            replayed=replayed,
            failed=failed,
        )

        return {"replayed": replayed, "failed": failed}


class AsyncEventProjector:
    """Asynchronous event projector for Phase 3.

    Processes events in background with configurable concurrency.
    Supports graceful shutdown and fallback to synchronous mode.
    """

    def __init__(
        self,
        projector: EventProjector,
        max_concurrent: int = 5,
        poll_interval: float = 1.0,
        fallback_to_sync: bool = True,
    ):
        """Initialize async projector.

        Args:
            projector: Underlying synchronous projector
            max_concurrent: Maximum concurrent projections
            poll_interval: Seconds between polling for new events
            fallback_to_sync: Whether to fallback to sync on queue failure
        """
        self.projector = projector
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self.fallback_to_sync = fallback_to_sync
        self._running = False
        self._task: asyncio.Task | None = None
        self._queue: asyncio.Queue[Event] = asyncio.Queue()

    async def start(self) -> None:
        """Start background projection loop."""
        self._running = True
        self._task = asyncio.create_task(self._projection_loop())
        logger.info("async_projector_started")

    async def stop(self) -> None:
        """Stop background projection loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("async_projector_stopped")

    async def enqueue(self, event: Event) -> bool:
        """Add event to projection queue.

        Args:
            event: Event to project

        Returns:
            True if queued, False if fallback to sync
        """
        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            if self.fallback_to_sync:
                logger.warning("queue_full_fallback_sync", event_id=event.id)
                self.projector._project_event(event)
                return True
            return False

    async def _projection_loop(self) -> None:
        """Background loop that processes events."""
        while self._running:
            try:
                # Project in batches
                result = self.projector.project_all(batch_size=self.max_concurrent)

                # If no events processed, wait before polling again
                if result["projected"] == 0:
                    await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error("async_projection_error", error=str(e))
                await asyncio.sleep(self.poll_interval)
