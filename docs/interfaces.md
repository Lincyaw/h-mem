# **Key Interface Definitions**

Based on the principle of simplicity, interface design follows the Unix philosophy of "less is more". All data exchange uses Pydantic models to ensure type safety.

## **Data Models**

### **Memory (Single Memory) - Extended with Index Support**

```python
from typing import Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime

class Memory(BaseModel):
    """Single Memory - Supports provenance chain and index profile

    Memory object is the core data unit of the system, containing three layers:
    1. Content layer: content (actual memory content)
    2. Metadata layer: source, timestamp, metadata (basic attributes)
    3. Index layer: index_profile (usage statistics for evolution triggers)

    IndexProfile is the key to "better with use":
    - Records usage outcomes (success/failure)
    - Supports evolution triggers based on statistics
    - Enables exploration-exploitation balance
    """
    # === Core Fields ===
    id: str | None = Field(default=None, description="Unique Memory Identifier")
    content: str = Field(description="Memory content")
    score: float = Field(ge=0, le=1, description="Relevance score")
    source: Literal["episodic", "semantic", "skill", "principle"] = Field(
        description="Source type for recall tagging and feedback tracing"
    )
    timestamp: datetime
    metadata: dict = Field(default_factory=dict)

    # === Provenance Fields ===
    parent_ids: list[str] = Field(
        default_factory=list,
        description="Parent memory IDs"
    )
    derivation_type: Literal[
        "extraction",   # Extracted from raw data
        "derivation",   # Derived from other memories
        "induction",    # Induced from multiple memories (principle/skill)
        "supersession", # Supersedes old memory (semantic triple)
        "refinement",   # Refined from existing memory
        "split",        # Split from a coarse memory
        "merge"         # Merged from multiple memories
    ] | None = Field(default=None)

    # === Index Fields ===
    index_profile: "IndexProfile | None" = Field(
        default=None,
        description="Index profile with usage statistics"
    )

    # === Version Fields ===
    version: int = Field(default=1, description="Version number")
    is_deprecated: bool = Field(default=False, description="Whether deprecated")
    successor_id: str | None = Field(default=None, description="Successor version ID")
```

### **IndexProfile - Usage Statistics**

```python
class IndexProfile(BaseModel):
    """Index Profile - Memory usage statistics

    Stored in SQLite for high-frequency read/write operations.
    Supports:
    1. Confidence calculation: success_rate with sample size consideration
    2. Evolution triggers: based on usage_count and success_rate
    3. Exploration bonus: favor low-usage memories for exploration
    """
    # === Basic Statistics ===
    usage_count: int = Field(default=0, description="Total usage count")
    success_count: int = Field(default=0, description="Success count")
    failure_count: int = Field(default=0, description="Failure count")
    weight: float = Field(default=1.0, ge=0, le=10, description="Composite weight [0-10]")

    # === Time Statistics ===
    first_used_at: datetime | None = Field(default=None, description="First usage time")
    last_used_at: datetime | None = Field(default=None, description="Last usage time")
    last_success_at: datetime | None = Field(default=None, description="Last success time")

    # === Computed Properties ===
    @property
    def success_rate(self) -> float:
        """Success rate"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    @property
    def confidence(self) -> float:
        """Confidence based on sample size (20 uses = full confidence)"""
        return min(1.0, self.usage_count / 20.0)

    @property
    def quality_score(self) -> float:
        """Quality score = success_rate × confidence"""
        return self.success_rate * self.confidence

    @property
    def needs_refinement(self) -> bool:
        """Whether this memory needs refinement"""
        # Trigger conditions:
        # 1. Used 10+ times but success rate < 0.5
        # 2. Used 20+ times but success rate < 0.3 (should deprecate)
        if self.usage_count >= 10 and self.success_rate < 0.5:
            return True
        return False

    @property
    def should_deprecate(self) -> bool:
        """Whether this memory should be deprecated"""
        return self.usage_count >= 20 and self.success_rate < 0.3
```

### **UsageRecord - Single Usage Record**

