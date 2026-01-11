"""Retrieval ranking strategies for memory system.

Implements pluggable ranking algorithms to sort retrieved memories
by relevance, combining multiple signals (similarity, recency, importance, outcome).
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from hmem.models import Memory


class RetrievalRanker(ABC):
    """Abstract base class for retrieval ranking strategies."""

    @abstractmethod
    def rank(self, candidates: list[Memory], query: str) -> list[Memory]:
        """Rank candidate memories by relevance.

        Args:
            candidates: List of candidate memories to rank
            query: Original search query for context

        Returns:
            Sorted list of memories, highest relevance first
        """
        pass


class HybridRanker(RetrievalRanker):
    """Hybrid ranking combining similarity, recency, importance, and outcome.

    Default weights based on information retrieval best practices:
    - similarity_weight: 0.5 (primary signal)
    - recency_weight: 0.15 (temporal decay)
    - importance_weight: 0.15 (access frequency)
    - outcome_weight: 0.2 (success/failure bias)

    Weights should sum to 1.0 for interpretable scores.
    """

    def __init__(
        self,
        similarity_weight: float = 0.5,
        recency_weight: float = 0.15,
        importance_weight: float = 0.15,
        outcome_weight: float = 0.2,
        importance_normalizer: float = 100.0,
        recency_halflife_days: float = 30.0,
        success_boost: float = 1.0,
        failure_penalty: float = 0.3,
    ):
        """Initialize hybrid ranker with configurable weights.

        Args:
            similarity_weight: Weight for similarity score (0.4-0.6 recommended)
            recency_weight: Weight for temporal recency (0.1-0.2 recommended)
            importance_weight: Weight for access importance (0.1-0.2 recommended)
            outcome_weight: Weight for outcome (success/failure) signal
            importance_normalizer: Denominator for normalizing access counts
            recency_halflife_days: Days for recency score to decay to 0.5
            success_boost: Score for successful outcomes (0-1)
            failure_penalty: Score for failed outcomes (0-1, lower = more penalty)

        Raises:
            ValueError: If weights don't sum to approximately 1.0
        """
        total_weight = (
            similarity_weight + recency_weight + importance_weight + outcome_weight
        )
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(
                f"Weights must sum to 1.0, got {total_weight:.3f}. "
                f"Adjust weights to maintain interpretable scores."
            )

        self.similarity_weight = similarity_weight
        self.recency_weight = recency_weight
        self.importance_weight = importance_weight
        self.outcome_weight = outcome_weight
        self.importance_normalizer = importance_normalizer
        self.recency_halflife_days = recency_halflife_days
        self.success_boost = success_boost
        self.failure_penalty = failure_penalty

    def rank(self, candidates: list[Memory], query: str) -> list[Memory]:
        """Rank memories using hybrid scoring.

        Args:
            candidates: Candidate memories with initial similarity scores
            query: Search query (currently unused, reserved for query-specific ranking)

        Returns:
            Ranked memories with updated composite scores
        """
        now = datetime.now(timezone.utc)

        for memory in candidates:
            # Component 1: Similarity score (already set by retrieval)
            similarity_score = memory.score

            # Component 2: Recency score (exponential decay)
            recency_score = self._calculate_recency(memory.timestamp, now)

            # Component 3: Importance score (normalized access count)
            access_count = memory.metadata.get("access_count", 0)
            importance_score = min(1.0, access_count / self.importance_normalizer)

            # Component 4: Outcome score (boost success, penalize failure)
            outcome_score = self._calculate_outcome_score(memory)

            # Composite score
            memory.score = (
                self.similarity_weight * similarity_score
                + self.recency_weight * recency_score
                + self.importance_weight * importance_score
                + self.outcome_weight * outcome_score
            )

        return sorted(candidates, key=lambda m: m.score, reverse=True)

    def _calculate_outcome_score(self, memory: Memory) -> float:
        """Calculate outcome-based score.

        Boosts successful memories and penalizes failed ones.
        Neutral (unknown/pending) outcomes get a middle score.

        Args:
            memory: Memory to score

        Returns:
            Outcome score in [0, 1]
        """
        # Check content for outcome indicators
        content_lower = memory.content.lower()

        # Check metadata for explicit outcome
        outcome = memory.metadata.get("outcome", "unknown")

        # Detect outcome from content if not in metadata
        if outcome == "unknown":
            if any(
                kw in content_lower
                for kw in ["success", "succeeded", "worked", "successfully"]
            ):
                outcome = "success"
            elif any(
                kw in content_lower for kw in ["fail", "failed", "error", "failure"]
            ):
                outcome = "failure"

        if outcome == "success":
            return self.success_boost
        elif outcome == "failure":
            return self.failure_penalty
        else:
            # Neutral/unknown outcomes get middle score
            return 0.6

    def _calculate_recency(self, timestamp: datetime, now: datetime) -> float:
        """Calculate recency score using exponential decay.

        Args:
            timestamp: When the memory was created
            now: Current time

        Returns:
            Recency score in [0, 1], where 1.0 = just created
        """
        # Ensure both timestamps have timezone info (or neither do)
        if timestamp.tzinfo is None and now.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        elif timestamp.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        age_days = (now - timestamp).total_seconds() / 86400.0

        # Exponential decay: score = 0.5^(age/halflife)
        decay_factor = 2 ** (-age_days / self.recency_halflife_days)

        return max(0.0, min(1.0, decay_factor))
