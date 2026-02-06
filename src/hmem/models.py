from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Single message in a conversation (similar to OpenAI's message structure).

    This represents one turn in a conversation between user and assistant.
    Follows the OpenAI API message format for compatibility.
    """

    role: Literal["system", "user", "assistant"] = Field(
        description="Role of the message sender"
    )
    content: str = Field(description="Message content")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="When the message was created"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Optional metadata (e.g., token_count, model)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "role": "user",
                "content": "What's the weather like?",
                "timestamp": "2026-01-10T10:00:00",
                "metadata": {"token_count": 5},
            }
        }
    }


class Conversation(BaseModel):
    """A sequence of messages representing a conversation session.

    This is the primary input format for the memory system.
    Conversations are at Level 0 (raw) in the hierarchical semantic graph
    and serve as the source for derived memories.
    """

    id: str | None = Field(
        default=None,
        description="Unique conversation identifier (auto-generated if not provided)",
    )
    messages: list[Message] = Field(
        description="List of messages in chronological order"
    )
    session_id: str = Field(
        description="Unique identifier for this conversation session"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Conversation timestamp (typically first message time)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Session-level metadata (e.g., user_id, topic)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "conv_abc123",
                "session_id": "session_123",
                "messages": [
                    {"role": "user", "content": "My name is Alice"},
                    {"role": "assistant", "content": "Nice to meet you, Alice!"},
                ],
                "metadata": {"user_id": "user_001"},
            }
        }
    }


class IndexProfile(BaseModel):
    """Index Profile - Q-value based memory utility profile (MemRL-inspired).

    Implements Monte Carlo style Q-value learning for memory ranking.
    Q-value represents learned utility: how useful this memory has been.

    Update rule: Q_new = Q_old + α(r - Q_old)
    Where α is learning rate, r is reward (1.0=success, 0.0=failure)

    Design rationale (from MemRL paper integration):
    - Replaces redundant signals (success_count, failure_count, weight)
    - Three orthogonal signals: Similarity + Q-value + Freshness
    - Q-value triggers refinement when low Q + high usage
    """

    # Core Q-value fields
    q_value: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Learned utility (MemRL Q-value)"
    )
    q_update_count: int = Field(
        default=0, ge=0, description="Number of Q-value updates (for confidence)"
    )

    # Time fields (for freshness calculation)
    created_at: datetime = Field(
        default_factory=datetime.now, description="When this profile was created"
    )
    last_used_at: datetime | None = Field(default=None, description="Last usage time")

    @property
    def confidence(self) -> float:
        """Confidence based on update count (20 updates = full confidence)."""
        return min(1.0, self.q_update_count / 20.0)

    @property
    def quality_score(self) -> float:
        """Quality score = q_value × confidence.

        Backward compatible property that combines Q-value with confidence.
        """
        return self.q_value * self.confidence

    @property
    def needs_refinement(self) -> bool:
        """Whether this memory needs refinement (Q-value based).

        Trigger: Low Q (<0.3) + High usage (≥5)
        Interpretation: frequently used but doesn't work well
        """
        return self.q_value < 0.3 and self.q_update_count >= 5

    @property
    def should_deprecate(self) -> bool:
        """Whether this memory should be deprecated (Q-value based).

        Trigger: Very low Q (<0.2) + High usage (≥10)
        Interpretation: seriously broken, consider removing
        """
        return self.q_value < 0.2 and self.q_update_count >= 10

    model_config = {
        "json_schema_extra": {
            "example": {
                "q_value": 0.75,
                "q_update_count": 12,
                "created_at": "2026-01-01T10:00:00",
                "last_used_at": "2026-01-10T15:30:00",
            }
        }
    }


class UsageRecord(BaseModel):
    """Usage Record - Records each memory usage.

    Stored in SQLite for usage tracking and association discovery.
    Extended with sequence information for pattern mining.
    """

    id: str = Field(description="Unique record ID")
    memory_id: str = Field(description="Memory ID")
    session_id: str = Field(description="Session ID")
    subtask_id: str | None = Field(
        default=None, description="Which subtask this usage belongs to"
    )
    sequence_position: int = Field(
        default=0, ge=0, description="Position in the session sequence"
    )
    query: str = Field(description="Query at recall time")
    rank_position: int = Field(
        ge=1, description="Rank position at recall time (1-based)"
    )
    outcome: Literal["success", "failure", "not_used", "unknown"] = Field(
        default="unknown", description="Usage outcome"
    )
    used_at: datetime = Field(default_factory=datetime.now, description="Usage time")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "usage_abc123",
                "memory_id": "mem_xyz789",
                "session_id": "session_001",
                "subtask_id": "subtask_1",
                "sequence_position": 0,
                "query": "How to scrape a website?",
                "rank_position": 1,
                "outcome": "success",
                "used_at": "2026-01-10T10:00:00",
            }
        }
    }


class Association(BaseModel):
    """Association - Discovered relationship between memories.

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
    support: int = Field(ge=1, description="Support count (occurrences)")
    discovered_at: datetime = Field(
        default_factory=datetime.now, description="Discovery time"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_id": "mem_001",
                "target_id": "mem_002",
                "relation_type": "COMPLEMENTS",
                "confidence": 0.85,
                "support": 5,
                "discovered_at": "2026-01-10T10:00:00",
            }
        }
    }


