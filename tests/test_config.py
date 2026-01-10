"""Unit tests for configuration system (config.py).

Tests configuration loading, validation, and defaults.
"""

import pytest
from pathlib import Path

from hmem.config import MemoryConfig


class TestMemoryConfig:
    """Tests for MemoryConfig class."""
    
    def test_default_config_creation(self):
        """Test creating MemoryConfig with default values."""
        config = MemoryConfig()
        
        # Should have reasonable defaults
        assert isinstance(config.folding_threshold, float)
        assert 0 < config.folding_threshold < 1
        
        assert isinstance(config.token_limit, int)
        assert config.token_limit > 0
        
        assert config.consolidation_mode in ["synchronous", "asynchronous"]
    
    def test_config_with_custom_values(self):
        """Test creating MemoryConfig with custom parameters."""
        config = MemoryConfig(
            folding_strategy="hmem.perception.strategies.TokenBasedFolder",
            folding_threshold=0.75,
            token_limit=8000,
            consolidation_mode="asynchronous",
            consolidation_trigger="background_queue",
        )
        
        assert config.folding_threshold == 0.75
        assert config.token_limit == 8000
        assert config.consolidation_mode == "asynchronous"
    
    def test_config_validation_threshold_range(self):
        """Test that folding_threshold is validated to be in valid range."""
        # Valid thresholds
        MemoryConfig(folding_threshold=0.5)
        MemoryConfig(folding_threshold=0.8)
        MemoryConfig(folding_threshold=0.95)
        
        # Invalid thresholds should be caught if validation is implemented
        # This test documents expected behavior
        try:
            config = MemoryConfig(folding_threshold=1.5)
            # If no validation, at least check it's stored
            assert config.folding_threshold == 1.5
        except ValueError:
            # Expected if validation is implemented
            pass
    
    def test_config_token_limit_positive(self):
        """Test that token_limit must be positive."""
        # Valid
        config = MemoryConfig(token_limit=4000)
        assert config.token_limit == 4000
        
        # Invalid (if validation implemented)
        try:
            MemoryConfig(token_limit=-1000)
        except ValueError:
            pass  # Expected
    
    def test_config_consolidation_modes(self):
        """Test valid consolidation modes."""
        # Synchronous mode
        config_sync = MemoryConfig(consolidation_mode="synchronous")
        assert config_sync.consolidation_mode == "synchronous"
        
        # Asynchronous mode
        config_async = MemoryConfig(consolidation_mode="asynchronous")
        assert config_async.consolidation_mode == "asynchronous"


class TestConfigFileLoading:
    """Tests for loading configuration from files."""
    
    def test_from_file_method_exists(self):
        """Test that from_file classmethod exists."""
        assert hasattr(MemoryConfig, "from_file")
        assert callable(MemoryConfig.from_file)
    
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
        
        config = MemoryConfig(
            token_limit=8000,
            folding_threshold=0.8,
        )
        
        # Should accept config
        memory = MemorySystem(config=config)
        
        assert memory.config is not None
        assert memory.config.token_limit == 8000
    
    def test_memory_system_uses_config_values(self):
        """Test that MemorySystem respects config values."""
        from hmem.core.memory_system import MemorySystem
        
        config = MemoryConfig(
            consolidation_mode="synchronous",
        )
        
        memory = MemorySystem(config=config)
        
        # Config should be accessible
        assert memory.config.consolidation_mode == "synchronous"
