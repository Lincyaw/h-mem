"""Unit tests for configuration system (config.py).

Tests configuration loading, validation, and defaults.
"""

import pytest

from hmem.config import (
    MemoryConfig,
    ContextConfig,
)


class TestMemoryConfig:
    """Tests for MemoryConfig class."""

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


class TestConfigFileLoading:
    """Tests for loading configuration from files."""

    def test_default_config_file_loading(self):
        """Test loading default config file if it exists."""
        try:
            config = MemoryConfig.from_file()
            assert isinstance(config, MemoryConfig)
        except FileNotFoundError:
            pytest.skip("Default config file not found")
        except NotImplementedError:
            pytest.skip("from_file not implemented yet")


class TestConfigIntegration:
    """Integration tests for config with other components."""

    def test_config_passed_to_memory_system(self):
        """Test that MemoryConfig can be passed to MemorySystem."""
        from hmem.core.memory_system import MemorySystem

        config = MemoryConfig()
        memory = MemorySystem(config=config)

        assert memory.config is not None
        assert memory.config.context.max_tokens == 4000


class TestConfigDrivenBehavior:
    """Tests for configuration-driven behavior changes."""

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