class SystemStats(BaseModel):
    """System statistics for evolution trigger decisions."""

    remember_count: int = Field(default=0, ge=0, description="Total remember calls")
    total_memories: int = Field(default=0, ge=0, description="Total memories stored")
    total_usage: int = Field(default=0, ge=0, description="Total usage records")
    last_evolution_at: datetime | None = Field(
        default=None, description="Last evolution time"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "remember_count": 100,
                "total_memories": 500,
                "total_usage": 1000,
                "last_evolution_at": "2026-01-10T10:00:00",
            }
        }
    }


class Memory(BaseModel):
    """A retrieved memory from the system with provenance tracking.

    This is what gets returned when recalling memories.
    Can represent different types: episodic (experiences), semantic (facts),
    skill (procedures), or principle (induced rules).

    Memory object is the core data unit of the system, containing three layers:
    1. Content layer: content (actual memory content)
    2. Metadata layer: source, timestamp, metadata (basic attributes)
    3. Index layer: index_profile (usage statistics for evolution triggers)

    Provenance fields enable building a hierarchical semantic graph where:
    - Raw memories (conversations) are at Level 0
    - Episodic events are at Level 1 (derived from conversations)
    - Semantic facts are at Level 2 (derived from events)
    - Principles are at Level 3 (induced from multiple memories)

    The 'source' field enables recall marking for feedback:
    - <memory>...</memory> for episodic
    - <fact>...</fact> for semantic
    - <skill>...</skill> for skill
    - <principle>...</principle> for principle
    """

    # === Core Fields ===
    id: str | None = Field(default=None, description="Unique memory identifier")
    content: str = Field(description="The memory content")
    score: float = Field(ge=0, le=1, description="Relevance score")
    source: Literal["episodic", "semantic", "skill", "principle"] = Field(
        description="Source type of the memory for recall marking"
    )
    timestamp: datetime = Field(description="When this memory was created")
    metadata: dict[str, Any] = Field(default_factory=dict)

    # === Provenance Fields ===
    parent_ids: list[str] = Field(
        default_factory=list,
        description="IDs of parent memories this was derived from",
    )
    derivation_type: (
        Literal[
            "extraction",  # Extracted from raw data
            "derivation",  # Derived from other memories
            "induction",  # Induced from multiple memories (principle/skill)
            "supersession",  # Supersedes old memory (semantic triple)
            "refinement",  # Refined from existing memory
            "split",  # Split from a coarse memory
            "merge",  # Merged from multiple memories
        ]
        | None
    ) = Field(
        default=None,
        description="How this memory was derived",
    )

    # === Index Fields ===
    index_profile: IndexProfile | None = Field(
        default=None,
        description="Index profile with usage statistics",
    )

    # === Version Fields ===
    version: int = Field(default=1, ge=1, description="Version number")
    is_deprecated: bool = Field(default=False, description="Whether deprecated")
    successor_id: str | None = Field(default=None, description="Successor version ID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "mem_abc123",
                "content": "User prefers dark mode",
                "score": 0.95,
                "source": "semantic",
                "timestamp": "2026-01-10T10:00:00",
                "metadata": {"session_id": "s1"},
                "parent_ids": ["conv_xyz789"],
                "derivation_type": "extraction",
                "index_profile": {
                    "q_value": 0.75,
                    "q_update_count": 5,
                },
                "version": 1,
                "is_deprecated": False,
                "successor_id": None,
            }
        }
    }


