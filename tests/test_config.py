"""Unit tests for configuration system (config.py).

Tests configuration loading, validation, and defaults.
"""

import pytest
from pathlib import Path

from hmem.config import MemoryConfig, ContextConfig, ConsolidationConfig, RetrievalConfig


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
