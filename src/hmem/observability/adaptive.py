"""Adaptive threshold management for retrieval.

Implements meta-cognitive mechanisms from design.md:
- Dynamic threshold adjustment based on feedback
- Per-topic threshold tracking
- Effectiveness measurement
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import structlog

logger = structlog.get_logger()


@dataclass
class ThresholdFeedback:
    """Feedback record for threshold adjustment."""

    topic: str
    threshold_used: float
    accepted: bool
    result_count: int
    timestamp: datetime = field(default_factory=datetime.now)


class AdaptiveThresholdManager:
    """Dynamically adjusts retrieval thresholds based on feedback.

    Problem: Fixed threshold (e.g., 0.5) causes either:
    - High threshold → missed relevant results
    - Low threshold → too much noise

    Solution: Track retrieval effectiveness and adjust threshold.

    Feedback signals:
    - User accepts result → lower threshold OK
    - User rejects all results → threshold too high
    - User sees too many results → threshold too low

    Example:
        >>> manager = AdaptiveThresholdManager(initial=0.5)
        >>> threshold = manager.get_threshold("web_scraping")
        >>> manager.record_feedback("web_scraping", accepted=True)
        >>> # Threshold gradually decreases if results consistently accepted
    """

    def __init__(
        self,
        initial_threshold: float = 0.5,
        min_threshold: float = 0.2,
        max_threshold: float = 0.9,
        adjustment_rate: float = 0.02,
        history_size: int = 100,
    ) -> None:
        """Initialize adaptive manager.

        Args:
            initial_threshold: Starting threshold for new topics
            min_threshold: Minimum allowed threshold
            max_threshold: Maximum allowed threshold
            adjustment_rate: How much to adjust per feedback
            history_size: Number of feedback records to retain
        """
        self.initial_threshold = initial_threshold
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.adjustment_rate = adjustment_rate
        self.history_size = history_size

        self._thresholds: dict[str, float] = {}
        self._feedback_history: dict[str, deque[ThresholdFeedback]] = {}
        self._accept_counts: dict[str, int] = {}
        self._reject_counts: dict[str, int] = {}

    def get_threshold(self, topic: str) -> float:
        """Get current threshold for topic.

        Args:
            topic: Query topic (can be hashed from query)

        Returns:
            Current threshold
        """
        return self._thresholds.get(topic, self.initial_threshold)

    def record_feedback(
        self,
        topic: str,
        accepted: bool,
        result_count: int = 0,
        threshold_used: float | None = None,
    ) -> float:
        """Record user feedback and adjust threshold.

        Args:
            topic: Query topic
            accepted: Whether user accepted results
            result_count: Number of results shown
            threshold_used: Threshold that was used (for tracking)

        Returns:
            New threshold after adjustment
        """
        current = self.get_threshold(topic)
        threshold_used = threshold_used or current

        # Create feedback record
        feedback = ThresholdFeedback(
            topic=topic,
            threshold_used=threshold_used,
            accepted=accepted,
            result_count=result_count,
        )

        # Store in history
        if topic not in self._feedback_history:
            self._feedback_history[topic] = deque(maxlen=self.history_size)
        self._feedback_history[topic].append(feedback)

        # Update counts
        if topic not in self._accept_counts:
            self._accept_counts[topic] = 0
            self._reject_counts[topic] = 0

        if accepted:
            self._accept_counts[topic] += 1
        else:
            self._reject_counts[topic] += 1

        # Calculate new threshold
        new_threshold = self._calculate_adjustment(topic, accepted, result_count)
        self._thresholds[topic] = new_threshold

        logger.debug(
            "threshold_adjusted",
            topic=topic,
            old_threshold=current,
            new_threshold=new_threshold,
            accepted=accepted,
        )

        return new_threshold

    def _calculate_adjustment(
        self, topic: str, accepted: bool, result_count: int
    ) -> float:
        """Calculate threshold adjustment.

        Args:
            topic: Query topic
            accepted: Whether results were accepted
            result_count: Number of results

        Returns:
            New threshold value
        """
        current = self.get_threshold(topic)

        if accepted:
            # Results accepted - threshold can go lower
            # But if many results, might need higher threshold
            if result_count > 10:
                # Too many results - slightly increase threshold
                adjustment = self.adjustment_rate * 0.5
            else:
                # Good number of results - decrease threshold
                adjustment = -self.adjustment_rate
        else:
            # Results rejected - threshold too high (missing relevant)
            # or too low (too much noise)
            if result_count == 0:
                # No results - threshold too high
                adjustment = -self.adjustment_rate * 2
            elif result_count > 10:
                # Too many irrelevant results - threshold too low
                adjustment = self.adjustment_rate * 2
            else:
                # Some results but rejected - slightly lower
                adjustment = -self.adjustment_rate

        new_threshold = current + adjustment
        return max(self.min_threshold, min(self.max_threshold, new_threshold))

    def get_effectiveness(self, topic: str) -> float:
        """Get acceptance rate for topic.

        Args:
            topic: Query topic

        Returns:
            Acceptance rate (0.0 to 1.0)
        """
        accepts = self._accept_counts.get(topic, 0)
        rejects = self._reject_counts.get(topic, 0)
        total = accepts + rejects

        if total == 0:
            return 0.5  # No data - neutral

        return accepts / total

    def get_stats(self) -> dict[str, Any]:
        """Get manager statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "topics_tracked": len(self._thresholds),
            "total_feedback": sum(len(h) for h in self._feedback_history.values()),
            "thresholds": dict(self._thresholds),
            "effectiveness": {
                topic: self.get_effectiveness(topic) for topic in self._thresholds
            },
        }

    def reset_topic(self, topic: str) -> None:
        """Reset threshold for topic.

        Args:
            topic: Topic to reset
        """
        self._thresholds.pop(topic, None)
        self._feedback_history.pop(topic, None)
        self._accept_counts.pop(topic, None)
        self._reject_counts.pop(topic, None)

    def reset_all(self) -> None:
        """Reset all thresholds."""
        self._thresholds.clear()
        self._feedback_history.clear()
        self._accept_counts.clear()
        self._reject_counts.clear()
