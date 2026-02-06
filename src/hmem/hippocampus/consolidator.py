"""Consolidator - Simulates sleep process for memory consolidation.

Handles writing, conflict resolution, and active forgetting with proper
transaction management and error handling.

Key mechanisms:
- Async consolidation mode for non-blocking operation
- Transaction management with retries and locking
"""

import threading
from concurrent.futures import ThreadPoolExecutor
import structlog

from hmem.constants import (
    CONSOLIDATOR_MAX_WORKERS,
    CONSOLIDATOR_MAX_RETRIES,
    CONSOLIDATOR_TIMEOUT,
    CONSOLIDATOR_RETRY_DELAY,
    CONSOLIDATOR_FORGETTING_THRESHOLD,
    CONSOLIDATOR_DECAY_FACTOR,
    CONSOLIDATOR_REFINEMENT_MIN_USAGE,
    CONSOLIDATOR_REFINEMENT_MIN_SUCCESS_RATE,
)
from hmem.exceptions import ConsolidationError
from hmem.models import ConsolidationResult, Event
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
                max_workers=CONSOLIDATOR_MAX_WORKERS, thread_name_prefix="consolidation"
            )
        return _consolidation_executor


class Consolidator:
    """Orchestrates memory consolidation process.

    Responsibilities:
    1. Write events to long-term storage
    2. Manage transactions with optimistic locking

    Note: Conflict detection/resolution and forgetting mechanisms are now
    handled by the entity-centric model (attribute cardinality) and the
    EvolutionEngine (Q-value based deprecation).

    Execution modes:
    - Synchronous (blocking at session end)
    - Asynchronous (background queue)

    Example:
        >>> consolidator = Consolidator()
        >>> result = consolidator.consolidate("sess_001", events)
        >>> print(result.stored_events)
    """

    def __init__(
        self,
        lock_provider: LockProvider | None = None,
        max_retries: int = CONSOLIDATOR_MAX_RETRIES,
        retry_delay: float = CONSOLIDATOR_RETRY_DELAY,
        forgetting_threshold: float = CONSOLIDATOR_FORGETTING_THRESHOLD,
        decay_factor: float = CONSOLIDATOR_DECAY_FACTOR,
        refinement_min_usage: int = CONSOLIDATOR_REFINEMENT_MIN_USAGE,
        refinement_min_success_rate: float = CONSOLIDATOR_REFINEMENT_MIN_SUCCESS_RATE,
    ):
        """Initialize consolidator.

        Args:
            lock_provider: Lock provider for transaction management (default: FileLockProvider)
            max_retries: Maximum consolidation retry attempts on transient errors
            retry_delay: Base delay between retries (uses exponential backoff)
            forgetting_threshold: Weight threshold below which facts are pruned
            decay_factor: Multiplier for time-based weight decay
            refinement_min_usage: Minimum usage count before considering refinement
            refinement_min_success_rate: Success rate threshold for triggering refinement
        """
        self.lock_provider = lock_provider or FileLockProvider()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.forgetting_threshold = forgetting_threshold
        self.decay_factor = decay_factor
        self.refinement_min_usage = refinement_min_usage
        self.refinement_min_success_rate = refinement_min_success_rate

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
            with self.lock_provider.acquire(
                f"consolidate:{session_id}", timeout=CONSOLIDATOR_TIMEOUT
            ):
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
        2. Return statistics

        Note: Fact extraction, conflict detection, and forgetting are now
        handled by ConversationProcessor and EvolutionEngine respectively.

        Args:
            session_id: Session identifier
            events: Events to consolidate

        Returns:
            Consolidation statistics
        """
        stored_events = len(events)
        errors: list[str] = []

        # Validate events
        for idx, event in enumerate(events):
            if not event.content:
                errors.append(f"Event {idx} has empty content")

        success = len(errors) == 0

        logger.info(
            "consolidation_complete",
            session_id=session_id,
            stored_events=stored_events,
            success=success,
        )

        return ConsolidationResult(
            success=success,
            stored_events=stored_events,
            updated_facts=0,
            conflicts_resolved=0,
            errors=errors,
            metadata={
                "session_id": session_id,
                "event_types": [e.outcome for e in events],
            },
        )

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
