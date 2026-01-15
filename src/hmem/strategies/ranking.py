"""Retrieval ranking strategies for memory system.

Implements pluggable ranking algorithms to sort retrieved memories
by relevance, combining multiple signals (similarity, recency, importance, quality, exploration).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from hmem.constants import (
    RANKING_DEFAULT_SIMILARITY_WEIGHT,
    RANKING_DEFAULT_RECENCY_WEIGHT,
    RANKING_DEFAULT_IMPORTANCE_WEIGHT,
    RANKING_DEFAULT_OUTCOME_WEIGHT,
    RANKING_DEFAULT_QUALITY_WEIGHT,
    RANKING_DEFAULT_EXPLORATION_WEIGHT,
    RANKING_DEFAULT_IMPORTANCE_NORMALIZER,
    RANKING_DEFAULT_RECENCY_HALFLIFE_DAYS,
    RANKING_DEFAULT_SUCCESS_BOOST,
    RANKING_DEFAULT_FAILURE_PENALTY,
    RANKING_DEFAULT_INITIAL_EXPLORATION_RATE,
    RANKING_DEFAULT_MIN_EXPLORATION_RATE,
    Q_LEARNING_DEFAULT_SIMILARITY_WEIGHT,
    Q_LEARNING_DEFAULT_Q_WEIGHT,
    Q_LEARNING_DEFAULT_FRESHNESS_WEIGHT,
    Q_LEARNING_DEFAULT_FRESHNESS_HALFLIFE_DAYS,
)
from hmem.models import Memory

from hmem.utils.outcome_detector import OutcomeDetector


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
        similarity_weight: float = RANKING_DEFAULT_SIMILARITY_WEIGHT,
        recency_weight: float = RANKING_DEFAULT_RECENCY_WEIGHT,
        importance_weight: float = RANKING_DEFAULT_IMPORTANCE_WEIGHT,
        outcome_weight: float = RANKING_DEFAULT_OUTCOME_WEIGHT,
        importance_normalizer: float = RANKING_DEFAULT_IMPORTANCE_NORMALIZER,
        recency_halflife_days: float = RANKING_DEFAULT_RECENCY_HALFLIFE_DAYS,
        success_boost: float = RANKING_DEFAULT_SUCCESS_BOOST,
        failure_penalty: float = RANKING_DEFAULT_FAILURE_PENALTY,
        outcome_detector: OutcomeDetector | None = None,
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
            outcome_detector: Optional OutcomeDetector for LLM-based detection

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
        self._outcome_detector = outcome_detector

    def _calculate_memory_score(self, memory: Memory, now: datetime) -> float:
        """Calculate composite score for a single memory."""
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
        return (
            self.similarity_weight * similarity_score
            + self.recency_weight * recency_score
            + self.importance_weight * importance_score
            + self.outcome_weight * outcome_score
        )

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
            memory.score = self._calculate_memory_score(memory, now)

        return sorted(candidates, key=lambda m: m.score, reverse=True)

    def _detect_outcome_from_content(self, content: str, current_outcome: str) -> str:
        """Detect outcome from content using OutcomeDetector or keyword fallback.

        Args:
            content: Memory content to analyze
            current_outcome: Pre-existing outcome if known

        Returns:
            Detected outcome: "success", "failure", or "unknown"
        """
        # Return existing outcome if already known
        if current_outcome in ("success", "failure"):
            return current_outcome

        # Use OutcomeDetector if available
        if self._outcome_detector is not None:
            return self._outcome_detector.detect(content, current_outcome)

        # Fallback to keyword matching
        return self._detect_outcome_keywords(content)

    def _detect_outcome_keywords(self, content: str) -> str:
        """Fallback keyword-based outcome detection.

        Args:
            content: Content to analyze

        Returns:
            Detected outcome based on keywords
        """
        content_lower = content.lower()

        success_keywords = [
            "success",
            "succeeded",
            "successful",
            "worked",
            "works",
            "working",
            "fixed",
            "resolved",
            "solved",
            "completed",
            "done",
            "finished",
        ]
        failure_keywords = [
            "fail",
            "failed",
            "failure",
            "error",
            "exception",
            "broken",
            "crash",
            "bug",
            "issue",
            "problem",
            "wrong",
        ]

        if any(kw in content_lower for kw in success_keywords):
            return "success"
        elif any(kw in content_lower for kw in failure_keywords):
            return "failure"

        return "unknown"

    def _calculate_outcome_score(self, memory: Memory) -> float:
        """Calculate outcome-based score.

        Boosts successful memories and penalizes failed ones.
        Neutral (unknown/pending) outcomes get a middle score.

        Args:
            memory: Memory to score

        Returns:
            Outcome score in [0, 1]
        """
        # Check metadata for explicit outcome, fallback to content detection
        outcome = self._detect_outcome_from_content(
            memory.content, memory.metadata.get("outcome", "unknown")
        )

        return {
            "success": self.success_boost,
            "failure": self.failure_penalty,
        }.get(outcome, 0.6)  # Default middle score for unknown/neutral

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


class HybridRankerWithExploration(RetrievalRanker):
    """Hybrid ranking with quality score and exploration bonus.

    Implements the ranking formula from interfaces.md:
    score = w1*similarity + w2*recency + w3*importance + w4*quality_score + w5*exploration_bonus

    Default weights based on documentation:
    - similarity_weight: 0.4 (primary signal)
    - recency_weight: 0.15 (temporal decay)
    - importance_weight: 0.15 (access frequency)
    - quality_weight: 0.2 (from IndexProfile quality_score)
    - exploration_weight: 0.1 (favor low-usage memories)

    Exploration mechanism:
    - Adaptive rate decays as knowledge base matures
    - Low-usage memories get higher exploration bonus
    - Exploration bonus: 1.0 / (1 + log(1 + usage_count))
    """

    def __init__(
        self,
        similarity_weight: float = RANKING_DEFAULT_SIMILARITY_WEIGHT,
        recency_weight: float = RANKING_DEFAULT_RECENCY_WEIGHT,
        importance_weight: float = RANKING_DEFAULT_IMPORTANCE_WEIGHT,
        quality_weight: float = RANKING_DEFAULT_QUALITY_WEIGHT,
        exploration_weight: float = RANKING_DEFAULT_EXPLORATION_WEIGHT,
        importance_normalizer: float = RANKING_DEFAULT_IMPORTANCE_NORMALIZER,
        recency_halflife_days: float = RANKING_DEFAULT_RECENCY_HALFLIFE_DAYS,
        initial_exploration_rate: float = RANKING_DEFAULT_INITIAL_EXPLORATION_RATE,
        min_exploration_rate: float = RANKING_DEFAULT_MIN_EXPLORATION_RATE,
    ):
        """Initialize hybrid ranker with exploration support.

        Args:
            similarity_weight: Weight for similarity score (0.4 recommended)
            recency_weight: Weight for temporal recency (0.15 recommended)
            importance_weight: Weight for access importance (0.15 recommended)
            quality_weight: Weight for IndexProfile quality_score (0.2 recommended)
            exploration_weight: Weight for exploration bonus (0.1 recommended)
            importance_normalizer: Denominator for normalizing access counts
            recency_halflife_days: Days for recency score to decay to 0.5
            initial_exploration_rate: Starting exploration rate
            min_exploration_rate: Minimum exploration rate

        Raises:
            ValueError: If weights don't sum to approximately 1.0
        """
        total_weight = (
            similarity_weight
            + recency_weight
            + importance_weight
            + quality_weight
            + exploration_weight
        )
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(
                f"Weights must sum to 1.0, got {total_weight:.3f}. "
                f"Adjust weights to maintain interpretable scores."
            )

        self.similarity_weight = similarity_weight
        self.recency_weight = recency_weight
        self.importance_weight = importance_weight
        self.quality_weight = quality_weight
        self.exploration_weight = exploration_weight
        self.importance_normalizer = importance_normalizer
        self.recency_halflife_days = recency_halflife_days
        self.initial_exploration_rate = initial_exploration_rate
        self.min_exploration_rate = min_exploration_rate
        self._current_exploration_rate = initial_exploration_rate

    def _calculate_memory_score(self, memory: Memory, now: datetime) -> float:
        """Calculate composite score for a single memory using the 5-component formula."""
        # Component 1: Similarity score (already set by retrieval)
        similarity_score = memory.score

        # Component 2: Recency score (exponential decay)
        recency_score = self._calculate_recency(memory.timestamp, now)

        # Component 3: Importance score (normalized access count)
        access_count = memory.metadata.get("access_count", 0)
        importance_score = min(1.0, access_count / self.importance_normalizer)

        # Component 4: Quality score from IndexProfile
        quality_score = self._calculate_quality_score(memory)

        # Component 5: Exploration bonus for low-usage memories
        exploration_bonus = self._calculate_exploration_bonus(memory)

        # Composite score
        return (
            self.similarity_weight * similarity_score
            + self.recency_weight * recency_score
            + self.importance_weight * importance_score
            + self.quality_weight * quality_score
            + self.exploration_weight * exploration_bonus
        )

    def _calculate_quality_score(self, memory: Memory) -> float:
        """Calculate quality score from IndexProfile.

        Args:
            memory: Memory with optional index_profile

        Returns:
            Quality score in [0, 1]
        """
        if memory.index_profile is not None:
            return memory.index_profile.quality_score

        # Fallback: use metadata success_rate if available
        success_rate = memory.metadata.get("success_rate", 0.5)
        return float(success_rate)

    def _calculate_exploration_bonus(self, memory: Memory) -> float:
        """Calculate exploration bonus for low-usage memories.

        Formula: 1.0 / (1 + log(1 + usage_count))

        This gives higher bonus to memories that haven't been used much,
        encouraging exploration of the knowledge base.

        Args:
            memory: Memory with optional index_profile

        Returns:
            Exploration bonus in [0, 1]
        """
        # Get usage count from index_profile or metadata
        usage_count = 0
        if memory.index_profile is not None:
            usage_count = memory.index_profile.usage_count
        else:
            usage_count = memory.metadata.get("usage_count", 0)

        # Formula: 1.0 / (1 + log(1 + usage_count))
        # - New memories (usage_count=0): bonus = 1.0
        # - Moderately used (usage_count=10): bonus ≈ 0.29
        # - Heavily used (usage_count=100): bonus ≈ 0.18
        bonus = 1.0 / (1.0 + math.log(1.0 + usage_count))

        # Apply current exploration rate
        return bonus * self._current_exploration_rate

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

    def rank(self, candidates: list[Memory], query: str) -> list[Memory]:
        """Rank memories using hybrid scoring with exploration.

        Args:
            candidates: Candidate memories with initial similarity scores
            query: Search query (currently unused, reserved for query-specific ranking)

        Returns:
            Ranked memories with updated composite scores
        """
        now = datetime.now(timezone.utc)

        for memory in candidates:
            memory.score = self._calculate_memory_score(memory, now)

        return sorted(candidates, key=lambda m: m.score, reverse=True)

    def decay_exploration_rate(self, total_memories: int) -> None:
        """Decay exploration rate as knowledge base matures.

        Args:
            total_memories: Total number of memories in the system
        """
        # Decay exploration rate based on knowledge base size
        # Rate decays from initial to min as memories grow
        if total_memories > 0:
            decay = 1.0 / (1.0 + math.log(1.0 + total_memories / 100.0))
            self._current_exploration_rate = max(
                self.min_exploration_rate,
                self.initial_exploration_rate * decay,
            )

    @property
    def current_exploration_rate(self) -> float:
        """Get current exploration rate."""
        return self._current_exploration_rate


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

        # Signal 3: Freshness (temporal decay)
        freshness = self._calculate_freshness(memory.timestamp, now)

        return (
            self.similarity_weight * similarity
            + self.q_weight * q_value
            + self.freshness_weight * freshness
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
