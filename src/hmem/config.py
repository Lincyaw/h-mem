"""Configuration management for memory system.

Follows Unix Rule of Silence: all complexity hidden in config files.
Users can customize strategies without touching code.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from hmem.exceptions import ConfigurationError


class ConsolidationConfig(BaseModel):
    """Consolidation configuration."""

    mode: str = Field(
        default="synchronous", description="consolidation: synchronous/asynchronous"
    )
    trigger: str = Field(
        default="on_session_end",
        description="trigger mode: on_session_end/background_queue",
    )
    queue_timeout: int = Field(default=30, description="timeout (s)")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = ["synchronous", "asynchronous"]
        if v not in allowed:
            raise ValueError(f"mode must be one of {allowed}")
        return v


class ContextConfig(BaseModel):
    """Context manager configuration."""

    max_tokens: int = Field(
        default=4000, ge=1000, le=128000, description="Maximum context tokens"
    )
    folding_strategy: str = Field(
        default="hmem.perception.strategies.TokenBasedFolder",
        description="Folding strategy class path",
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
    cache_enabled: bool = Field(default=True, description="Enable cache")
    phase1_timeout_ms: int = Field(
        default=50, description="Phase 1 fast retrieval timeout (ms)"
    )
    phase2_timeout_ms: int = Field(
        default=500, description="Phase 2 deep retrieval timeout (ms)"
    )
    adaptive_threshold: bool = Field(
        default=False, description="Enable adaptive threshold (Phase 3)"
    )


class ReflectionConfig(BaseModel):
    """Reflection configuration."""

    policy: str = Field(
        default="hmem.hippocampus.policies.MultiScalePolicy",
        description="Reflection policy class path",
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
    """Storage configuration."""

    episodic_backend: str = Field(
        default="chromadb", description="Episodic storage backend"
    )
    episodic_path: str = Field(
        default="./.hmem/episodic", description="Episodic storage path"
    )

    semantic_backend: str = Field(
        default="sqlite", description="Semantic storage backend"
    )
    semantic_path: str = Field(
        default="./.hmem/semantic.db", description="Semantic storage path"
    )

    skill_backend: str = Field(default="sqlite", description="Skill storage backend")
    skill_path: str = Field(
        default="./.hmem/skills.db", description="Skill storage path"
    )


class LockConfig(BaseModel):
    """Lock configuration for distributed coordination."""

    backend: str = Field(
        default="file:///tmp/h-mem-locks",
        description="Lock backend: file:// or redis://",
    )
    timeout: float = Field(
        default=10.0, ge=1.0, le=60.0, description="Lock timeout (seconds)"
    )


class EmbeddingConfig(BaseModel):
    """Embedding generation configuration."""

    model: str = Field(default="text-embedding-3-small", description="Embedding model")
    dimensions: int = Field(default=1536, description="Embedding dimensions")
    batch_size: int = Field(default=100, description="Batch size for embedding")


class MemoryConfig(BaseModel):
    """Memory system main configuration."""

    context: ContextConfig = Field(default_factory=ContextConfig)
    consolidation: ConsolidationConfig = Field(default_factory=ConsolidationConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    reflection: ReflectionConfig = Field(default_factory=ReflectionConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    lock: LockConfig = Field(default_factory=LockConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)

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
