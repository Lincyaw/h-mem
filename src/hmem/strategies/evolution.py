"""Evolution trigger hooks for memory system.

Implements pluggable trigger strategies to determine when memory evolution
(refinement, deprecation, split, merge) should occur.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta

from hmem.models import SystemStats


class EvolutionTriggerHook(ABC):
    """Abstract base class for evolution trigger strategies.

    Evolution triggers determine when the system should run evolution operations
    like refining low-performance memories, deprecating failed ones, etc.
    """

    @abstractmethod
    def should_trigger(self, stats: SystemStats) -> bool:
        """Determine if evolution should be triggered.

        Args:
            stats: Current system statistics

        Returns:
            True if evolution should be triggered
        """
        pass


class BatchEvolutionHook(EvolutionTriggerHook):
    """Trigger evolution after every N remember operations.

    Use case: Regular batch processing for consistent evolution.

    Example:
        >>> hook = BatchEvolutionHook(batch_size=50)
        >>> if hook.should_trigger(stats):
        ...     system.evolve()
    """

    def __init__(self, batch_size: int = 50):
        """Initialize batch evolution hook.

        Args:
            batch_size: Number of remembers between evolution triggers
        """
        self.batch_size = batch_size
        self._last_trigger_count = 0

    def should_trigger(self, stats: SystemStats) -> bool:
        """Trigger every batch_size remembers.

        Args:
            stats: Current system statistics

        Returns:
            True if enough remembers have accumulated
        """
        if stats.remember_count - self._last_trigger_count >= self.batch_size:
            self._last_trigger_count = stats.remember_count
            return True
        return False

    def reset(self) -> None:
        """Reset the trigger counter."""
        self._last_trigger_count = 0


class TimeBasedHook(EvolutionTriggerHook):
    """Trigger evolution at regular time intervals.

    Use case: Scheduled maintenance for predictable evolution.

    Example:
        >>> hook = TimeBasedHook(interval_hours=24)  # Daily evolution
        >>> if hook.should_trigger(stats):
        ...     system.evolve()
    """

    def __init__(self, interval_hours: float = 24.0):
        """Initialize time-based evolution hook.

        Args:
            interval_hours: Hours between evolution triggers
        """
        self.interval = timedelta(hours=interval_hours)

    def should_trigger(self, stats: SystemStats) -> bool:
        """Trigger if enough time has passed since last evolution.

        Args:
            stats: Current system statistics

        Returns:
            True if enough time has passed
        """
        if stats.last_evolution_at is None:
            return True

        now = datetime.now(timezone.utc)

        # Handle timezone-naive last_evolution_at
        last_evolution = stats.last_evolution_at
        if last_evolution.tzinfo is None:
            last_evolution = last_evolution.replace(tzinfo=timezone.utc)

        return now - last_evolution >= self.interval


class ThresholdHook(EvolutionTriggerHook):
    """Trigger evolution when pending work exceeds a threshold.

    Use case: Demand-driven evolution for responsive systems.

    The "pending work" is measured as:
    - New memories since last evolution
    - Usage records since last evolution

    Example:
        >>> hook = ThresholdHook(memory_threshold=100, usage_threshold=500)
        >>> if hook.should_trigger(stats):
        ...     system.evolve()
    """

    def __init__(
        self,
        memory_threshold: int = 100,
        usage_threshold: int = 500,
    ):
        """Initialize threshold-based evolution hook.

        Args:
            memory_threshold: Trigger when new memories exceed this
            usage_threshold: Trigger when usage records exceed this
        """
        self.memory_threshold = memory_threshold
        self.usage_threshold = usage_threshold
        self._last_memory_count = 0
        self._last_usage_count = 0

    def should_trigger(self, stats: SystemStats) -> bool:
        """Trigger if memory or usage thresholds are exceeded.

        Args:
            stats: Current system statistics

        Returns:
            True if any threshold is exceeded
        """
        new_memories = stats.total_memories - self._last_memory_count
        new_usage = stats.total_usage - self._last_usage_count

        if new_memories >= self.memory_threshold or new_usage >= self.usage_threshold:
            self._last_memory_count = stats.total_memories
            self._last_usage_count = stats.total_usage
            return True

        return False

    def reset(self) -> None:
        """Reset the threshold counters."""
        self._last_memory_count = 0
        self._last_usage_count = 0


class CompositeEvolutionHook(EvolutionTriggerHook):
    """Combine multiple evolution hooks with OR/AND logic.

    Use case: Complex trigger conditions.

    Example:
        >>> # Trigger if either time-based OR batch-based condition is met
        >>> hook = CompositeEvolutionHook(
        ...     hooks=[TimeBasedHook(24), BatchEvolutionHook(50)],
        ...     mode="any"
        ... )
        >>> if hook.should_trigger(stats):
        ...     system.evolve()
    """

    def __init__(
        self,
        hooks: list[EvolutionTriggerHook],
        mode: str = "any",  # "any" (OR) or "all" (AND)
    ):
        """Initialize composite evolution hook.

        Args:
            hooks: List of hooks to combine
            mode: "any" for OR logic, "all" for AND logic
        """
        self.hooks = hooks
        self.mode = mode

        if mode not in ("any", "all"):
            raise ValueError(f"Invalid mode: {mode}. Use 'any' or 'all'.")

    def should_trigger(self, stats: SystemStats) -> bool:
        """Trigger based on combined hook conditions.

        Args:
            stats: Current system statistics

        Returns:
            True if trigger conditions are met
        """
        if self.mode == "any":
            return any(hook.should_trigger(stats) for hook in self.hooks)
        else:
            return all(hook.should_trigger(stats) for hook in self.hooks)


class QualityBasedHook(EvolutionTriggerHook):
    """Trigger evolution when system quality metrics degrade.

    Use case: Reactive evolution when performance drops.

    Example:
        >>> hook = QualityBasedHook(min_success_rate=0.7)
        >>> if hook.should_trigger(stats):
        ...     system.evolve()  # Refine low-performing memories
    """

    def __init__(
        self,
        min_success_rate: float = 0.7,
        sample_size: int = 100,
    ):
        """Initialize quality-based evolution hook.

        Args:
            min_success_rate: Trigger if avg success rate drops below this
            sample_size: Minimum usage records to consider
        """
        self.min_success_rate = min_success_rate
        self.sample_size = sample_size
        self._recent_successes = 0
        self._recent_failures = 0

    def record_outcome(self, outcome: str) -> None:
        """Record a usage outcome for quality tracking.

        Args:
            outcome: "success" or "failure"
        """
        if outcome == "success":
            self._recent_successes += 1
        elif outcome == "failure":
            self._recent_failures += 1

    def should_trigger(self, stats: SystemStats) -> bool:
        """Trigger if success rate drops below threshold.

        Args:
            stats: Current system statistics (not directly used)

        Returns:
            True if quality threshold is not met
        """
        _ = stats  # Required by interface but not used; quality tracked via record_outcome()
        total = self._recent_successes + self._recent_failures

        if total < self.sample_size:
            return False  # Not enough data

        success_rate = self._recent_successes / total
        return success_rate < self.min_success_rate

    def reset(self) -> None:
        """Reset quality tracking counters."""
        self._recent_successes = 0
        self._recent_failures = 0
