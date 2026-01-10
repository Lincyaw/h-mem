"""Consolidator - Simulates sleep process for memory consolidation.

Handles writing, conflict resolution, and active forgetting with proper
transaction management and error handling.

Key mechanisms:
- Semantic conflict detection and resolution
- Reconsolidation (weight updates on retrieval)
- Active forgetting (decay + interference-based pruning)
- Async consolidation mode for non-blocking operation
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol, Any
import structlog

from hmem.exceptions import ConsolidationError
from hmem.models import ConsolidationResult, Event, SemanticTriple
from hmem.strategies.locks import LockProvider, FileLockProvider

logger = structlog.get_logger()

# Shared thread pool for async consolidation
_consolidation_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """Get or create the shared thread pool executor."""
    global _consolidation_executor
    with _executor_lock:
        if _consolidation_executor is None:
            _consolidation_executor = ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="consolidation"
            )
        return _consolidation_executor


class SemanticStoreProtocol(Protocol):
    """Protocol for semantic store used by Consolidator."""

    def add_or_update(
        self, triple: SemanticTriple, parent_ids: list[str] | None = None
    ) -> tuple[bool, int]: ...

    def check_conflict(
        self, subject: str, predicate: str, new_object: str
    ) -> tuple[bool, list[Any]]: ...

    def resolve_conflict(
        self,
        subject: str,
        predicate: str,
        old_object: str,
        new_object: str,
        new_parent_ids: list[str] | None = None,
    ) -> int: ...

    def prune_low_weight(self, threshold: float) -> int: ...

    def apply_decay(self, decay_factor: float, min_weight: float) -> int: ...


class EncoderProtocol(Protocol):
    """Protocol for memory encoder used by Consolidator."""

    def extract_facts(
        self, text: str, parent_ids: list[str] | None = None
    ) -> list[SemanticTriple]: ...


class Consolidator:
    """Orchestrates memory consolidation process.

    Responsibilities:
    1. Write events to long-term storage
    2. Detect and resolve conflicts (semantic graph)
    3. Apply forgetting mechanisms (decay + interference)
    4. Manage transactions with optimistic locking

    Execution modes:
    - Phase 1: Synchronous (blocking at session end)
    - Phase 3: Asynchronous (background queue)

    Example:
        >>> consolidator = Consolidator()
        >>> result = consolidator.consolidate("sess_001", events)
        >>> print(result.stored_events, result.updated_facts)
    """

    def __init__(
        self,
        lock_provider: LockProvider | None = None,
        semantic_store: SemanticStoreProtocol | None = None,
        encoder: EncoderProtocol | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        forgetting_threshold: float = 0.3,
        decay_factor: float = 0.99,
    ):
        """Initialize consolidator.

        Args:
            lock_provider: Lock provider for transaction management (default: FileLockProvider)
            semantic_store: Semantic store for fact storage and conflict resolution
            encoder: Memory encoder for fact extraction
            max_retries: Maximum consolidation retry attempts on transient errors
            retry_delay: Base delay between retries (uses exponential backoff)
            forgetting_threshold: Weight threshold below which facts are pruned
            decay_factor: Multiplier for time-based weight decay
        """
        self.lock_provider = lock_provider or FileLockProvider()
        self.semantic_store = semantic_store
        self.encoder = encoder
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.forgetting_threshold = forgetting_threshold
        self.decay_factor = decay_factor

    def consolidate(
        self,
        session_id: str,
        events: list[Event],
    ) -> ConsolidationResult:
        """Execute consolidation for session with transaction safety.

        Args:
            session_id: Session to consolidate
            events: Events to consolidate

        Returns:
            Statistics of consolidation

        Raises:
            ConsolidationError: If consolidation fails after all retries
        """
        if not events:
            logger.warning("consolidation_empty", session_id=session_id)
            return ConsolidationResult(
                success=True,
                stored_events=0,
                updated_facts=0,
                conflicts_resolved=0,
                errors=["No events to consolidate"],
                metadata={"session_id": session_id},
            )

        # Acquire session lock to prevent concurrent consolidation
        try:
            with self.lock_provider.acquire(f"consolidate:{session_id}", timeout=30.0):
                return self._consolidate_with_retries(session_id, events)
        except Exception as e:
            logger.error(
                "consolidation_failed",
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ConsolidationError(
                f"Failed to consolidate session {session_id}: {e}"
            ) from e

    def _consolidate_with_retries(
        self,
        session_id: str,
        events: list[Event],
    ) -> ConsolidationResult:
        """Execute consolidation with exponential backoff retry logic.

        Args:
            session_id: Session identifier
            events: Events to consolidate

        Returns:
            Consolidation result

        Raises:
            ConsolidationError: If all retries exhausted
        """
        import time

        last_error = None

        for attempt in range(self.max_retries):
            try:
                return self._do_consolidate(session_id, events)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)  # Exponential backoff
                    logger.warning(
                        "consolidation_retry",
                        session_id=session_id,
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        delay=delay,
                        error=str(e),
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "consolidation_retries_exhausted",
                        session_id=session_id,
                        attempts=self.max_retries,
                        final_error=str(e),
                    )

        raise ConsolidationError(
            f"Consolidation failed after {self.max_retries} attempts"
        ) from last_error

    def _do_consolidate(
        self,
        session_id: str,
        events: list[Event],
    ) -> ConsolidationResult:
        """Perform actual consolidation work.

        This is the core consolidation logic:
        1. Validate events
        2. Extract semantic facts from events
        3. Detect and resolve conflicts
        4. Apply forgetting mechanisms
        5. Return statistics

        Args:
            session_id: Session identifier
            events: Events to consolidate

        Returns:
            Consolidation statistics
        """
        stored_events = len(events)
        updated_facts = 0
        conflicts_resolved = 0
        errors: list[str] = []

        # Validate events
        for idx, event in enumerate(events):
            if not event.content:
                errors.append(f"Event {idx} has empty content")

        # Extract and store semantic facts (if encoder and store available)
        if self.encoder and self.semantic_store:
            for event in events:
                try:
                    facts = self.encoder.extract_facts(
                        event.content,
                        parent_ids=event.parent_ids,
                    )

                    for fact in facts:
                        # Check for conflicts before adding
                        resolved = self._handle_fact_with_conflict_check(
                            fact, event.parent_ids
                        )
                        conflicts_resolved += resolved
                        updated_facts += 1

                except Exception as e:
                    errors.append(f"Fact extraction failed for event: {e}")
                    logger.warning(
                        "fact_extraction_failed",
                        event_id=event.id,
                        error=str(e),
                    )

        # Apply forgetting mechanisms
        forgotten = self._apply_forgetting()

        success = len(errors) == 0

        logger.info(
            "consolidation_complete",
            session_id=session_id,
            stored_events=stored_events,
            updated_facts=updated_facts,
            conflicts=conflicts_resolved,
            forgotten=forgotten,
            success=success,
        )

        return ConsolidationResult(
            success=success,
            stored_events=stored_events,
            updated_facts=updated_facts,
            conflicts_resolved=conflicts_resolved,
            errors=errors,
            metadata={
                "session_id": session_id,
                "event_types": [e.outcome for e in events],
                "facts_forgotten": forgotten,
            },
        )

    def _handle_fact_with_conflict_check(
        self,
        fact: SemanticTriple,
        parent_ids: list[str] | None = None,
    ) -> int:
        """Add fact with conflict detection and resolution.

        Args:
            fact: Semantic triple to add
            parent_ids: Parent memory IDs for provenance

        Returns:
            Number of conflicts resolved
        """
        if not self.semantic_store:
            return 0

        # Check for conflicts
        has_conflict, conflicting = self.semantic_store.check_conflict(
            fact.subject, fact.predicate, fact.object
        )

        if has_conflict and conflicting:
            # Resolve each conflict
            resolved = 0
            for old_triple in conflicting:
                old_obj = (
                    old_triple.object
                    if hasattr(old_triple, "object")
                    else str(old_triple)
                )
                resolved += self.semantic_store.resolve_conflict(
                    fact.subject,
                    fact.predicate,
                    old_obj,
                    fact.object,
                    parent_ids,
                )
            return resolved
        else:
            # No conflict - add or update
            self.semantic_store.add_or_update(fact, parent_ids)
            return 0

    def _apply_forgetting(self) -> int:
        """Apply active forgetting mechanisms.

        This implements the cognitive principle that memories must be
        actively maintained - unused memories gradually fade.

        Two mechanisms:
        1. Decay: All weights slowly decrease over time
        2. Pruning: Low-weight facts are removed

        Returns:
            Number of facts forgotten (pruned)
        """
        if not self.semantic_store:
            return 0

        # Apply time-based decay
        decayed = self.semantic_store.apply_decay(
            decay_factor=self.decay_factor,
            min_weight=self.forgetting_threshold,
        )

        # Prune low-weight facts
        pruned = self.semantic_store.prune_low_weight(
            threshold=self.forgetting_threshold
        )

        if pruned > 0:
            logger.info(
                "active_forgetting_applied",
                decayed=decayed,
                pruned=pruned,
            )

        return pruned

    def _resolve_conflicts(self, facts: list[SemanticTriple]) -> int:
        """Detect and resolve semantic conflicts.

        Args:
            facts: Newly extracted facts

        Returns:
            Number of conflicts resolved
        """
        if not self.semantic_store:
            return 0

        resolved = 0
        for fact in facts:
            resolved += self._handle_fact_with_conflict_check(fact, fact.parent_ids)

        return resolved

    def consolidate_async(
        self,
        session_id: str,
        events: list[Event],
    ) -> None:
        """Execute consolidation asynchronously in background thread.

        Non-blocking consolidation for improved response times.
        Uses a shared thread pool to limit concurrent consolidations.

        Args:
            session_id: Session to consolidate
            events: Events to consolidate

        Note:
            - Results are logged but not returned (fire-and-forget)
            - Failures are logged as warnings, not raised
            - For blocking consolidation, use consolidate() instead
        """
        if not events:
            logger.debug(
                "async_consolidation_skipped", session_id=session_id, reason="no_events"
            )
            return

        def _background_consolidate() -> None:
            try:
                result = self.consolidate(session_id, events)
                logger.info(
                    "async_consolidation_complete",
                    session_id=session_id,
                    stored_events=result.stored_events,
                    updated_facts=result.updated_facts,
                    success=result.success,
                )
            except Exception as e:
                logger.warning(
                    "async_consolidation_failed",
                    session_id=session_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )

        executor = _get_executor()
        executor.submit(_background_consolidate)

        logger.debug(
            "async_consolidation_submitted",
            session_id=session_id,
            event_count=len(events),
        )
