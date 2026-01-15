"""Unit tests for Q-value learning module (MemRL-inspired).

Tests cover:
1. QValueUpdater - Monte Carlo Q-value updates
2. QValueRanker - Three-signal ranking
3. Refinement decision logic
4. IndexProfile Q-value properties
"""

from datetime import datetime, timedelta, timezone

import pytest

from hmem.models import IndexProfile, Memory
from hmem.strategies.q_learning import (
    QValueUpdater,
    create_initial_profile,
    migrate_legacy_profile,
)
from hmem.strategies.ranking import QValueRanker
from hmem.strategies.refine import (
    RefineAction,
    create_refined_profile,
    determine_refine_action,
    find_refine_candidates,
)


class TestQValueUpdater:
    """Tests for QValueUpdater class."""

    def test_init_valid_alpha(self):
        """Should accept valid alpha values."""
        updater = QValueUpdater(alpha=0.1)
        assert updater.alpha == 0.1

        updater = QValueUpdater(alpha=0.5)
        assert updater.alpha == 0.5

    def test_init_invalid_alpha(self):
        """Should reject invalid alpha values."""
        with pytest.raises(ValueError):
            QValueUpdater(alpha=0.0)

        with pytest.raises(ValueError):
            QValueUpdater(alpha=1.5)

        with pytest.raises(ValueError):
            QValueUpdater(alpha=-0.1)

    def test_update_increases_q_on_success(self):
        """Q-value should increase when reward=1.0."""
        updater = QValueUpdater(alpha=0.1)
        profile = IndexProfile(q_value=0.5, q_update_count=0)

        updater.update(profile, reward=1.0)

        # Q_new = 0.5 + 0.1 * (1.0 - 0.5) = 0.55
        assert profile.q_value == pytest.approx(0.55)
        assert profile.q_update_count == 1
        assert profile.last_used_at is not None

    def test_update_decreases_q_on_failure(self):
        """Q-value should decrease when reward=0.0."""
        updater = QValueUpdater(alpha=0.1)
        profile = IndexProfile(q_value=0.5, q_update_count=0)

        updater.update(profile, reward=0.0)

        # Q_new = 0.5 + 0.1 * (0.0 - 0.5) = 0.45
        assert profile.q_value == pytest.approx(0.45)
        assert profile.q_update_count == 1

    def test_update_neutral_on_unknown(self):
        """Q-value should stay same when reward=0.5."""
        updater = QValueUpdater(alpha=0.1)
        profile = IndexProfile(q_value=0.5, q_update_count=0)

        updater.update(profile, reward=0.5)

        # Q_new = 0.5 + 0.1 * (0.5 - 0.5) = 0.5
        assert profile.q_value == pytest.approx(0.5)
        assert profile.q_update_count == 1

    def test_update_invalid_reward(self):
        """Should reject invalid reward values."""
        updater = QValueUpdater(alpha=0.1)
        profile = IndexProfile(q_value=0.5, q_update_count=0)

        with pytest.raises(ValueError):
            updater.update(profile, reward=1.5)

        with pytest.raises(ValueError):
            updater.update(profile, reward=-0.1)

    def test_convergence_to_true_mean(self):
        """Q-value should converge toward expected reward over many updates."""
        updater = QValueUpdater(alpha=0.1)
        profile = IndexProfile(q_value=0.5, q_update_count=0)

        # Use deterministic sequence: 80% success rate (8 successes, 2 failures per 10)
        for _ in range(20):  # 20 cycles of 10 = 200 updates
            for _ in range(8):  # 8 successes
                updater.update(profile, reward=1.0)
            for _ in range(2):  # 2 failures
                updater.update(profile, reward=0.0)

        # Should converge toward 0.8 (order affects final value due to recency)
        assert 0.65 < profile.q_value < 0.90
        assert profile.q_update_count == 200

    def test_reward_from_outcome(self):
        """Should correctly map outcomes to rewards."""
        updater = QValueUpdater()

        assert updater.reward_from_outcome("success") == 1.0
        assert updater.reward_from_outcome("failure") == 0.0
        assert updater.reward_from_outcome("unknown") == 0.5

    def test_batch_update(self):
        """Should update multiple profiles."""
        updater = QValueUpdater(alpha=0.1)
        profiles = [
            IndexProfile(q_value=0.5, q_update_count=0),
            IndexProfile(q_value=0.6, q_update_count=5),
            IndexProfile(q_value=0.4, q_update_count=3),
        ]

        count = updater.batch_update(profiles, reward=1.0)

        assert count == 3
        assert all(p.q_value > 0.5 for p in profiles[:2])
        assert profiles[2].q_value > 0.4


