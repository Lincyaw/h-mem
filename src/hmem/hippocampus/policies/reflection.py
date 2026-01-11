"""Reflection policies for triggering deep reflection."""

from abc import ABC, abstractmethod
from datetime import datetime

from hmem.models import ReflectionContext


class ReflectionPolicy(ABC):
    """Abstract policy for triggering reflection.

    Different policies implement different time-scale strategies:
    - Threshold-based: Reflect after N similar events
    - Time-based: Reflect daily/weekly
    - Multi-scale: Combine multiple triggers
    """

    @abstractmethod
    def should_reflect(self, context: ReflectionContext) -> bool:
        """Determine if reflection should trigger.

        Args:
            context: Current system context

        Returns:
            True if reflection should be triggered
        """
        pass


class MultiScalePolicy(ReflectionPolicy):
    """Multi-timescale reflection policy (default).

    Triggers reflection at multiple levels:
    - Immediate: After 3 similar events (fast feedback loop)
    - Daily: Every 24 hours (consolidate daily patterns)
    - Weekly: Every 7 days (extract long-term principles)

    Configuration:
        immediate_threshold: 3 events
        daily_interval: 24 hours
        weekly_interval: 7 days
    """

    def __init__(
        self,
        immediate_threshold: int = 3,
        daily_interval: int = 24,
        weekly_interval: int = 168,
    ) -> None:
        """Initialize multi-scale policy.

        Args:
            immediate_threshold: Event count trigger
            daily_interval: Hours between daily reflections
            weekly_interval: Hours between weekly reflections
        """
        self.immediate_threshold = immediate_threshold
        self.daily_interval = daily_interval
        self.weekly_interval = weekly_interval

    def should_reflect(self, context: ReflectionContext) -> bool:
        """Check all trigger conditions.

        Args:
            context: Current context

        Returns:
            True if any trigger fires
        """
        # Immediate trigger: event count (use episode_count from ReflectionContext)
        if context.episode_count >= self.immediate_threshold:
            return True

        # Time-based triggers
        if context.last_reflection_time:
            hours_since = (
                datetime.now() - context.last_reflection_time
            ).total_seconds() / 3600

            if hours_since >= self.weekly_interval:
                return True
            if hours_since >= self.daily_interval:
                return True

        return False
