"""Configuration management for memory system.

Follows Unix Rule of Silence: all complexity hidden in config files.
Users can customize strategies without touching code.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from hmem.exceptions import ConfigurationError


class ContextConfig(BaseModel):
    """Context manager configuration (legacy - kept for backward compatibility)."""

    max_tokens: int = Field(
        default=4000, ge=1000, le=128000, description="Maximum context tokens"
    )
    folding_threshold: float = Field(
        default=0.8, ge=0.5, le=0.95, description="Trigger threshold"
    )
    preserve_recent: int = Field(
        default=5, ge=1, le=20, description="Recent messages to preserve"
    )


class RetrievalConfig(BaseModel):
    """Retrieval configuration."""

    default_limit: int = Field(
        default=10, ge=1, le=100, description="Default number of results"
    )
    enable_relevance_filter: bool = Field(
        default=True,
        description="Enable LLM-based relevance filtering to prevent returning irrelevant memories",
    )
    min_relevance_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score for LLM filter (0-1)",
    )


class ReflectionConfig(BaseModel):
    """Reflection configuration."""

    policy: str = Field(
        default="hmem.hippocampus.policies.MultiScalePolicy",
        description="Reflection policy class path",
    )
    trigger_threshold: int = Field(
        default=5,
        ge=3,
        le=100,
        description="Trigger reflection when episode count is multiple of this",
    )
    min_episodes: int = Field(
        default=3,
        ge=2,
        le=50,
        description="Minimum episodes required before reflection can trigger",
    )
    immediate_threshold: int = Field(
        default=3, description="Immediate reflection threshold (events)"
    )
    daily_interval: int = Field(
        default=24, description="Daily reflection interval (hours)"
    )
    weekly_interval: int = Field(
        default=168, description="Weekly reflection interval (hours)"
    )
    min_cluster_size: int = Field(
        default=3, description="Minimum episodes for clustering"
    )
    similarity_threshold: float = Field(
        default=0.75, ge=0.5, le=1.0, description="Clustering similarity threshold"
    )


class StorageConfig(BaseModel):
    """Storage configuration - Unified Neo4j backend."""

    # Neo4j configuration (unified backend for all memory types)
    neo4j_uri: str = Field(
        default="bolt://localhost:7687",
        description="Neo4j connection URI",
    )
    neo4j_username: str = Field(
        default="neo4j",
        description="Neo4j username",
    )
    neo4j_password: str = Field(
        default="testpassword123",
        description="Neo4j password",
    )
    neo4j_database: str = Field(
        default="neo4j",
        description="Neo4j database name",
    )


class EmbeddingConfig(BaseModel):
    """Embedding generation configuration."""

    model: str = Field(default="text-embedding-3-small", description="Embedding model")
    dimensions: int = Field(default=1536, description="Embedding dimensions")
    batch_size: int = Field(default=100, description="Batch size for embedding")


class LLMConfig(BaseModel):
    """LLM configuration for fact extraction and reflection."""

    model: str = Field(
        default="openai:deepseek-chat",
        description="LLM model identifier (format: provider:model_name or provider:endpoint_id)",
    )
    temperature: float = Field(
        default=0.1, ge=0.0, le=2.0, description="Sampling temperature"
    )
    extraction_enabled: bool = Field(
        default=True, description="Enable fact extraction from conversations"
    )
    reflection_enabled: bool = Field(
        default=True, description="Enable principle induction from episodes"
    )
    skill_generation_enabled: bool = Field(
        default=True, description="Enable automatic skill generation from principles"
    )


class QLearningConfig(BaseModel):
    """Q-Learning configuration (MemRL-inspired).

    Controls Q-value based memory ranking and refinement.
    """

    # Learning rate for Q-value updates
    alpha: float = Field(
        default=0.1,
        ge=0.01,
        le=1.0,
        description="Learning rate (0.1 = smooth, 0.3 = fast)",
    )

    # Ranking weights (must sum to 1.0)
    similarity_weight: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Weight for semantic similarity"
    )
    q_weight: float = Field(
        default=0.35, ge=0.0, le=1.0, description="Weight for Q-value (learned utility)"
    )
    freshness_weight: float = Field(
        default=0.15, ge=0.0, le=1.0, description="Weight for freshness (time decay)"
    )

    # Freshness decay
    freshness_halflife_days: float = Field(
        default=30.0, ge=1.0, le=365.0, description="Days for freshness to decay to 0.5"
    )

    # Refinement triggers
    refine_q_threshold: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Q below this + high usage = refine"
    )
    refine_min_usage: int = Field(
        default=5, ge=1, description="Minimum updates before considering refine"
    )
    deprecate_q_threshold: float = Field(
        default=0.2, ge=0.0, le=1.0, description="Q below this = deprecation candidate"
    )
    deprecate_min_usage: int = Field(
        default=10, ge=1, description="Minimum updates for deprecation"
    )

    # Q-value inheritance on refine
    inheritance_q_decay: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Inherit this fraction of old Q-value"
    )
    inheritance_confidence_decay: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Inherit this fraction of update count"
    )


class AgentConfig(BaseModel):
    """ReAct Agent Loop configuration.

    Controls the agent's iteration limits, timeouts, and error handling.
    """

    max_iterations: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum ReAct cycles before stopping",
    )
    timeout_seconds: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Maximum execution time in seconds",
    )
    stuck_threshold: int = Field(
        default=3,
        ge=2,
        le=10,
        description="Repeated identical actions before considering stuck",
    )
    max_format_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum attempts to recover from LLM format errors",
    )
    tool_retry_default: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Default retry count for retriable tool errors",
    )
    enable_parallel_tools: bool = Field(
        default=True,
        description="Execute independent tool calls in parallel",
    )
    max_workers: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximum concurrent tool executions",
    )


class SkillsConfig(BaseModel):
    """Skills system configuration.

    Controls the self-bootstrapping skill system behavior.
    """

    # Directory paths (relative to project root or absolute)
    skills_dir: str = Field(
        default="",
        description="Path to skills directory. Empty = package default (src/hmem/skills)",
    )

    # Safety limits
    min_processes_for_creation: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Minimum similar processes required to create a skill",
    )
    max_creations_per_hour: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum skills that can be created per hour",
    )
    suspend_q_threshold: float = Field(
        default=0.1,
        ge=0.0,
        le=0.5,
        description="Q-value below which skills are auto-suspended",
    )
    min_q_updates_for_suspend: int = Field(
        default=5,
        ge=1,
        description="Minimum Q-value updates before considering suspension",
    )

    # Feature flags
    auto_induction_enabled: bool = Field(
        default=True,
        description="Enable automatic skill induction from processes",
    )
    file_system_output_enabled: bool = Field(
        default=True,
        description="Write induced skills to file system (SKILL.md files)",
    )


class MemoryConfig(BaseModel):
    """Memory system main configuration."""

    context: ContextConfig = Field(default_factory=ContextConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    reflection: ReflectionConfig = Field(default_factory=ReflectionConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    q_learning: QLearningConfig = Field(default_factory=QLearningConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    log_level: str = Field(default="INFO", description="Log level")
    enable_diagnostics: bool = Field(
        default=False, description="Enable diagnostic features (Phase 3)"
    )

    @classmethod
    def from_file(cls, config_path: str = "config/memory.yaml") -> "MemoryConfig":
        """Load configuration from file."""
        return ConfigManager.load_from_file(config_path)


class ConfigManager:
    """Configuration manager."""

    @staticmethod
    def load_from_file(config_path: str) -> MemoryConfig:
        """Load configuration from YAML file."""
        path = Path(config_path)

        if not path.exists():
            raise ConfigurationError(f"Config file not found: {config_path}")

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data is None:
                data = {}

            return MemoryConfig(**data)

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML format: {e}") from e
        except Exception as e:
            raise ConfigurationError(f"Failed to load config: {e}") from e

    @staticmethod
    def get_default_config() -> MemoryConfig:
        """Get default configuration."""
        return MemoryConfig()

    @staticmethod
    def save_to_file(config: MemoryConfig, config_path: str) -> None:
        """Save configuration to file."""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            data = config.model_dump()
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