```python
class UsageRecord(BaseModel):
    """Usage Record - Records each memory usage

    Stored in SQLite for usage tracking and association discovery.
    Extended with sequence information for pattern mining.
    """
    id: str = Field(description="Unique record ID")
    memory_id: str = Field(description="Memory ID")
    session_id: str = Field(description="Session ID")

    # === Sequence Information ===
    subtask_id: str | None = Field(
        default=None,
        description="Which subtask this usage belongs to"
    )
    sequence_position: int = Field(
        default=0,
        description="Position in the session sequence"
    )

    # === Usage Information ===
    query: str = Field(description="Query at recall time")
    rank_position: int = Field(description="Rank position at recall time (1-based)")
    outcome: Literal["success", "failure", "not_used", "unknown"] = Field(
        default="unknown",
        description="Usage outcome"
    )

    # === Timestamp ===
    used_at: datetime = Field(default_factory=datetime.now)
```

### **Association - Discovered Relationship**

```python
class Association(BaseModel):
    """Association - Discovered relationship between memories

    Types:
    - CAUSES: A failed -> B succeeded (A causes trying B)
    - COMPLEMENTS: A and B used together successfully
    - FOLLOWED_BY: A used in subtask_i, B used in subtask_i+1
    """
    source_id: str = Field(description="Source memory ID")
    target_id: str = Field(description="Target memory ID")
    relation_type: Literal["CAUSES", "COMPLEMENTS", "FOLLOWED_BY"] = Field(
        description="Relationship type"
    )
    confidence: float = Field(ge=0, le=1, description="Confidence (0-1)")
    support: int = Field(description="Support count (occurrences)")
    discovered_at: datetime = Field(default_factory=datetime.now)
```

---

### **Event (Episodic Event)**

```python
class Event(BaseModel):
    """Episodic Event - Business Layer Data Model"""
    id: str | None = Field(default=None, description="Unique Event Identifier")
    content: str = Field(description="Event text description")
    outcome: str = Field(description="Event outcome: success/failure/unknown")
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)
    parent_ids: list[str] = Field(default_factory=list)
    derivation_type: Literal["extraction", "derivation"] = "extraction"
```

### **Principle**

```python
class Principle(BaseModel):
    """Extracted Principle - Supports version evolution and usage feedback"""
    id: str | None = None
    content: str
    evidence_count: int
    confidence: float = Field(ge=0, le=1)
    created_at: datetime = Field(default_factory=datetime.now)
    parent_ids: list[str] = Field(default_factory=list)
    derivation_type: Literal["induction"] = "induction"

    # === Index Profile ===
    index_profile: IndexProfile = Field(default_factory=IndexProfile)

    # === Version Fields ===
    version: int = 1
    is_deprecated: bool = False
    successor_id: str | None = None
```

### **Skill**

```python
class Skill(BaseModel):
    """Procedural Skill - Supports template and feedback optimization"""
    id: str | None = None
    name: str
    trigger_pattern: str
    code_template: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    parent_ids: list[str] = Field(default_factory=list)
    derivation_type: Literal["induction"] = "induction"

    # === Index Profile ===
    index_profile: IndexProfile = Field(default_factory=IndexProfile)

    # === Version Fields ===
    version: int = 1
    is_deprecated: bool = False
    successor_id: str | None = None
```

### **SemanticTriple**

```python
class SemanticTriple(BaseModel):
    """Semantic Triple - Supports conflict resolution and version evolution"""
    id: str | None = None
    subject: str
    predicate: str
    object: str
    weight: float = 1.0
    version: int = 1
    parent_ids: list[str] = Field(default_factory=list)
    derivation_type: Literal["extraction", "derivation", "supersession"] = "extraction"

    # Conflict resolution fields
    is_superseded: bool = False
    superseded_by: str | None = None
```

### **ConsolidationResult**

```python
class ConsolidationResult(BaseModel):
    """Consolidation Result Statistics"""
    success: bool
    stored_events: int
    updated_facts: int
    conflicts_resolved: int
    index_updates: int = Field(default=0, description="Updated index profiles")
    errors: list[str] = []
```

