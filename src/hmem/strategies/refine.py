"""Refinement Decision Logic (Q-value based).

Determines when memories should be refined based on Q-value patterns.

Design rationale (from MemRL integration):
- Low Q + High usage = frequently used but doesn't work → REFINE
- Very low Q + High usage = seriously broken → DEPRECATE
- High Q = working well → REINFORCE (no action)
- Low Q + Low usage = not relevant → candidate for forgetting
"""

from datetime import datetime
from enum import Enum
from typing import Any

from hmem.constants import (
    Q_LEARNING_REFINE_Q_THRESHOLD_LOW,
    Q_LEARNING_REFINE_MIN_USAGE,
    Q_LEARNING_DEPRECATE_Q_THRESHOLD,
    Q_LEARNING_DEPRECATE_MIN_USAGE,
    Q_LEARNING_INHERITANCE_Q_DECAY,
    Q_LEARNING_INHERITANCE_CONFIDENCE_DECAY,
)
from hmem.models import IndexProfile


class RefineAction(Enum):
    """Actions based on Q-value analysis."""

    KEEP = "keep"  # No action needed
    REFINE = "refine"  # Content needs improvement
    REINFORCE = "reinforce"  # Working well, increase confidence
    DEPRECATE = "deprecate"  # Consider removing


def determine_refine_action(
    profile: IndexProfile,
    q_threshold_low: float = Q_LEARNING_REFINE_Q_THRESHOLD_LOW,
    q_threshold_very_low: float = Q_LEARNING_DEPRECATE_Q_THRESHOLD,
    q_threshold_high: float = 0.7,
    min_usage_for_refine: int = Q_LEARNING_REFINE_MIN_USAGE,
    min_usage_for_deprecate: int = Q_LEARNING_DEPRECATE_MIN_USAGE,
) -> RefineAction:
    """Determine what action to take based on Q-value patterns.

    Decision matrix:
    | Q-value      | Usage Count | Action     |
    |--------------|-------------|------------|
    | High (>0.7)  | Any         | REINFORCE  |
    | Medium       | Low (<5)    | KEEP       |
    | Medium       | High (≥5)   | KEEP       |
    | Low (<0.3)   | Low (<5)    | KEEP       |
    | Low (<0.3)   | High (≥5)   | REFINE     |
    | Very Low     | High (≥10)  | DEPRECATE  |

    Args:
        profile: IndexProfile with Q-value data
        q_threshold_low: Q below this + high usage = refine
        q_threshold_very_low: Q below this = deprecation candidate
        q_threshold_high: Q above this = working well
        min_usage_for_refine: Minimum updates before considering refine
        min_usage_for_deprecate: Minimum updates for deprecation

    Returns:
        RefineAction indicating recommended action
    """
    q = profile.q_value
    usage = profile.q_update_count

    # High Q = working well
    if q > q_threshold_high:
        return RefineAction.REINFORCE

    # Very low Q + High usage = seriously broken
    if q < q_threshold_very_low and usage >= min_usage_for_deprecate:
        return RefineAction.DEPRECATE

    # Low Q + High usage = frequently used but failing
    if q < q_threshold_low and usage >= min_usage_for_refine:
        return RefineAction.REFINE

    return RefineAction.KEEP


def create_refined_profile(
    old_profile: IndexProfile,
    q_decay: float = Q_LEARNING_INHERITANCE_Q_DECAY,
    confidence_decay: float = Q_LEARNING_INHERITANCE_CONFIDENCE_DECAY,
) -> IndexProfile:
    """Create a new IndexProfile for a refined memory with Q-value inheritance.

    Q-value inheritance formula:
        new_q = old_q × q_decay + 0.5 × (1 - q_decay)

    This balances:
    - Continuity: inherit some learning from old version
    - Uncertainty: new content might behave differently

    Examples:
    - Old Q=0.3 (bad): new Q = 0.3×0.8 + 0.5×0.2 = 0.34
    - Old Q=0.8 (good): new Q = 0.8×0.8 + 0.5×0.2 = 0.74

    Args:
        old_profile: Profile of the memory being refined
        q_decay: How much Q-value to inherit (0.8 = 80%)
        confidence_decay: How much confidence to inherit (0.5 = 50%)

    Returns:
        New IndexProfile for the refined memory
    """
    # Q-value inheritance with decay toward neutral
    new_q_value = old_profile.q_value * q_decay + 0.5 * (1 - q_decay)

    # Reduce confidence (we're less certain about refined content)
    new_update_count = max(1, int(old_profile.q_update_count * confidence_decay))

    return IndexProfile(
        q_value=new_q_value,
        q_update_count=new_update_count,
        created_at=datetime.now(),
        last_used_at=None,
    )


def find_refine_candidates(
    profiles: list[tuple[str, IndexProfile]],
    q_threshold_low: float = Q_LEARNING_REFINE_Q_THRESHOLD_LOW,
    min_usage: int = Q_LEARNING_REFINE_MIN_USAGE,
) -> list[dict[str, Any]]:
    """Find memories that need refinement based on Q-value patterns.

    Args:
        profiles: List of (memory_id, IndexProfile) tuples
        q_threshold_low: Q below this triggers refine consideration
        min_usage: Minimum updates before considering refine

    Returns:
        List of refine candidate dicts with id, action, q_value, usage, reason
    """
    candidates = []

    for mem_id, profile in profiles:
        action = determine_refine_action(
            profile,
            q_threshold_low=q_threshold_low,
            min_usage_for_refine=min_usage,
        )

        if action in (RefineAction.REFINE, RefineAction.DEPRECATE):
            candidates.append(
                {
                    "id": mem_id,
                    "action": action.value,
                    "q_value": profile.q_value,
                    "usage": profile.q_update_count,
                    "reason": f"Low Q ({profile.q_value:.2f}) with {profile.q_update_count} uses",
                }
            )

    return candidates