class TestQValueRanker:
    """Tests for QValueRanker class."""

    def test_init_valid_weights(self):
        """Should accept weights that sum to 1.0."""
        ranker = QValueRanker(
            similarity_weight=0.5,
            q_weight=0.35,
            freshness_weight=0.15,
        )
        assert ranker.similarity_weight == 0.5
        assert ranker.q_weight == 0.35
        assert ranker.freshness_weight == 0.15

    def test_init_invalid_weights(self):
        """Should reject weights that don't sum to 1.0."""
        with pytest.raises(ValueError):
            QValueRanker(
                similarity_weight=0.5,
                q_weight=0.5,
                freshness_weight=0.5,
            )

    def test_high_q_value_ranks_higher(self):
        """Memories with higher Q-values should rank higher."""
        ranker = QValueRanker()
        now = datetime.now(timezone.utc)

        mem_high_q = Memory(
            id="mem_high",
            content="high q memory",
            score=0.8,
            source="semantic",
            timestamp=now,
            index_profile=IndexProfile(q_value=0.9, q_update_count=10),
        )
        mem_low_q = Memory(
            id="mem_low",
            content="low q memory",
            score=0.8,
            source="semantic",
            timestamp=now,
            index_profile=IndexProfile(q_value=0.1, q_update_count=10),
        )

        ranked = ranker.rank([mem_low_q, mem_high_q], "query")

        assert ranked[0].id == "mem_high"
        assert ranked[1].id == "mem_low"

    def test_freshness_decay(self):
        """Older memories should have lower freshness score."""
        ranker = QValueRanker(freshness_halflife_days=30.0)
        now = datetime.now(timezone.utc)

        fresh = ranker._calculate_freshness(now, now)
        old_30d = ranker._calculate_freshness(now - timedelta(days=30), now)
        old_60d = ranker._calculate_freshness(now - timedelta(days=60), now)

        assert fresh == pytest.approx(1.0)
        assert old_30d == pytest.approx(0.5, abs=0.01)
        assert old_60d == pytest.approx(0.25, abs=0.01)

    def test_default_q_value_for_no_profile(self):
        """Should use default Q=0.5 when no IndexProfile."""
        ranker = QValueRanker()
        now = datetime.now(timezone.utc)

        mem = Memory(
            id="mem_no_profile",
            content="no profile",
            score=0.8,
            source="semantic",
            timestamp=now,
            index_profile=None,
        )

        q_value = ranker._get_q_value(mem)
        assert q_value == 0.5


class TestRefineDecision:
    """Tests for refinement decision logic."""

    def test_high_q_returns_reinforce(self):
        """High Q-value should return REINFORCE."""
        profile = IndexProfile(q_value=0.8, q_update_count=10)
        action = determine_refine_action(profile)
        assert action == RefineAction.REINFORCE

    def test_low_q_high_usage_returns_refine(self):
        """Low Q + high usage should return REFINE."""
        profile = IndexProfile(q_value=0.2, q_update_count=8)
        action = determine_refine_action(profile)
        assert action == RefineAction.REFINE

    def test_low_q_low_usage_returns_keep(self):
        """Low Q + low usage should return KEEP."""
        profile = IndexProfile(q_value=0.2, q_update_count=2)
        action = determine_refine_action(profile)
        assert action == RefineAction.KEEP

    def test_very_low_q_high_usage_returns_deprecate(self):
        """Very low Q + high usage should return DEPRECATE."""
        profile = IndexProfile(q_value=0.1, q_update_count=15)
        action = determine_refine_action(profile)
        assert action == RefineAction.DEPRECATE

    def test_medium_q_returns_keep(self):
        """Medium Q-value should return KEEP."""
        profile = IndexProfile(q_value=0.5, q_update_count=10)
        action = determine_refine_action(profile)
        assert action == RefineAction.KEEP