### **Message & Conversation Models**

```python
class Message(BaseModel):
    """Single Message"""
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)


class Conversation(BaseModel):
    """Conversation Session"""
    session_id: str
    messages: list[Message]
    started_at: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)
```

---

## **Exceptions**

```python
class MemoryError(Exception):
    """Memory System Base Exception"""
    pass

class RetrievalError(MemoryError):
    """Retrieval Failed"""
    pass

class ConsolidationError(MemoryError):
    """Consolidation Failed"""
    pass

class ReflectionError(MemoryError):
    """Reflection Failed"""
    pass

class EvolutionError(MemoryError):
    """Memory Evolution Failed"""
    pass
```

---

## **Core Interface: MemorySystem**

```python
from abc import ABC, abstractmethod
from typing import Iterator, Any

class MemorySystemInterface(ABC):
    """Cognitive Memory System Core Interface [Core - Stable Interface]

    Follows Unix philosophy: simple interface, sophisticated implementation.
    Users only need to understand two core operations: memory storage and retrieval.
    All intelligent decisions (consolidation, reflection, evolution) are internal strategies.
    """

    @abstractmethod
    def remember(
        self,
        conversation: Conversation | list[Message],
    ) -> str:
        """
        Store conversation into memory system (single write interface).

        Behavior:
        1. Async consolidation: Extract events and facts
        2. Async feedback collection: Extract feedback from XML tags
        3. Async index update: Update IndexProfile, check evolution triggers

        Args:
            conversation: Conversation object or list of Message objects

        Returns:
            session_id: Unique identifier for this conversation session

        Raises:
            MemoryError: Raised when storage fails
        """
        pass

    @abstractmethod
    def recall(
        self,
        query: str | Message | Conversation,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> Iterator[Memory]:
        """
        Retrieve relevant memories (single read interface).

        Behavior:
        1. Candidate retrieval: Vector similarity + graph queries
        2. Hybrid ranking: similarity + recency + importance + quality_score
        3. Exploration-exploitation: Adaptive exploration rate for low-usage memories
        4. Usage recording: Create UsageRecord for each recall

        Args:
            query: Search query (str/Message/Conversation)
            limit: Maximum results (1-100)
            filters: Optional filter conditions

        Yields:
            Memory: Memories with index_profile attached

        Performance:
            - First batch (≤3 results): P95 < 50ms
            - Full results: P95 < 500ms
        """
        pass
```

---

## **Storage Layer Interfaces**

### **EpisodicStoreProtocol**

```python
class EpisodicStoreProtocol(Protocol):
    """Episodic Store Protocol - Extended with usage tracking"""

    def add(self, event: Event) -> str:
        """Add event, return event_id"""
        ...

    def search(
        self,
        query: str,
        limit: int = 10,
        filters: dict | None = None
    ) -> list[Memory]:
        """Vector similarity search"""
        ...

    def record_usage(self, usage: UsageRecord) -> None:
        """Record memory usage"""
        ...

    def get_usage_history(
        self,
        memory_id: str,
        limit: int = 100
    ) -> list[UsageRecord]:
        """Get usage history"""
        ...
```

### **SemanticStoreProtocol**

```python
class SemanticStoreProtocol(Protocol):
    """Semantic Store Protocol - Extended with association storage"""

    def add_or_update(
        self,
        triple: SemanticTriple,
        parent_ids: list[str] | None = None
    ) -> tuple[bool, int]:
        """Add or update triple"""
        ...

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Full-text search + graph traversal"""
        ...

    def add_association(self, association: Association) -> None:
        """Add discovered association"""
        ...

    def get_associations(
        self,
        memory_id: str,
        relation_type: str | None = None
    ) -> list[Association]:
        """Get associations for a memory"""
        ...

    def get_complements(self, memory_id: str) -> list[Memory]:
        """Get complementary memories"""
        ...

    def get_causal_chain(
        self,
        memory_id: str,
        max_depth: int = 3
    ) -> list[Memory]:
        """Get causal chain from a memory"""
        ...
```

---

## **Strategy Interfaces**

### **RetrievalRanker**

