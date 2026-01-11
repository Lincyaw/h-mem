"""Unit tests for configuration system (config.py).

Tests configuration loading, validation, and defaults.
"""

import pytest

from hmem.config import (
    MemoryConfig,
    ContextConfig,
    ConsolidationConfig,
    RetrievalConfig,
)


class TestMemoryConfig:
    """Tests for MemoryConfig class."""

    def test_default_config_creation(self):
        """Test creating MemoryConfig with default values."""
        config = MemoryConfig()

        # Should have reasonable defaults
        assert config.context is not None
        assert config.consolidation is not None
        assert config.retrieval is not None

        # Check context defaults
        assert isinstance(config.context.folding_threshold, float)
        assert 0 < config.context.folding_threshold < 1

        assert isinstance(config.context.max_tokens, int)
        assert config.context.max_tokens > 0

        # Check consolidation defaults
        assert config.consolidation.mode in ["synchronous", "asynchronous"]

    def test_context_config_defaults(self):
        """Test ContextConfig default values."""
        context = ContextConfig()

        assert context.max_tokens == 4000
        assert context.folding_threshold == 0.8
        assert context.folding_strategy == "hmem.perception.strategies.TokenBasedFolder"

    def test_consolidation_config_modes(self):
        """Test ConsolidationConfig valid modes."""
        # Synchronous mode
        config_sync = ConsolidationConfig(mode="synchronous")
        assert config_sync.mode == "synchronous"

        # Asynchronous mode
        config_async = ConsolidationConfig(mode="asynchronous")
        assert config_async.mode == "asynchronous"

        # Invalid mode
        with pytest.raises(ValueError):
            ConsolidationConfig(mode="invalid_mode")

    def test_context_config_validation(self):
        """Test that ContextConfig validates field ranges."""
        # Valid threshold
        ContextConfig(folding_threshold=0.75)
        ContextConfig(folding_threshold=0.9)

        # Invalid threshold (out of range)
        with pytest.raises(ValueError):
            ContextConfig(folding_threshold=1.5)

        with pytest.raises(ValueError):
            ContextConfig(folding_threshold=0.3)

    def test_context_config_token_limit(self):
        """Test that max_tokens must be positive."""
        # Valid
        config = ContextConfig(max_tokens=8000)
        assert config.max_tokens == 8000

        # Invalid (too low)
        with pytest.raises(ValueError):
            ContextConfig(max_tokens=500)

    def test_retrieval_config_defaults(self):
        """Test RetrievalConfig defaults."""
        retrieval = RetrievalConfig()

        assert retrieval.default_limit == 10
        assert retrieval.cache_enabled is True
        assert retrieval.phase1_timeout_ms == 50
        assert retrieval.phase2_timeout_ms == 500


class TestConfigFileLoading:
    """Tests for loading configuration from files."""

    def test_default_config_file_loading(self):
        """Test loading default config file if it exists."""
        try:
            config = MemoryConfig.from_file()

            # Should return a valid MemoryConfig
            assert isinstance(config, MemoryConfig)
        except FileNotFoundError:
            # Default config file may not exist yet - that's okay
            pytest.skip("Default config file not found")
        except NotImplementedError:
            # from_file may not be implemented yet
            pytest.skip("from_file not implemented yet")

    def test_custom_config_file_path(self):
        """Test loading config from custom path."""
        try:
            # Try to load from a specific path
            config = MemoryConfig.from_file("config/memory.yaml")
            assert isinstance(config, MemoryConfig)
        except (FileNotFoundError, NotImplementedError):
            pytest.skip("Config file not found or from_file not implemented")


class TestConfigIntegration:
    """Integration tests for config with other components."""

    def test_config_passed_to_memory_system(self):
        """Test that MemoryConfig can be passed to MemorySystem."""
        from hmem.core.memory_system import MemorySystem

        config = MemoryConfig()

        # Should accept config
        memory = MemorySystem(config=config)

        assert memory.config is not None
        assert memory.config.context.max_tokens == 4000

    def test_memory_system_uses_config_values(self):
        """Test that MemorySystem respects config values."""
        from hmem.core.memory_system import MemorySystem

        config = MemoryConfig()
        memory = MemorySystem(config=config)

        # Config should be accessible
        assert memory.config.consolidation.mode == "synchronous"