class Event(BaseModel):
    """Episodic event - business layer data model with provenance tracking.

    Events are derived from raw conversations (Level 0) and form Level 1
    in the hierarchical semantic graph.
    """

    id: str | None = Field(default=None, description="Unique event identifier")
    content: str = Field(description="Text description of the event")
    outcome: Literal["success", "failure", "unknown"] = Field(
        description="Outcome of the event"
    )
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = Field(
        default=None, description="Vector embedding for similarity search"
    )
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extended fields like session_id, user_query, etc.",
    )
    parent_ids: list[str] = Field(
        default_factory=list,
        description="IDs of source memories (e.g., conversation/message IDs)",
    )
    derivation_type: Literal["extraction", "derivation"] = Field(
        default="extraction",
        description="How this event was derived from parent memories",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "evt_abc123",
                "content": "User asked to write a web scraper. Attempted using requests.get() but got blocked.",
                "outcome": "failure",
                "tags": ["web_scraping", "debugging"],
                "metadata": {"session_id": "s1", "user_query": "write a scraper"},
                "parent_ids": ["conv_xyz789"],
                "derivation_type": "extraction",
            }
        }
    }


class ConsolidationResult(BaseModel):
    """Consolidation result statistics."""

    success: bool
    stored_events: int
    updated_facts: int
    conflicts_resolved: int
    index_updates: int = Field(default=0, ge=0, description="Updated index profiles")
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "stored_events": 5,
                "updated_facts": 3,
                "conflicts_resolved": 1,
                "index_updates": 2,
                "errors": [],
            }
        }
    }


class Principle(BaseModel):
    """Extracted principle with multi-evidence provenance.

    Principles are at Level 3 in the hierarchical semantic graph,
    induced from multiple Level 1/2 memories (events/facts).
    """

    id: str | None = Field(default=None, description="Unique principle identifier")
    content: str
    evidence_count: int = Field(
        description="Number of episodes supporting this principle"
    )
    confidence: float = Field(ge=0, le=1)
    embedding: list[float] | None = Field(
        default=None, description="Vector embedding for similarity search"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_ids: list[str] = Field(
        default_factory=list,
        description="IDs of evidence memories this principle was induced from",
    )
    derivation_type: Literal["induction"] = Field(
        default="induction",
        description="Principles are always induced from multiple memories",
    )

    # === Index Profile ===
    index_profile: IndexProfile = Field(
        default_factory=IndexProfile,
        description="Usage statistics for evolution triggers",
    )

    # === Version Fields ===
    version: int = Field(default=1, ge=1, description="Version number")
    is_deprecated: bool = Field(
        default=False, description="Whether superseded by a newer version"
    )
    successor_id: str | None = Field(
        default=None, description="ID of the successor version"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "prin_abc123",
                "content": "Data analysis tasks must start with data cleaning",
                "evidence_count": 5,
                "confidence": 0.85,
                "metadata": {"topic": "data_analysis"},
                "parent_ids": ["evt_001", "evt_002", "evt_003"],
                "derivation_type": "induction",
                "index_profile": {
                    "q_value": 0.8,
                    "q_update_count": 10,
                },
                "version": 1,
                "is_deprecated": False,
            }
        }
    }


