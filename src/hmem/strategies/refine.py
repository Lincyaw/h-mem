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
    """Actions based on Q-value analysis.

    Extended to distinguish refinement reasons (Gemini feedback fix):
    - REFINE_LOW_QUALITY: Memory has low Q due to poor quality → reset Q
    - REFINE_VERSION_UPDATE: Memory needs update but was working → inherit Q
    """

    KEEP = "keep"  # No action needed
    REFINE = "refine"  # Legacy: Content needs improvement (use specific types below)
    REFINE_LOW_QUALITY = "refine_low_quality"  # Low Q triggered → reset Q value
    REFINE_VERSION_UPDATE = "refine_version_update"  # Version update → inherit Q
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
    | Q-value      | Usage Count | Action            |
    |--------------|-------------|-------------------|
    | High (>0.7)  | Any         | REINFORCE         |
    | Medium       | Any         | KEEP              |
    | Low (<0.3)   | Low (<5)    | KEEP              |
    | Low (<0.3)   | High (≥5)   | REFINE_LOW_QUALITY|
    | Very Low     | High (≥10)  | DEPRECATE         |

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
        return RefineAction.REFINE_LOW_QUALITY

    return RefineAction.KEEP


def create_refined_profile(
    old_profile: IndexProfile,
    reason: RefineAction | None = None,
    q_decay: float = Q_LEARNING_INHERITANCE_Q_DECAY,
    confidence_decay: float = Q_LEARNING_INHERITANCE_CONFIDENCE_DECAY,
) -> IndexProfile:
    """Create a new IndexProfile for a refined memory with Q-value inheritance.

    Enhanced to handle different refinement reasons (Gemini feedback fix):
    - REFINE_LOW_QUALITY: Reset Q to neutral + exploration bonus (0.55)
      Rationale: Old content was "garbage", new content deserves fair chance
    - REFINE_VERSION_UPDATE: Inherit Q with decay toward neutral
      Rationale: Old content was working, new version should inherit reputation

    Q-value inheritance formula (for version updates):
        new_q = old_q × q_decay + 0.5 × (1 - q_decay)

    Args:
        old_profile: Profile of the memory being refined
        reason: Why refinement is happening (affects Q inheritance)
        q_decay: How much Q-value to inherit (0.8 = 80%)
        confidence_decay: How much confidence to inherit (0.5 = 50%)

    Returns:
        New IndexProfile for the refined memory
    """
    # Handle low quality refinement: reset Q to give fair chance
    if reason == RefineAction.REFINE_LOW_QUALITY:
        return IndexProfile(
            q_value=0.55,  # Slightly above neutral, exploration bonus
            q_update_count=1,  # Reset confidence
            created_at=datetime.now(),
            last_used_at=None,
        )

    # Handle version update or legacy refinement: inherit Q with decay
    new_q_value = old_profile.q_value * q_decay + 0.5 * (1 - q_decay)
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

        if action in (
            RefineAction.REFINE,
            RefineAction.REFINE_LOW_QUALITY,
            RefineAction.DEPRECATE,
        ):
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
