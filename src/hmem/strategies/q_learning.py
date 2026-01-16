"""Q-Value Learning Module (MemRL-inspired).

Implements Monte Carlo style Q-value updates for memory utility learning.

Update rule: Q_new = Q_old + α(r - Q_old)

Where:
- α = learning rate (typically 0.1)
- r = reward signal (1.0 for success, 0.0 for failure)

Design rationale:
- Q-value directly learns "usefulness" of memories
- Converges to expected reward over time
- Simple and theoretically grounded (MemRL paper)
"""

from datetime import datetime
from typing import Literal

from hmem.constants import (
    Q_LEARNING_DEFAULT_ALPHA,
    Q_LEARNING_DEFAULT_Q_VALUE,
    REWARD_SUCCESS,
    REWARD_FAILURE,
    REWARD_UNKNOWN_USED,
    REWARD_UNKNOWN_IGNORED,
)
from hmem.models import IndexProfile


class QValueUpdater:
    """Monte Carlo style Q-value updater (MemRL-inspired).

    Update rule: Q_new = Q_old + α(r - Q_old)

    This converges to the expected reward over time:
    - If memory consistently succeeds (r=1.0), Q → 1.0
    - If memory consistently fails (r=0.0), Q → 0.0
    - Mixed outcomes converge to the success rate

    Theoretical guarantee (from MemRL):
    - Bounded variance: Var(Q) ≤ α/(2-α) × σ²
    - Convergence to true expected return
    """

    def __init__(self, alpha: float = Q_LEARNING_DEFAULT_ALPHA):
        """Initialize Q-value updater.

        Args:
            alpha: Learning rate (0.1 = smooth updates, 0.3 = fast adaptation)
                   Recommended: 0.1 for stable learning
        """
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"Alpha must be in (0, 1], got {alpha}")
        self.alpha = alpha

    def update(self, profile: IndexProfile, reward: float) -> None:
        """Update Q-value using Monte Carlo rule.

        Args:
            profile: IndexProfile to update (modified in place)
            reward: Reward signal (1.0 = success, 0.0 = failure, 0.5 = neutral)
        """
        if not 0.0 <= reward <= 1.0:
            raise ValueError(f"Reward must be in [0, 1], got {reward}")

        # Monte Carlo update: Q_new = Q_old + α(r - Q_old)
        profile.q_value += self.alpha * (reward - profile.q_value)
        profile.q_update_count += 1
        profile.last_used_at = datetime.now()

    def reward_from_outcome(
        self,
        outcome: Literal[
            "success", "failure", "unknown", "unknown_used", "unknown_ignored"
        ],
    ) -> float:
        """Convert outcome to reward signal.

        Extended to distinguish between "recalled and used" vs "recalled but ignored"
        (Gemini feedback fix). This helps the system learn which memories are
        actually useful vs just taking up context window space.

        Args:
            outcome: Session or task outcome
                - success: Memory was used and led to success
                - failure: Memory was used and led to failure
                - unknown: Legacy outcome, neutral reward
                - unknown_used: Memory was used but outcome unknown (slight positive)
                - unknown_ignored: Memory was recalled but ignored (slight negative)

        Returns:
            Reward value in [0, 1]
        """
        return {
            "success": REWARD_SUCCESS,
            "failure": REWARD_FAILURE,
            "unknown": 0.5,  # Backward compatibility
            "unknown_used": REWARD_UNKNOWN_USED,
            "unknown_ignored": REWARD_UNKNOWN_IGNORED,
        }.get(outcome, 0.5)

    def batch_update(
        self,
        profiles: list[IndexProfile],
        reward: float,
    ) -> int:
        """Update Q-values for multiple profiles.

        Args:
            profiles: List of IndexProfiles to update
            reward: Reward signal to apply to all

        Returns:
            Number of profiles updated
        """
        for profile in profiles:
            self.update(profile, reward)
        return len(profiles)


def create_initial_profile(
    q_value: float = Q_LEARNING_DEFAULT_Q_VALUE,
) -> IndexProfile:
    """Create a new IndexProfile with initial Q-value.

    Args:
        q_value: Initial Q-value (default 0.5 = neutral)

    Returns:
        New IndexProfile instance
    """
    return IndexProfile(
        q_value=q_value,
        q_update_count=0,
        created_at=datetime.now(),
        last_used_at=None,
    )


def migrate_legacy_profile(
    success_count: int,
    failure_count: int,
    usage_count: int = 0,
    created_at: datetime | None = None,
    last_used_at: datetime | None = None,
) -> IndexProfile:
    """Migrate legacy IndexProfile to Q-value based format.

    Converts old success_count/failure_count to Q-value.

    Args:
        success_count: Old success count
        failure_count: Old failure count
        usage_count: Old usage count (optional)
        created_at: Original creation time
        last_used_at: Last usage time

    Returns:
        New IndexProfile with Q-value derived from success rate
    """
    total = success_count + failure_count

    if total > 0:
        q_value = success_count / total
        q_update_count = total
    else:
        q_value = Q_LEARNING_DEFAULT_Q_VALUE
        q_update_count = 0

    return IndexProfile(
        q_value=q_value,
        q_update_count=q_update_count,
        created_at=created_at or datetime.now(),
        last_used_at=last_used_at,
        # Keep legacy fields for backward compatibility
        usage_count=usage_count,
        success_count=success_count,
        failure_count=failure_count,
    )
