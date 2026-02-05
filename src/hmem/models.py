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
    """Procedural skill with usage feedback tracking.

    Skills are at Level 3 in the hierarchical semantic graph,
    induced from multiple successful execution examples.
    """

    id: str | None = Field(default=None, description="Unique skill identifier")
    name: str = Field(description="Unique skill name")
    trigger_pattern: str = Field(
        description="Activation condition (supports | for alternatives)"
    )
    code_template: dict[str, Any] = Field(
        description="Parameterized template with steps and parameters"
    )
    description: str | None = Field(
        default=None, description="Human-readable description"
    )
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = Field(
        default=None, description="Vector embedding for similarity search"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_ids: list[str] = Field(
        default_factory=list,
        description="IDs of evidence memories this skill was induced from",
    )
    derivation_type: Literal["induction", "extraction"] = Field(
        default="induction",
        description="Skills are typically induced from multiple examples",
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
                "name": "web_scraping_selenium",
                "trigger_pattern": "scrape|crawl|extract data from website",
                "code_template": {
                    "steps": [
                        "Initialize Selenium WebDriver",
                        "Navigate to {url}",
                        "Wait for {selector}",
                        "Extract content",
                    ],
                    "params": ["url", "selector"],
                },
                "description": "Use Selenium for dynamic website scraping",
                "metadata": {"category": "web_scraping"},
                "parent_ids": ["evt_001", "evt_002"],
                "derivation_type": "induction",
                "index_profile": {
                    "q_value": 0.9,
                    "q_update_count": 10,
                },
                "version": 1,
                "is_deprecated": False,
            }
        }
    }


class SemanticTriple(BaseModel):
    """Semantic triple with provenance tracking.

    Semantic triples are at Level 2 in the hierarchical semantic graph,
    derived from events or conversations.

    Now includes IndexProfile for Q-value based learning (MemRL integration).
    Also includes importance and confidence for intelligent memory filtering.
    """

    id: str | None = Field(default=None, description="Unique triple identifier")
    subject: str
    predicate: str
    object: str
    weight: float = Field(default=1.0, ge=0)
    version: int = Field(default=1)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    parent_ids: list[str] = Field(
        default_factory=list,
        description="IDs of source memories this fact was derived from",
    )
    derivation_type: Literal["extraction", "derivation", "supersession"] = Field(
        default="extraction",
        description="How this triple was derived",
    )
    source_role: Literal["user", "assistant", "system"] | None = Field(
        default=None,
        description="Role of the message this fact was extracted from (user/assistant/system)",
    )
    embedding: list[float] | None = Field(
        default=None, description="Vector embedding for similarity search"
    )

    # === Importance and Confidence (NEW: for intelligent filtering) ===
    importance: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Importance level 1-5 (1=trivial, 5=critical)",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in this fact (0=uncertain, 1=certain)",
    )

    # === Index Profile (NEW: Q-value based) ===
    index_profile: IndexProfile = Field(
        default_factory=IndexProfile,
        description="Q-value based utility profile for learning",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "triple_abc123",
                "subject": "User",
                "predicate": "PREFERS",
                "object": "dark_mode",
                "weight": 1.0,
                "parent_ids": ["conv_xyz789"],
                "derivation_type": "extraction",
                "source_role": "user",
                "importance": 4,
                "confidence": 1.0,
                "index_profile": {
                    "q_value": 0.75,
                    "q_update_count": 5,
                },
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
