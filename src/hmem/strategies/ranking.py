"""Retrieval ranking strategies for memory system.

Implements pluggable ranking algorithms to sort retrieved memories
by relevance, combining multiple signals (similarity, recency, importance, quality, exploration).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from hmem.constants import (
    Q_LEARNING_DEFAULT_SIMILARITY_WEIGHT,
    Q_LEARNING_DEFAULT_Q_WEIGHT,
    Q_LEARNING_DEFAULT_FRESHNESS_WEIGHT,
    Q_LEARNING_DEFAULT_FRESHNESS_HALFLIFE_DAYS,
    TYPE_FRESHNESS_WEIGHTS,
)
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


class QValueRanker(RetrievalRanker):
    """MemRL-inspired ranking with Q-value learning.

    Uses three orthogonal signals:
    - Similarity: Semantic relevance (from vector search)
    - Q-value: Learned utility (from feedback loop)
    - Freshness: Information timeliness (exponential decay)

    Formula: score = w_s × similarity + w_q × q_value + w_f × freshness

    Design rationale (from MemRL paper):
    - Q-value directly learns "usefulness" through Monte Carlo updates
    - Replaces redundant signals (recency, importance, outcome)
    - Three signals are orthogonal: semantic, learned, temporal
    """

    def __init__(
        self,
        similarity_weight: float = Q_LEARNING_DEFAULT_SIMILARITY_WEIGHT,
        q_weight: float = Q_LEARNING_DEFAULT_Q_WEIGHT,
        freshness_weight: float = Q_LEARNING_DEFAULT_FRESHNESS_WEIGHT,
        freshness_halflife_days: float = Q_LEARNING_DEFAULT_FRESHNESS_HALFLIFE_DAYS,
    ):
        """Initialize Q-value ranker.

        Args:
            similarity_weight: Weight for similarity score (0.5 recommended)
            q_weight: Weight for Q-value (0.35 recommended)
            freshness_weight: Weight for freshness (0.15 recommended)
            freshness_halflife_days: Days for freshness to decay to 0.5

        Raises:
            ValueError: If weights don't sum to approximately 1.0
        """
        total_weight = similarity_weight + q_weight + freshness_weight
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(
                f"Weights must sum to 1.0, got {total_weight:.3f}. "
                f"Adjust weights to maintain interpretable scores."
            )

        self.similarity_weight = similarity_weight
        self.q_weight = q_weight
        self.freshness_weight = freshness_weight
        self.freshness_halflife_days = freshness_halflife_days

    def _calculate_freshness(self, timestamp: datetime, now: datetime) -> float:
        """Calculate freshness score using exponential decay.

        Formula: freshness = 0.5^(age_days / halflife)

        Args:
            timestamp: When the memory was created
            now: Current time

        Returns:
            Freshness score in [0, 1], where 1.0 = just created
        """
        # Ensure both timestamps have timezone info
        if timestamp.tzinfo is None and now.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        elif timestamp.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        age_days = (now - timestamp).total_seconds() / 86400.0
        decay_factor = 2 ** (-age_days / self.freshness_halflife_days)

        return max(0.0, min(1.0, decay_factor))

    def _get_q_value(self, memory: Memory) -> float:
        """Get Q-value from memory's IndexProfile.

        Args:
            memory: Memory with optional index_profile

        Returns:
            Q-value in [0, 1], default 0.5 (neutral)
        """
        if memory.index_profile is not None:
            return memory.index_profile.q_value
        return 0.5  # Neutral default

    def _calculate_score(self, memory: Memory, now: datetime) -> float:
        """Calculate composite score using three orthogonal signals.

        Type-aware freshness: Principle (L3) gets no freshness decay,
        while Episodic (L1) gets full decay. This prevents "wisdom"
        from being penalized for age.

        Args:
            memory: Memory to score
            now: Current time

        Returns:
            Composite score in [0, 1]
        """
        # Signal 1: Similarity (already computed by vector search)
        similarity = memory.score

        # Signal 2: Q-value (learned utility)
        q_value = self._get_q_value(memory)

        # Signal 3: Freshness (temporal decay) - type-aware
        freshness = self._calculate_freshness(memory.timestamp, now)

        # Type-aware freshness weight adjustment
        # Principle: no freshness decay (type_factor=0)
        # Episodic: full freshness decay (type_factor=1)
        type_factor = TYPE_FRESHNESS_WEIGHTS.get(memory.source, 1.0)
        effective_freshness_weight = self.freshness_weight * type_factor

        # Redistribute unused freshness weight to other signals
        # This ensures weights still sum to 1.0
        remaining_weight = self.freshness_weight * (1 - type_factor)
        effective_sim_weight = self.similarity_weight + remaining_weight * 0.6
        effective_q_weight = self.q_weight + remaining_weight * 0.4

        return (
            effective_sim_weight * similarity
            + effective_q_weight * q_value
            + effective_freshness_weight * freshness
        )

    def rank(self, candidates: list[Memory], query: str) -> list[Memory]:
        """Rank memories using Q-value based scoring.

        Args:
            candidates: Candidate memories with initial similarity scores
            query: Search query (reserved for future query-specific ranking)

        Returns:
            Ranked memories with updated composite scores
        """
        now = datetime.now(timezone.utc)

        for memory in candidates:
            memory.score = self._calculate_score(memory, now)

        return sorted(candidates, key=lambda m: m.score, reverse=True)