class Skill(BaseModel):
    """Procedural skill induced from multiple similar Processes.

    Skills are at Layer 2 (derived knowledge). They are generalized
    procedures abstracted from multiple concrete Process instances.
    A Skill captures the common pattern across several similar experiences.

    Relationships:
        - (:Process)-[:INSTANCE_OF]->(:Skill)  # Processes that exemplify this skill
        - (:Skill)-[:GUIDED_BY]->(:Principle)   # High-level principles (sparse)
    """

    id: str | None = Field(default=None, description="Unique skill identifier")
    name: str = Field(description="Short skill name")
    description: str = Field(description="Human-readable description of the skill")
    trigger_pattern: str = Field(
        default="",
        description="Generalized trigger condition (abstracted from source Processes)",
    )
    action_template: str = Field(
        default="",
        description="Generalized action steps (abstracted from source Processes)",
    )
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = Field(
        default=None, description="Vector embedding for similarity search"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_process_ids: list[str] = Field(
        default_factory=list,
        description="IDs of Processes this skill was induced from",
    )

    # === Index Profile ===
    index_profile: IndexProfile = Field(
        default_factory=IndexProfile,
        description="Usage statistics for evolution triggers",
    )

    # === Version Fields ===
    version: int = Field(default=1, ge=1, description="Version number")
    is_deprecated: bool = Field(
        default=False, description="Whether superseded by a newer version"
    )
    successor_id: str | None = Field(
        default=None, description="ID of the successor version"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "skill_abc123",
                "name": "排查资源泄漏",
                "description": "调试任何系统时，先跑最小验证命令确认基础环节正常",
                "trigger_pattern": "系统出现资源泄漏或OOM",
                "action_template": "1. 确认外部依赖配置 2. 抓取profile/dump 3. 定位泄漏源",
                "source_process_ids": ["proc_001", "proc_002", "proc_003"],
                "index_profile": {
                    "q_value": 0.9,
                    "q_update_count": 10,
                },
                "version": 1,
                "is_deprecated": False,
            }
        }
    }


class ReflectionContext(BaseModel):
    """Reflection context information."""

    episode_count: int
    time_span_days: float
    avg_similarity: float = Field(
        description="Average similarity of memories within topic"
    )
    last_reflection_time: datetime | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "episode_count": 10,
                "time_span_days": 7.0,
                "avg_similarity": 0.8,
            }
        }
    }


# ============================================================================
# New Entity-Centric Memory Model
# ============================================================================


class Entity(BaseModel):
    """Entity node - represents a real-world entity with aliases for resolution.

    Entities are first-class citizens in the memory graph. They can be people,
    projects, organizations, concepts, or tools. The alias system enables
    entity resolution across different mentions (e.g., "my boss" = "张三").

    Example:
        >>> entity = Entity(
        ...     canonical_name="张三",
        ...     aliases=["我的上级", "领导", "老板"],
        ...     entity_type="PERSON"
        ... )
    """

    id: str | None = Field(default=None, description="Unique entity identifier")
    canonical_name: str = Field(description="Primary/canonical name for the entity")
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names/references for entity resolution",
    )
    entity_type: Literal["PERSON", "PROJECT", "ORGANIZATION", "CONCEPT", "TOOL"] = (
        Field(description="Type of entity")
    )
    embedding: list[float] | None = Field(
        default=None, description="Vector embedding for similarity search"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Indicates if this entity needs resolution (temporary entity)
    needs_resolution: bool = Field(
        default=False,
        description="True if this is a temporary entity awaiting merge",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "entity_abc123",
                "canonical_name": "张三",
                "aliases": ["我的上级", "领导"],
                "entity_type": "PERSON",
                "needs_resolution": False,
            }
        }
    }


