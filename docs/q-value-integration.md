# Q-Value Integration Design: Incorporating MemRL into h-mem

> This document describes how to integrate Q-value learning from MemRL into h-mem's memory system, including the rationale behind design decisions.

## Table of Contents

1. [Background: MemRL Paper Overview](#1-background-memrl-paper-overview)
2. [Comparative Analysis: MemRL vs h-mem](#2-comparative-analysis-memrl-vs-h-mem)
3. [Design Decisions and Rationale](#3-design-decisions-and-rationale)
4. [Implementation Plan](#4-implementation-plan)
5. [Migration Strategy](#5-migration-strategy)

---

## 1. Background: MemRL Paper Overview

### 1.1 Core Contribution

**MemRL** (Self-Evolving Agents via Runtime Reinforcement Learning on Episodic Memory) proposes a framework that enables LLM agents to self-evolve through non-parametric reinforcement learning on episodic memory.

**Key Innovation**: Instead of fine-tuning LLM parameters, MemRL learns Q-values for memories to distinguish high-value strategies from semantic noise.

### 1.2 Memory Structure: Intent-Experience-Utility Triplet

```
M = {(z_i, e_i, Q_i)}
```

| Component | Description | Example |
|-----------|-------------|---------|
| `z_i` | Intent Embedding | Vector representation of query/task |
| `e_i` | Experience | LLM-summarized execution trajectory |
| `Q_i` | Utility (Q-value) | Learned usefulness score |

### 1.3 Two-Phase Retrieval

```
Phase A: Similarity-Based Recall
    C(s) = TopK({i | sim(s, z_i) > δ}, by sim)

Phase B: Value-Aware Selection
    score = (1-λ) · sim̂(s, z_i) + λ · Q̂(z_i, e_i)
```

### 1.4 Q-Value Update Rule (Monte Carlo Style)

```
Q_new = Q_old + α(r - Q_old)
```

Where:
- `α` = learning rate (typically 0.1)
- `r` = reward signal (1.0 for success, 0.0 for failure)

### 1.5 Theoretical Guarantees

MemRL provides mathematical convergence proof:
- **Theorem 1**: Q-values converge to true expected returns
- **Bounded Variance**: `Var(Q) ≤ α/(2-α) · σ²`
- **Forgetting Rate**: 0.041 (empirically measured)

---

## 2. Comparative Analysis: MemRL vs h-mem

### 2.1 Philosophical Differences

| Dimension | MemRL | h-mem |
|-----------|-------|-------|
| **Theoretical Basis** | Constructive Episodic Simulation | Atkinson-Shiffrin Memory Model |
| **Core Metaphor** | Decision-making from past experiences | Knowledge organization & retrieval |
| **Learning Paradigm** | Reinforcement Learning (Value Iteration) | Cognitive Psychology (Consolidation) |

### 2.2 Memory Granularity Comparison

```
h-mem Layers                      MemRL
─────────────────────────────────────────────
L3 Principles/Skills              (none)
     ↑ induction
L2 Facts
     ↑                           ≈ Experience (task trajectory summary)
L1 Events (fragmented)            (none)
     ↑
L0 Sensory                        (none)
```

**Key Insight**: MemRL's "experience" is task-level trajectory summaries, closest to h-mem's **L2 Facts** layer - not as fragmented as Events, not as abstract as Principles.

### 2.3 Retrieval Mechanism Comparison

| Aspect | MemRL | h-mem (Current) |
|--------|-------|-----------------|
| Primary Signal | Q-value (learned utility) | Similarity (semantic match) |
| Secondary Signals | Similarity | Recency, Importance, Outcome |
| Exploration | λ parameter balances exploration/exploitation | Exploration bonus (heuristic) |
| Theoretical Guarantee | Bellman convergence | None |

### 2.4 Strengths and Weaknesses

**MemRL Strengths**:
- Mathematical convergence proof
- Q-value directly learns "usefulness"
- Low forgetting rate (0.041)
- Acts as trajectory verifier for multi-step tasks

**MemRL Weaknesses**:
- Requires clear reward signals
- No knowledge abstraction (no induction)
- Flat memory structure
- No provenance tracking

**h-mem Strengths**:
- Knowledge hierarchy (Event → Fact → Principle)
- Multi-storage backend (Vector + Graph + KV)
- Complete provenance chain
- Configuration-driven flexibility

**h-mem Weaknesses**:
- No theoretical convergence guarantee
- Heuristic weight updates
- Weak exploration mechanism
- Complex feedback inference

---

## 3. Design Decisions and Rationale

### 3.1 Decision: Use Q-value as the Single "Utility" Signal

**Problem**: Current h-mem uses multiple overlapping signals:
- `success_count` / `failure_count` → success rate
- `outcome` (success/failure/unknown)
- `recency` (time decay)
- `importance` (access frequency)

**Issue**: These signals are **not orthogonal**:
- `outcome` and `success_rate` both measure success/failure
- `importance` (access count) correlates with recency
- No principled way to combine them

**Solution**: Replace with **three orthogonal signals**:

```
score = w_s × Similarity + w_q × Q-value + w_f × Freshness
```

| Signal | Meaning | Source |
|--------|---------|--------|
| Similarity | Semantic relevance | Vector search (computed) |
| Q-value | Learned utility | Feedback loop (learned) |
| Freshness | Information timeliness | Timestamp (computed) |

**Rationale**:
1. **Similarity** = "Is this relevant to the query?" (semantic)
2. **Q-value** = "Did this work well in the past?" (learned)
3. **Freshness** = "Is this still current?" (temporal)

These three dimensions are independent and cover different aspects of memory quality.

### 3.2 Decision: Layered Q-values (L2 + L3 only)

**Problem**: Should all memory types have Q-values?

**Analysis**:

| Layer | Content | Should have Q-value? | Reason |
|-------|---------|---------------------|--------|
| L1 Events | Fragmented conversation logs | ❌ No | Too granular, rarely recalled directly |
| L2 Facts | Structured facts (SemanticTriple) | ✅ Yes | MemRL operates at this level |
| L3 Principles | Induced rules | ✅ Yes | High-level reusable knowledge |
| L3 Skills | Procedural templates | ✅ Yes | High-level reusable knowledge |

**Decision**: Only L2 (Facts) and L3 (Principles/Skills) have Q-values.

**Rationale**:
1. L1 Events are "raw materials" - too numerous and fragmented
2. L2/L3 memories are what actually get recalled and used
3. MemRL's experience granularity aligns with L2 Facts
4. Reduces storage and computation overhead

### 3.3 Decision: Layer-Independent Q-value Updates

**Problem**: When a Skill is recalled and used successfully, should we also update Q-values of the underlying Events that generated it?

**Options Considered**:

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Layer Independent | Update only the recalled memory | Simple, no credit dilution | Events never learn |
| B. Backpropagation | Propagate reward to parent memories | Full credit assignment | Complex, dilutes credit |
| C. Hybrid | Update recalled + use child Q-values for refine decisions | Balance | Moderate complexity |

**Decision**: **Option A - Layer Independent**

```python
# Only update the memory that was actually recalled
if memory_id.startswith("skill_"):
    update_q_value(skill_store, memory_id, reward)
elif memory_id.startswith("fact_"):
    update_q_value(semantic_store, memory_id, reward)
elif memory_id.startswith("prin_"):
    update_q_value(semantic_store, memory_id, reward)
# L1 Events: no Q-value update
```

**Rationale**:
1. Avoids complex credit assignment problem
2. Each layer learns its own "utility when recalled"
3. Parent-child Q-values are used indirectly for refine decisions

### 3.4 Decision: Q-value Drives Refinement

**Problem**: When should a Principle or Skill be refined?

**Current h-mem approach**: Heuristic rules based on `success_rate` and `usage_count`

**MemRL insight**: Q-value naturally encodes "this memory isn't working"

**Decision**: Use Q-value to trigger refinement:

| Condition | Q-value | Usage Count | Action |
|-----------|---------|-------------|--------|
| Low Q + High Usage | < 0.3 | ≥ 5 | **Trigger Refine** |
| Very Low Q + High Usage | < 0.2 | ≥ 10 | Mark as Deprecation Candidate |
| High Q | > 0.7 | any | Reinforce (no action) |

**Rationale**:
1. Low Q + High Usage = "frequently used but doesn't work" → needs improvement
2. Low Q + Low Usage = "irrelevant" → candidate for forgetting
3. Q-value is more principled than success_rate (learned vs. counted)

### 3.5 Decision: Q-value Inheritance on Refine

**Problem**: When a Skill is refined, what Q-value should the new version have?

**Options**:
1. Reset to neutral (0.5)
2. Inherit fully from old version
3. Inherit with decay

**Decision**: **Inherit with decay**

```python
new_q_value = old_q_value * 0.8 + 0.5 * 0.2  # 80% inherit + 20% neutral
new_update_count = max(1, old_update_count // 2)  # Reduce confidence
```

**Rationale**:
1. Fully resetting loses learning history
2. Fully inheriting ignores that content changed
3. Decay balances continuity with uncertainty about new content

---

## 4. Implementation Plan

### 4.1 Phase 1: Data Model Changes

#### 4.1.1 Simplify IndexProfile

**Before**:
```python
class IndexProfile(BaseModel):
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    weight: float = 1.0
    first_used_at: datetime | None = None
    last_used_at: datetime | None = None
    last_success_at: datetime | None = None
```

**After**:
```python
class IndexProfile(BaseModel):
    """Memory utility profile with Q-value learning (MemRL-inspired)."""

    # Core Q-value fields
    q_value: float = Field(default=0.5, ge=0.0, le=1.0)
    q_update_count: int = Field(default=0, ge=0)

    # Time fields (for freshness calculation)
    created_at: datetime = Field(default_factory=datetime.now)
    last_used_at: datetime | None = None

    @property
    def confidence(self) -> float:
        """Confidence based on update count (20 updates = full confidence)."""
        return min(1.0, self.q_update_count / 20.0)

    @property
    def needs_refinement(self) -> bool:
        """Low Q + high usage → needs refinement."""
        return self.q_value < 0.3 and self.q_update_count >= 5

    @property
    def should_deprecate(self) -> bool:
        """Very low Q + high usage → deprecation candidate."""
        return self.q_value < 0.2 and self.q_update_count >= 10
```

#### 4.1.2 Add IndexProfile to SemanticTriple

```python
class SemanticTriple(BaseModel):
    # ... existing fields ...

    # NEW: Q-value based utility profile
    index_profile: IndexProfile = Field(
        default_factory=IndexProfile,
        description="Q-value based utility profile"
    )
```

### 4.2 Phase 2: Ranking Strategy Changes

#### 4.2.1 New QValueRanker

**File**: `src/hmem/strategies/ranking.py`

```python
class QValueRanker(RetrievalRanker):
    """MemRL-inspired ranking with Q-value learning.

    Three orthogonal signals:
    - Similarity: Semantic relevance (from vector search)
    - Q-value: Learned utility (from feedback)
    - Freshness: Information timeliness (exponential decay)
    """

    def __init__(
        self,
        similarity_weight: float = 0.5,
        q_weight: float = 0.35,
        freshness_weight: float = 0.15,
        freshness_halflife_days: float = 30.0,
    ):
        # Validate weights sum to 1.0
        total = similarity_weight + q_weight + freshness_weight
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        self.similarity_weight = similarity_weight
        self.q_weight = q_weight
        self.freshness_weight = freshness_weight
        self.freshness_halflife_days = freshness_halflife_days

    def _calculate_score(self, memory: Memory, now: datetime) -> float:
        # Signal 1: Similarity (already computed by vector search)
        similarity = memory.score

        # Signal 2: Q-value (from IndexProfile)
        q_value = 0.5  # default neutral
        if memory.index_profile:
            q_value = memory.index_profile.q_value

        # Signal 3: Freshness (exponential decay)
        freshness = self._calculate_freshness(memory.timestamp, now)

        return (
            self.similarity_weight * similarity
            + self.q_weight * q_value
            + self.freshness_weight * freshness
        )

    def _calculate_freshness(self, timestamp: datetime, now: datetime) -> float:
        """Exponential decay: score = 0.5^(age_days / halflife)"""
        age_days = (now - timestamp).total_seconds() / 86400.0
        return 2 ** (-age_days / self.freshness_halflife_days)
```

### 4.3 Phase 3: Q-Value Update Mechanism

#### 4.3.1 QValueUpdater Component

**File**: `src/hmem/strategies/q_learning.py`

```python
from datetime import datetime
from typing import Literal

from hmem.models import IndexProfile


class QValueUpdater:
    """Monte Carlo style Q-value updater (MemRL-inspired).

    Update rule: Q_new = Q_old + α(r - Q_old)

    Called during remember() phase when feedback is available.
    """

    def __init__(self, alpha: float = 0.1):
        """
        Args:
            alpha: Learning rate (0.1 = smooth updates, 0.3 = fast adaptation)
        """
        self.alpha = alpha

    def update(self, profile: IndexProfile, reward: float) -> None:
        """Update Q-value using Monte Carlo rule.

        Args:
            profile: IndexProfile to update
            reward: Reward signal (1.0 = success, 0.0 = failure)
        """
        profile.q_value += self.alpha * (reward - profile.q_value)
        profile.q_update_count += 1
        profile.last_used_at = datetime.now()

    def reward_from_outcome(
        self,
        outcome: Literal["success", "failure", "unknown"]
    ) -> float:
        """Convert outcome to reward signal."""
        return {"success": 1.0, "failure": 0.0, "unknown": 0.5}[outcome]
```

#### 4.3.2 Integration into Consolidator

**File**: `src/hmem/hippocampus/consolidator.py` (modified)

```python
class Consolidator:
    def __init__(
        self,
        # ... existing params ...
        q_updater: QValueUpdater | None = None,
    ):
        self.q_updater = q_updater or QValueUpdater(alpha=0.1)

    def consolidate(
        self,
        session_id: str,
        events: list[Event],
        used_memory_ids: set[str] | None = None,  # NEW
        session_outcome: Literal["success", "failure", "unknown"] = "unknown",
    ) -> ConsolidationResult:
        """
        Extended consolidation with Q-value updates.

        Args:
            session_id: Session identifier
            events: Events to consolidate
            used_memory_ids: Memory IDs that were recalled and used
            session_outcome: Overall session outcome
        """
        # ... existing consolidation logic ...

        # NEW: Q-value updates
        q_updates = 0
        if used_memory_ids and session_outcome != "unknown":
            reward = self.q_updater.reward_from_outcome(session_outcome)
            q_updates = self._update_q_values(used_memory_ids, reward)

        # Check Q-value based refinement triggers
        refine_candidates = self._check_q_based_refinement()

        return ConsolidationResult(
            # ... existing fields ...
            metadata={
                "q_updates": q_updates,
                "refine_candidates": refine_candidates,
            }
        )

    def _update_q_values(self, memory_ids: set[str], reward: float) -> int:
        """Update Q-values for used memories (L2 Facts + L3 Principles/Skills)."""
        updated = 0

        for mem_id in memory_ids:
            # Determine memory type by ID prefix and update accordingly
            if mem_id.startswith("fact_") and self.semantic_store:
                profile = self.semantic_store.get_profile(mem_id)
                if profile:
                    self.q_updater.update(profile, reward)
                    self.semantic_store.save_profile(mem_id, profile)
                    updated += 1

            elif mem_id.startswith("skill_") and self.skill_store:
                profile = self.skill_store.get_profile(mem_id)
                if profile:
                    self.q_updater.update(profile, reward)
                    self.skill_store.save_profile(mem_id, profile)
                    updated += 1

            elif mem_id.startswith("prin_") and self.semantic_store:
                profile = self.semantic_store.get_principle_profile(mem_id)
                if profile:
                    self.q_updater.update(profile, reward)
                    self.semantic_store.save_principle_profile(mem_id, profile)
                    updated += 1

            # L1 Events (evt_*): no Q-value, skip

        return updated

    def _check_q_based_refinement(self) -> list[dict[str, Any]]:
        """Check for memories needing refinement based on Q-value."""
        candidates = []

        # Check Skills
        if self.skill_store:
            for skill in self.skill_store.get_all():
                profile = skill.index_profile
                if profile and profile.needs_refinement:
                    candidates.append({
                        "type": "skill",
                        "id": skill.id,
                        "action": "refine",
                        "q_value": profile.q_value,
                        "usage": profile.q_update_count,
                        "reason": f"Low Q ({profile.q_value:.2f}) with {profile.q_update_count} uses"
                    })

        # Check Principles
        if self.semantic_store:
            for principle in self.semantic_store.get_all_principles():
                profile = principle.index_profile
                if profile and profile.needs_refinement:
                    candidates.append({
                        "type": "principle",
                        "id": principle.id,
                        "action": "refine",
                        "q_value": profile.q_value,
                        "usage": profile.q_update_count,
                        "reason": f"Low Q ({profile.q_value:.2f}) with {profile.q_update_count} uses"
                    })

        return candidates
```

### 4.4 Phase 4: Configuration Changes

**File**: `config/memory.yaml`

```yaml
# ============ Q-Learning Configuration (NEW) ============
q_learning:
  # Learning rate for Q-value updates
  alpha: 0.1

  # Ranking weights (must sum to 1.0)
  weights:
    similarity: 0.5    # Semantic relevance
    q_value: 0.35      # Learned utility
    freshness: 0.15    # Information timeliness

  # Freshness decay
  freshness_halflife_days: 30.0

  # Refinement triggers
  refine:
    q_threshold_low: 0.3       # Q below this + high usage → refine
    min_usage_for_refine: 5    # Minimum updates before considering refine
    deprecate_threshold: 0.2   # Q below this → deprecation candidate
    min_usage_for_deprecate: 10

  # Q-value inheritance on refine
  inheritance:
    q_decay: 0.8           # Inherit 80% of old Q-value
    confidence_decay: 0.5  # Inherit 50% of update count

# ============ Retrieval Configuration (UPDATED) ============
retrieval:
  # Changed from HybridRanker to QValueRanker
  ranker: "hmem.strategies.ranking.QValueRanker"
  default_limit: 10
  cache_enabled: true
```

### 4.5 Complete Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                          RECALL Phase                           │
├─────────────────────────────────────────────────────────────────┤
│  Query → Vector Search → Candidates                             │
│                              ↓                                  │
│           QValueRanker.rank(candidates)                         │
│           ┌─────────────────────────────────┐                   │
│           │ score = 0.5×sim + 0.35×Q + 0.15×fresh │            │
│           └─────────────────────────────────┘                   │
│                              ↓                                  │
│           Return ranked memories (with XML markup)              │
│           Record used_memory_ids                                │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                         REMEMBER Phase                          │
├─────────────────────────────────────────────────────────────────┤
│  1. Collect session information                                 │
│     - used_memory_ids (extracted from XML tags)                 │
│     - session_outcome (LLM analysis / explicit)                 │
│                                                                 │
│  2. Q-value updates (L2 Facts + L3 Principles/Skills only)      │
│     ┌─────────────────────────────────────┐                     │
│     │ Q_new = Q_old + α × (reward - Q_old) │                    │
│     └─────────────────────────────────────┘                     │
│                                                                 │
│  3. Refine trigger check                                        │
│     - Low Q + High usage → add to refine queue                  │
│     - Very low Q → mark as deprecation candidate                │
│                                                                 │
│  4. Execute Refine (if triggered)                               │
│     - LLM generates new content                                 │
│     - Q-value inheritance (with decay)                          │
│     - Old memory marked deprecated                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Migration Strategy

### 5.1 Data Migration

```python
def migrate_index_profile(old_profile: dict) -> IndexProfile:
    """Migrate old IndexProfile to new Q-value based format."""
    # Derive Q-value from success_rate
    success = old_profile.get("success_count", 0)
    failure = old_profile.get("failure_count", 0)
    total = success + failure

    if total > 0:
        q_value = success / total
        q_update_count = total
    else:
        q_value = 0.5  # neutral
        q_update_count = 0

    return IndexProfile(
        q_value=q_value,
        q_update_count=q_update_count,
        created_at=old_profile.get("first_used_at", datetime.now()),
        last_used_at=old_profile.get("last_used_at"),
    )
```

### 5.2 Backward Compatibility

1. Keep old `HybridRanker` class, mark as `@deprecated`
2. Support both ranker types via configuration
3. Migration script to convert existing IndexProfile data

### 5.3 Testing Strategy

1. Unit tests for `QValueUpdater`
2. Integration tests for `QValueRanker`
3. Acceptance test: verify Q-value learning improves retrieval over time
4. Regression test: ensure no performance degradation

---

## 6. Q-Value and Memory Refinement Integration

### 6.1 The Refinement Challenge

h-mem has a unique capability that MemRL lacks: **knowledge abstraction and refinement**. Principles and Skills can evolve over time based on usage patterns.

**Question**: How should Q-value learning integrate with the refinement mechanism?

### 6.2 Q-Value as Refinement Signal

#### 6.2.1 Refinement Trigger Conditions

```python
class RefineAction(Enum):
    KEEP = "keep"           # No action needed
    REFINE = "refine"       # Content needs improvement
    REINFORCE = "reinforce" # Working well, increase confidence
    DEPRECATE = "deprecate" # Consider removing

def determine_refine_action(profile: IndexProfile) -> RefineAction:
    """Determine what action to take based on Q-value patterns."""

    Q_LOW = 0.3
    Q_VERY_LOW = 0.2
    Q_HIGH = 0.7
    MIN_USAGE = 5
    HIGH_USAGE = 10

    # Low Q + High usage = frequently used but doesn't work
    if profile.q_value < Q_LOW and profile.q_update_count >= MIN_USAGE:
        return RefineAction.REFINE

    # Very low Q + High usage = seriously broken
    if profile.q_value < Q_VERY_LOW and profile.q_update_count >= HIGH_USAGE:
        return RefineAction.DEPRECATE

    # High Q = working well
    if profile.q_value > Q_HIGH:
        return RefineAction.REINFORCE

    return RefineAction.KEEP
```

#### 6.2.2 Refinement Decision Matrix

| Q-value | Usage Count | Interpretation | Action |
|---------|-------------|----------------|--------|
| High (>0.7) | Any | Working well | Reinforce |
| Medium (0.3-0.7) | Low (<5) | Not enough data | Keep observing |
| Medium (0.3-0.7) | High (≥5) | Acceptable | Keep |
| Low (<0.3) | Low (<5) | Not relevant | Consider forgetting |
| Low (<0.3) | High (≥5) | **Frequently used but failing** | **REFINE** |
| Very Low (<0.2) | High (≥10) | Seriously broken | Deprecate |

### 6.3 Q-Value Inheritance Strategy

When a memory is refined, the new version needs an initial Q-value:

```python
def create_refined_memory(
    old_memory: Principle | Skill,
    new_content: str,
    q_decay: float = 0.8,
    confidence_decay: float = 0.5,
) -> dict[str, Any]:
    """Create a refined memory with Q-value inheritance.

    Args:
        old_memory: Original memory being refined
        new_content: New/improved content from LLM
        q_decay: How much Q-value to inherit (0.8 = 80%)
        confidence_decay: How much confidence to inherit (0.5 = 50%)

    Returns:
        Dict with fields for the new memory
    """
    old_profile = old_memory.index_profile or IndexProfile()

    # Q-value inheritance with decay
    # - If old Q was 0.3 (bad), new Q = 0.3 * 0.8 + 0.5 * 0.2 = 0.34
    # - If old Q was 0.8 (good), new Q = 0.8 * 0.8 + 0.5 * 0.2 = 0.74
    new_q_value = old_profile.q_value * q_decay + 0.5 * (1 - q_decay)

    # Reduce confidence (we're less certain about refined content)
    new_update_count = max(1, int(old_profile.q_update_count * confidence_decay))

    return {
        "content": new_content,
        "parent_ids": [old_memory.id],
        "derivation_type": "refinement",
        "index_profile": IndexProfile(
            q_value=new_q_value,
            q_update_count=new_update_count,
            created_at=datetime.now(),
        ),
        "version": old_memory.version + 1,
    }
```

### 6.4 Cross-Layer Q-Value Aggregation for Refine Decisions

While we update Q-values independently per layer, we can use cross-layer information for smarter refine decisions:

```python
def should_reinduce_principle(
    principle: Principle,
    child_facts: list[SemanticTriple],
) -> bool:
    """Check if a Principle should be re-induced from its source Facts.

    Scenario: Source Facts have high Q-values, but the induced Principle
    has low Q-value. This suggests the induction process produced
    something suboptimal.
    """
    if not child_facts:
        return False

    principle_q = principle.index_profile.q_value
    avg_child_q = sum(f.index_profile.q_value for f in child_facts) / len(child_facts)

    # Good ingredients but bad result → re-induce
    if avg_child_q > 0.6 and principle_q < 0.4:
        return True

    return False
```

### 6.5 Complete Refinement Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    REFINEMENT WORKFLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐                                                │
│  │ Q-value     │                                                │
│  │ < 0.3 AND   │──── YES ────→ Add to Refine Queue              │
│  │ usage ≥ 5   │                     │                          │
│  └─────────────┘                     ↓                          │
│         │                   ┌─────────────────┐                 │
│         NO                  │ LLM Refine      │                 │
│         ↓                   │ (generate new   │                 │
│  ┌─────────────┐            │  content)       │                 │
│  │ Q-value     │            └────────┬────────┘                 │
│  │ < 0.2 AND   │                     │                          │
│  │ usage ≥ 10  │                     ↓                          │
│  └─────────────┘            ┌─────────────────┐                 │
│         │                   │ Create New      │                 │
│        YES                  │ Memory with     │                 │
│         ↓                   │ Inherited Q     │                 │
│  Mark as Deprecation        └────────┬────────┘                 │
│  Candidate                           │                          │
│                                      ↓                          │
│                             ┌─────────────────┐                 │
│                             │ Mark Old Memory │                 │
│                             │ as Deprecated   │                 │
│                             │ (successor_id)  │                 │
│                             └─────────────────┘                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Detailed File Changes

### 7.1 Files to Modify

| File | Changes |
|------|---------|
| `src/hmem/models.py` | Simplify `IndexProfile`, add to `SemanticTriple` |
| `src/hmem/strategies/ranking.py` | Add `QValueRanker` class |
| `src/hmem/hippocampus/consolidator.py` | Add Q-value update logic |
| `src/hmem/hippocampus/retrieval_engine.py` | Track `used_memory_ids` |
| `src/hmem/storage/neo4j_semantic.py` | Add `get_profile`/`save_profile` methods |
| `src/hmem/storage/skill.py` | Add `get_profile`/`save_profile` methods |
| `src/hmem/config.py` | Add Q-learning configuration |
| `config/memory.yaml` | Add Q-learning section |
| `src/hmem/constants.py` | Add Q-learning constants |

### 7.2 Files to Create

| File | Purpose |
|------|---------|
| `src/hmem/strategies/q_learning.py` | `QValueUpdater` class |
| `src/hmem/strategies/refine.py` | Refinement decision logic |
| `tests/test_q_learning.py` | Unit tests for Q-value learning |
| `scripts/migrate_index_profile.py` | Migration script |

### 7.3 Detailed Changes by File

#### 7.3.1 `src/hmem/models.py`

```python
# REMOVE these fields from IndexProfile:
# - usage_count (replaced by q_update_count)
# - success_count (replaced by q_value)
# - failure_count (replaced by q_value)
# - weight (replaced by q_value)
# - first_used_at (use created_at)
# - last_success_at (not needed)

# ADD these fields to IndexProfile:
# - q_value: float = 0.5
# - q_update_count: int = 0
# - created_at: datetime

# ADD IndexProfile to SemanticTriple:
# - index_profile: IndexProfile = Field(default_factory=IndexProfile)
```

#### 7.3.2 `src/hmem/strategies/ranking.py`

```python
# ADD new class QValueRanker:
# - __init__(similarity_weight, q_weight, freshness_weight, freshness_halflife_days)
# - _calculate_score(memory, now) -> float
# - _calculate_freshness(timestamp, now) -> float
# - rank(candidates, query) -> list[Memory]

# KEEP HybridRanker but mark as @deprecated
```

#### 7.3.3 `src/hmem/hippocampus/consolidator.py`

```python
# ADD to __init__:
# - q_updater: QValueUpdater | None = None

# MODIFY consolidate():
# - Add used_memory_ids parameter
# - Add session_outcome parameter
# - Call _update_q_values()
# - Call _check_q_based_refinement()

# ADD new methods:
# - _update_q_values(memory_ids, reward) -> int
# - _check_q_based_refinement() -> list[dict]
```

#### 7.3.4 `src/hmem/constants.py`

```python
# ADD Q-learning constants:
Q_LEARNING_DEFAULT_ALPHA = 0.1
Q_LEARNING_DEFAULT_SIMILARITY_WEIGHT = 0.5
Q_LEARNING_DEFAULT_Q_WEIGHT = 0.35
Q_LEARNING_DEFAULT_FRESHNESS_WEIGHT = 0.15
Q_LEARNING_DEFAULT_FRESHNESS_HALFLIFE_DAYS = 30.0
Q_LEARNING_REFINE_Q_THRESHOLD_LOW = 0.3
Q_LEARNING_REFINE_MIN_USAGE = 5
Q_LEARNING_DEPRECATE_Q_THRESHOLD = 0.2
Q_LEARNING_DEPRECATE_MIN_USAGE = 10
Q_LEARNING_INHERITANCE_Q_DECAY = 0.8
Q_LEARNING_INHERITANCE_CONFIDENCE_DECAY = 0.5
```

---

## 8. Testing Plan

### 8.1 Unit Tests

#### 8.1.1 QValueUpdater Tests

```python
# tests/test_q_learning.py

class TestQValueUpdater:
    def test_update_increases_q_on_success(self):
        """Q-value should increase when reward=1.0"""
        updater = QValueUpdater(alpha=0.1)
        profile = IndexProfile(q_value=0.5, q_update_count=0)

        updater.update(profile, reward=1.0)

        assert profile.q_value == 0.55  # 0.5 + 0.1*(1.0-0.5)
        assert profile.q_update_count == 1

    def test_update_decreases_q_on_failure(self):
        """Q-value should decrease when reward=0.0"""
        updater = QValueUpdater(alpha=0.1)
        profile = IndexProfile(q_value=0.5, q_update_count=0)

        updater.update(profile, reward=0.0)

        assert profile.q_value == 0.45  # 0.5 + 0.1*(0.0-0.5)

    def test_convergence_to_true_mean(self):
        """Q-value should converge to expected reward"""
        updater = QValueUpdater(alpha=0.1)
        profile = IndexProfile(q_value=0.5, q_update_count=0)

        # Simulate 80% success rate
        for _ in range(100):
            reward = 1.0 if random.random() < 0.8 else 0.0
            updater.update(profile, reward)

        # Should converge close to 0.8
        assert 0.75 < profile.q_value < 0.85

    def test_reward_from_outcome(self):
        """outcome → reward mapping"""
        updater = QValueUpdater()

        assert updater.reward_from_outcome("success") == 1.0
        assert updater.reward_from_outcome("failure") == 0.0
        assert updater.reward_from_outcome("unknown") == 0.5
```

#### 8.1.2 QValueRanker Tests

```python
class TestQValueRanker:
    def test_weights_must_sum_to_one(self):
        """Should raise error if weights don't sum to 1.0"""
        with pytest.raises(ValueError):
            QValueRanker(similarity_weight=0.5, q_weight=0.5, freshness_weight=0.5)

    def test_high_q_value_ranks_higher(self):
        """Memories with higher Q-values should rank higher"""
        ranker = QValueRanker()

        mem_high_q = Memory(
            content="high q",
            score=0.8,  # same similarity
            source="semantic",
            timestamp=datetime.now(),
            index_profile=IndexProfile(q_value=0.9),
        )
        mem_low_q = Memory(
            content="low q",
            score=0.8,  # same similarity
            source="semantic",
            timestamp=datetime.now(),
            index_profile=IndexProfile(q_value=0.1),
        )

        ranked = ranker.rank([mem_low_q, mem_high_q], "query")

        assert ranked[0].content == "high q"

    def test_freshness_decay(self):
        """Older memories should have lower freshness score"""
        ranker = QValueRanker(freshness_halflife_days=30.0)
        now = datetime.now()

        fresh = ranker._calculate_freshness(now, now)
        old_30d = ranker._calculate_freshness(now - timedelta(days=30), now)
        old_60d = ranker._calculate_freshness(now - timedelta(days=60), now)

        assert fresh == 1.0
        assert 0.49 < old_30d < 0.51  # ~0.5 at halflife
        assert 0.24 < old_60d < 0.26  # ~0.25 at 2x halflife
```

### 8.2 Integration Tests

```python
class TestQValueIntegration:
    def test_recall_then_remember_updates_q(self):
        """Full cycle: recall → use → remember → Q updated"""
        system = MemorySystem(config)

        # Store a fact
        fact_id = system.store_fact("Python uses indentation for blocks")

        # Recall it
        memories = system.recall("How does Python handle code blocks?")
        assert any(m.id == fact_id for m in memories)

        # Remember with success outcome
        system.remember(
            conversation=conv,
            used_memory_ids={fact_id},
            session_outcome="success"
        )

        # Q-value should have increased
        fact = system.get_fact(fact_id)
        assert fact.index_profile.q_value > 0.5

    def test_low_q_triggers_refine(self):
        """Memories with low Q + high usage should trigger refine"""
        system = MemorySystem(config)

        # Create a skill with low Q and high usage
        skill_id = system.store_skill(...)
        skill = system.get_skill(skill_id)
        skill.index_profile.q_value = 0.2
        skill.index_profile.q_update_count = 10
        system.update_skill(skill)

        # Consolidate should detect refine candidate
        result = system.consolidate(session_id="test", events=[])

        assert any(
            c["id"] == skill_id and c["action"] == "refine"
            for c in result.metadata["refine_candidates"]
        )
```

### 8.3 Acceptance Tests

```python
class TestQValueAcceptance:
    def test_goldfish_with_q_learning(self):
        """Q-value learning should improve retrieval over repeated use"""
        system = MemorySystem(config)

        # Store multiple similar facts
        facts = [
            "Use requests library for HTTP calls",  # Good advice
            "Use urllib for HTTP calls",            # Also works but less common
            "Use socket for HTTP calls",            # Bad advice
        ]
        fact_ids = [system.store_fact(f) for f in facts]

        # Simulate usage patterns
        for _ in range(20):
            memories = system.recall("How to make HTTP request in Python?")

            # Simulate: requests advice works, socket advice fails
            for m in memories:
                if "requests" in m.content:
                    outcome = "success"
                elif "socket" in m.content:
                    outcome = "failure"
                else:
                    outcome = "success"

                system.remember(
                    conversation=None,
                    used_memory_ids={m.id},
                    session_outcome=outcome
                )

        # After learning, requests should rank highest
        memories = system.recall("How to make HTTP request in Python?")
        assert "requests" in memories[0].content
```

---

## 9. Risks and Mitigations

### 9.1 Risk: Cold Start Problem

**Issue**: New memories have Q=0.5 (neutral), may not be selected over proven memories.

**Mitigation**:
- Freshness signal gives bonus to new memories
- Can add exploration bonus (similar to current `HybridRankerWithExploration`)

### 9.2 Risk: Sparse Feedback

**Issue**: Not all sessions have clear success/failure signals.

**Mitigation**:
- Use `outcome="unknown"` → reward=0.5 (no change)
- LLM-based outcome detection from conversation content
- Explicit user feedback mechanisms

### 9.3 Risk: Q-Value Drift

**Issue**: Q-values might drift over time if task distribution changes.

**Mitigation**:
- Freshness signal naturally down-weights old memories
- Periodic re-evaluation of Q-values
- Confidence decay over time without updates

### 9.4 Risk: Migration Complexity

**Issue**: Existing data needs migration.

**Mitigation**:
- Migration script converts `success_rate` → initial Q-value
- Backward compatible config (can use old ranker)
- Gradual rollout with A/B testing

---

## Appendix A: MemRL Paper Reference

- **Title**: MemRL: Self-Evolving Agents via Runtime Reinforcement Learning on Episodic Memory
- **Authors**: Zhang et al.
- **ArXiv**: 2601.03192v1
- **Key Results**:
  - ALFWorld: +24.1pp improvement over baseline
  - Forgetting rate: 0.041 (vs 0.051 for MemP)
  - Pearson correlation between Q-value and success: r = 0.861

## Appendix B: Design Discussion Summary

The design decisions in this document were derived from iterative discussion:

1. **Initial observation**: MemRL's core contribution is Q-value learning for retrieval
2. **First refinement**: Identified that h-mem's `recency`, `importance`, `outcome` overlap with Q-value
3. **Second refinement**: Proposed three orthogonal signals (Similarity, Q-value, Freshness)
4. **Third refinement**: Decided L1 Events don't need Q-values (too granular)
5. **Fourth refinement**: Layer-independent updates (avoid credit assignment complexity)
6. **Fifth refinement**: Q-value drives refine decisions (replaces heuristic success_rate checks)

This iterative process ensures the design is both theoretically grounded (from MemRL) and practically integrated with h-mem's existing architecture.