```python
class RetrievalRanker(ABC):
    """Retrieval Result Ranking Strategy"""

    @abstractmethod
    def rank(
        self,
        candidates: list[Memory],
        query: str,
    ) -> list[Memory]:
        """Sort candidate memories

        Args:
            candidates: Candidate memories with initial scores
            query: Original query

        Returns:
            Sorted memories by relevance
        """
        pass


class HybridRankerWithExploration(RetrievalRanker):
    """Hybrid Ranker with Adaptive Exploration

    Ranking formula:
    score = w1*similarity + w2*recency + w3*importance + w4*quality_score + w5*exploration_bonus

    Exploration mechanism:
    - Adaptive rate: 20% initially, decays to 5% as knowledge base matures
    - Low-usage memories get exploration bonus
    """

    def __init__(
        self,
        similarity_weight: float = 0.4,
        recency_weight: float = 0.15,
        importance_weight: float = 0.15,
        quality_weight: float = 0.2,
        exploration_weight: float = 0.1,
        initial_exploration_rate: float = 0.2,
        min_exploration_rate: float = 0.05,
    ):
        self.weights = {
            "similarity": similarity_weight,
            "recency": recency_weight,
            "importance": importance_weight,
            "quality": quality_weight,
            "exploration": exploration_weight
        }
        self.initial_exploration_rate = initial_exploration_rate
        self.min_exploration_rate = min_exploration_rate

    def get_exploration_rate(self, total_usage: int) -> float:
        """Adaptive exploration rate"""
        decay_factor = total_usage / 1000
        rate = self.initial_exploration_rate / (1 + decay_factor)
        return max(self.min_exploration_rate, rate)

    def rank(self, candidates: list[Memory], query: str) -> list[Memory]:
        """Rank with exploration bonus"""
        import math
        import random

        for mem in candidates:
            # Quality score from IndexProfile
            quality_score = 0.5
            exploration_bonus = 0.0
            if mem.index_profile:
                quality_score = mem.index_profile.quality_score
                # Exploration bonus: lower usage = higher bonus
                exploration_bonus = 1.0 / (1 + math.log(1 + mem.index_profile.usage_count))

            mem.score = (
                self.weights["similarity"] * mem.score +
                self.weights["recency"] * self._recency_score(mem) +
                self.weights["importance"] * self._importance_score(mem) +
                self.weights["quality"] * quality_score +
                self.weights["exploration"] * exploration_bonus
            )

        return sorted(candidates, key=lambda m: m.score, reverse=True)
```

### **AssociationDiscoveryStrategy**

```python
class AssociationDiscoveryStrategy(ABC):
    """Association Discovery Strategy Interface - Extensible design"""

    @abstractmethod
    def discover(
        self,
        usage_records: list[UsageRecord],
        min_support: int = 3
    ) -> list[Association]:
        """
        Discover associations from usage records

        Args:
            usage_records: Usage record list
            min_support: Minimum support (occurrence count)

        Returns:
            Discovered association list
        """
        pass
```

### **EvolutionTriggerHook**

```python
class EvolutionTriggerHook(ABC):
    """Evolution Trigger Hook - Configurable trigger strategy"""

    @abstractmethod
    def should_trigger(self, stats: "SystemStats") -> bool:
        """Determine if evolution should be triggered"""
        pass


class BatchEvolutionHook(EvolutionTriggerHook):
    """Batch trigger: every N remembers"""

    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size

    def should_trigger(self, stats: "SystemStats") -> bool:
        return stats.remember_count % self.batch_size == 0


class SystemStats(BaseModel):
    """System statistics for trigger decisions"""
    remember_count: int = 0
    total_memories: int = 0
    total_usage: int = 0
    last_evolution_at: datetime | None = None
```

---

**Related Documents:**
- [System Design Philosophy](design.md) - Design philosophy and core concepts
- [Component Details](components.md) - Component responsibilities and implementations
- [Core Workflows](workflows.md) - Index building and evolution workflows
- [Memory Provenance](provenance.md) - Memory provenance and hierarchical semantic graph