class Attribute(BaseModel):
    """Attribute - a slot-value pair attached to an Entity.

    Attributes represent facts about entities with explicit cardinality:
    - single: Only one value valid at a time (e.g., job title, preferred theme)
    - multi: Multiple values can coexist (e.g., hobbies, skills)

    Scope controls temporal validity:
    - universal: Always valid across all contexts
    - project: Valid within a specific project
    - task: Valid only during a specific task/goal
    - session: Valid only within the originating conversation

    Conflict detection only applies to single-cardinality attributes.

    Example:
        >>> attr = Attribute(
        ...     entity_id="entity_abc",
        ...     slot="职位",
        ...     value="技术总监",
        ...     cardinality="single",
        ...     scope="universal"
        ... )
    """

    id: str | None = Field(default=None, description="Unique attribute identifier")
    entity_id: str = Field(description="ID of the entity this attribute belongs to")
    slot: str = Field(
        description="Attribute slot/key (e.g., '爱好', '职位', '偏好.主题')"
    )
    value: str = Field(description="Attribute value")
    cardinality: Literal["single", "multi"] = Field(
        default="single",
        description="single=one value at a time, multi=multiple values allowed",
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in this attribute"
    )

    # Temporal scope
    scope: Literal["universal", "project", "task", "session"] = Field(
        default="universal",
        description=(
            "Temporal scope: universal=always valid, project=within a project, "
            "task=during a specific task, session=only this conversation"
        ),
    )
    scope_context: str | None = Field(
        default=None,
        description="Context for non-universal scopes (e.g., project name, task description)",
    )

    embedding: list[float] | None = Field(
        default=None, description="Vector embedding for similarity search"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    parent_ids: list[str] = Field(
        default_factory=list, description="Source conversation/event IDs"
    )
    source_role: Literal["user", "assistant", "system"] | None = Field(
        default=None, description="Role of the message this was extracted from"
    )

    # Version fields for supersession
    version: int = Field(default=1, ge=1)
    is_superseded: bool = Field(default=False)

    # Q-value learning
    index_profile: IndexProfile = Field(default_factory=IndexProfile)

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "attr_abc123",
                "entity_id": "entity_xyz",
                "slot": "爱好",
                "value": "网球",
                "cardinality": "multi",
                "scope": "universal",
                "confidence": 0.9,
            }
        }
    }


class Process(BaseModel):
    """Process - represents a dynamic procedure (trigger -> action -> outcome).

    Processes capture procedural knowledge: what to do in certain situations.
    They can be linked to Facts/Entities they involve via INVOLVES relationships.

    Only generalizable processes should be stored - one-time debugging steps
    or project-specific workarounds should be filtered out during extraction.

    Multiple similar Processes can be abstracted into a Skill.

    Example:
        >>> process = Process(
        ...     trigger="遇到OOM错误",
        ...     action="先抓heap dump，再分析大对象",
        ...     outcome="定位内存泄漏源",
        ...     is_generalizable=True
        ... )
    """

    id: str | None = Field(default=None, description="Unique process identifier")
    trigger: str = Field(description="Situation/condition that triggers this process")
    action: str = Field(description="What to do (can be multi-step description)")
    outcome: str | None = Field(
        default=None, description="Expected result of following this process"
    )
    scope_entity_ids: list[str] = Field(
        default_factory=list,
        description="Entity IDs this process is scoped to (e.g., specific project)",
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in this process"
    )

    # Generalizability flag - only generalizable processes become skill candidates
    is_generalizable: bool = Field(
        default=True,
        description=(
            "Whether this process can be applied beyond its original context. "
            "False for one-time debugging steps or highly specific workarounds."
        ),
    )

    embedding: list[float] | None = Field(
        default=None, description="Trigger embedding for similarity matching"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    parent_ids: list[str] = Field(
        default_factory=list, description="Source conversation/event IDs"
    )
    involved_fact_ids: list[str] = Field(
        default_factory=list,
        description="Fact IDs that this process references/involves",
    )

    # Version and deprecation
    version: int = Field(default=1, ge=1)
    is_deprecated: bool = Field(default=False)

    # Q-value learning
    index_profile: IndexProfile = Field(default_factory=IndexProfile)

    # Link to induced skill (if any)
    skill_id: str | None = Field(
        default=None, description="ID of Skill this process is an instance of"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "proc_abc123",
                "trigger": "遇到OOM错误",
                "action": "先抓heap dump，再分析大对象",
                "outcome": "定位内存泄漏源",
                "scope_entity_ids": ["entity_hmem_project"],
                "is_generalizable": True,
                "confidence": 0.85,
            }
        }
    }