class TestRefinedProfile:
    """Tests for Q-value inheritance on refinement."""

    def test_create_refined_profile_inherits_q(self):
        """New profile should inherit Q-value with decay."""
        old_profile = IndexProfile(q_value=0.3, q_update_count=10)
        new_profile = create_refined_profile(old_profile, q_decay=0.8)

        # new_q = 0.3 * 0.8 + 0.5 * 0.2 = 0.34
        assert new_profile.q_value == pytest.approx(0.34)

    def test_create_refined_profile_reduces_confidence(self):
        """New profile should have reduced confidence."""
        old_profile = IndexProfile(q_value=0.5, q_update_count=10)
        new_profile = create_refined_profile(old_profile, confidence_decay=0.5)

        # new_count = max(1, 10 * 0.5) = 5
        assert new_profile.q_update_count == 5

    def test_create_refined_profile_min_count(self):
        """New profile should have at least 1 update count."""
        old_profile = IndexProfile(q_value=0.5, q_update_count=1)
        new_profile = create_refined_profile(old_profile, confidence_decay=0.1)

        assert new_profile.q_update_count >= 1


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_create_initial_profile(self):
        """Should create profile with default Q-value."""
        profile = create_initial_profile()
        assert profile.q_value == 0.5
        assert profile.q_update_count == 0
        assert profile.created_at is not None

    def test_create_initial_profile_custom_q(self):
        """Should create profile with custom Q-value."""
        profile = create_initial_profile(q_value=0.7)
        assert profile.q_value == 0.7

    def test_migrate_legacy_profile(self):
        """Should migrate legacy profile to Q-value format."""
        profile = migrate_legacy_profile(
            success_count=8,
            failure_count=2,
            usage_count=15,
        )

        # Q-value = 8 / (8 + 2) = 0.8
        assert profile.q_value == pytest.approx(0.8)
        assert profile.q_update_count == 10

    def test_migrate_legacy_profile_no_data(self):
        """Should use defaults when no success/failure data."""
        profile = migrate_legacy_profile(
            success_count=0,
            failure_count=0,
        )

        assert profile.q_value == 0.5
        assert profile.q_update_count == 0


class TestIndexProfileProperties:
    """Tests for IndexProfile Q-value properties."""

    def test_confidence_calculation(self):
        """Confidence should scale with update count."""
        profile = IndexProfile(q_value=0.5, q_update_count=0)
        assert profile.confidence == 0.0

        profile.q_update_count = 10
        assert profile.confidence == 0.5

        profile.q_update_count = 20
        assert profile.confidence == 1.0

        profile.q_update_count = 40
        assert profile.confidence == 1.0  # Capped at 1.0

    def test_quality_score(self):
        """Quality score = q_value × confidence."""
        profile = IndexProfile(q_value=0.8, q_update_count=10)
        # quality = 0.8 * 0.5 = 0.4
        assert profile.quality_score == pytest.approx(0.4)

    def test_needs_refinement_property(self):
        """Should detect refinement need."""
        profile = IndexProfile(q_value=0.2, q_update_count=8)
        assert profile.needs_refinement is True

        profile = IndexProfile(q_value=0.5, q_update_count=8)
        assert profile.needs_refinement is False

    def test_should_deprecate_property(self):
        """Should detect deprecation need."""
        profile = IndexProfile(q_value=0.1, q_update_count=15)
        assert profile.should_deprecate is True

        profile = IndexProfile(q_value=0.3, q_update_count=15)
        assert profile.should_deprecate is False


class TestFindRefineCandidates:
    """Tests for find_refine_candidates function."""

    def test_finds_refine_candidates(self):
        """Should find memories needing refinement."""
        profiles = [
            ("mem_1", IndexProfile(q_value=0.2, q_update_count=8)),
            ("mem_2", IndexProfile(q_value=0.8, q_update_count=10)),
            ("mem_3", IndexProfile(q_value=0.1, q_update_count=15)),
        ]

        candidates = find_refine_candidates(profiles)

        assert len(candidates) == 2
        ids = [c["id"] for c in candidates]
        assert "mem_1" in ids
        assert "mem_3" in ids

    def test_empty_when_all_healthy(self):
        """Should return empty when all memories are healthy."""
        profiles = [
            ("mem_1", IndexProfile(q_value=0.8, q_update_count=10)),
            ("mem_2", IndexProfile(q_value=0.7, q_update_count=5)),
        ]

        candidates = find_refine_candidates(profiles)
        assert len(candidates) == 0