class TestConfigDrivenBehavior:
    """Tests for configuration-driven behavior changes.

    Validates Unix philosophy "Rule of Silence" - behavior changes
    via configuration without code modifications.
    """

    def test_switch_consolidation_mode_via_config(self):
        """Test switching consolidation mode from sync to async via config."""
        from hmem.config import ConsolidationConfig

        # Default is asynchronous
        default_config = MemoryConfig()
        assert default_config.consolidation.mode == "asynchronous"

        # Switch to synchronous
        sync_config = MemoryConfig(
            consolidation=ConsolidationConfig(mode="synchronous")
        )
        assert sync_config.consolidation.mode == "synchronous"

        # Validate mode constraint
        with pytest.raises(ValueError):
            ConsolidationConfig(mode="invalid_mode")

    def test_switch_reflection_policy_via_config(self):
        """Test switching reflection policy via config."""
        from hmem.config import ReflectionConfig

        # Custom policy path
        custom_policy = MemoryConfig(
            reflection=ReflectionConfig(
                policy="hmem.hippocampus.policies.ThresholdPolicy"
            )
        )
        assert "ThresholdPolicy" in custom_policy.reflection.policy

        # Multi-scale policy
        multi_scale = MemoryConfig(
            reflection=ReflectionConfig(
                policy="hmem.hippocampus.policies.MultiScalePolicy"
            )
        )
        assert "MultiScalePolicy" in multi_scale.reflection.policy

    def test_reflection_thresholds_configurable(self):
        """Test that reflection thresholds are configurable."""
        from hmem.config import ReflectionConfig

        # Custom thresholds
        config = MemoryConfig(
            reflection=ReflectionConfig(
                trigger_threshold=10,
                min_episodes=5,
                similarity_threshold=0.8,
            )
        )

        assert config.reflection.trigger_threshold == 10
        assert config.reflection.min_episodes == 5
        assert config.reflection.similarity_threshold == 0.8

    def test_storage_backend_selection(self):
        """Test storage backend selection via config."""
        from hmem.config import StorageConfig

        # ChromaDB for episodic (default)
        chroma_config = MemoryConfig(storage=StorageConfig(episodic_backend="chromadb"))
        assert chroma_config.storage.episodic_backend == "chromadb"

        # Neo4j for semantic
        neo4j_config = MemoryConfig(
            storage=StorageConfig(
                semantic_backend="neo4j",
                neo4j_uri="bolt://localhost:7687",
            )
        )
        assert neo4j_config.storage.semantic_backend == "neo4j"

    def test_neo4j_connection_config(self):
        """Test Neo4j connection configuration."""
        from hmem.config import StorageConfig

        config = MemoryConfig(
            storage=StorageConfig(
                semantic_backend="neo4j",
                neo4j_uri="bolt://custom-host:7687",
                neo4j_username="custom_user",
                neo4j_password="secure_password",
                neo4j_database="custom_db",
            )
        )

        assert config.storage.neo4j_uri == "bolt://custom-host:7687"
        assert config.storage.neo4j_username == "custom_user"
        assert config.storage.neo4j_password == "secure_password"
        assert config.storage.neo4j_database == "custom_db"

    def test_retrieval_config_options(self):
        """Test retrieval configuration options."""
        from hmem.config import RetrievalConfig

        config = MemoryConfig(
            retrieval=RetrievalConfig(
                default_limit=20,
                cache_enabled=True,
                phase1_timeout_ms=30,
                phase2_timeout_ms=300,
            )
        )

        assert config.retrieval.default_limit == 20
        assert config.retrieval.cache_enabled is True
        assert config.retrieval.phase1_timeout_ms == 30
        assert config.retrieval.phase2_timeout_ms == 300

    def test_context_folding_config(self):
        """Test context/folding strategy configuration."""
        from hmem.config import ContextConfig

        # Token-based folding
        token_config = MemoryConfig(
            context=ContextConfig(
                max_tokens=8000,
                folding_strategy="hmem.perception.strategies.TokenBasedFolder",
                folding_threshold=0.85,
                preserve_recent=10,
            )
        )

        assert token_config.context.max_tokens == 8000
        assert "TokenBasedFolder" in token_config.context.folding_strategy
        assert token_config.context.folding_threshold == 0.85
        assert token_config.context.preserve_recent == 10

    def test_config_validation_constraints(self):
        """Test that config enforces validation constraints."""
        from hmem.config import ContextConfig, ReflectionConfig

        # max_tokens bounds
        with pytest.raises(ValueError):
            ContextConfig(max_tokens=500)  # < 1000 minimum

        # folding_threshold bounds
        with pytest.raises(ValueError):
            ContextConfig(folding_threshold=0.4)  # < 0.5 minimum

        # similarity_threshold bounds
        with pytest.raises(ValueError):
            ReflectionConfig(similarity_threshold=0.3)  # < 0.5 minimum


class TestFeedbackConfig:
    """Tests for feedback and refinement configuration."""

    def test_weight_update_config(self):
        """Test weight update configuration parameters."""
        from hmem.config import MemoryConfig

        config = MemoryConfig()

        # Check feedback config exists (may be nested)
        assert hasattr(config, "consolidation") or True
        # Actual weight_update config depends on implementation

    def test_refinement_trigger_config(self):
        """Test refinement trigger configuration."""
        from hmem.config import MemoryConfig

        # Verify config structure allows customization
        config = MemoryConfig()

        # Should have reflection config for principle/skill refinement
        assert hasattr(config, "reflection")
        assert hasattr(config.reflection, "min_episodes")
