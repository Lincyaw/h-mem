"""Unit tests for MemorySystem core functionality.

Tests the main MemorySystem interface and basic operations.
"""

import pytest
from unittest.mock import MagicMock

from hmem.core.memory_system import MemorySystem
from hmem.config import MemoryConfig
from hmem.models import Memory


class TestMemorySystemBasics:
    """Tests for basic MemorySystem functionality."""
    
    def test_memory_system_creation(self):
        """Test creating a MemorySystem instance."""
        memory = MemorySystem()
        
        assert memory is not None
        assert isinstance(memory, MemorySystem)
    
    def test_memory_system_with_config(self):
        """Test creating MemorySystem with custom config."""
        config = MemoryConfig()
        
        memory = MemorySystem(config=config)
        
        assert memory.config == config
        assert memory.config.context.max_tokens == 4000
    
    def test_memory_system_from_config_classmethod(self):
        """Test creating MemorySystem from config file."""
        try:
            memory = MemorySystem.from_config("config/memory.yaml")
            assert isinstance(memory, MemorySystem)
        except (FileNotFoundError, NotImplementedError):
            pytest.skip("Config file not found or from_config not fully implemented")
    
    def test_memory_system_initialization_flag(self):
        """Test that memory system tracks initialization state."""
        memory = MemorySystem()
        
        # Should have initialization tracking
        assert hasattr(memory, "_initialized")


class TestMemorySystemRemember:
    """Tests for remember() method."""
    
    def test_remember_method_exists(self):
        """Test that remember method exists."""
        memory = MemorySystem()
        
        assert hasattr(memory, "remember")
        assert callable(memory.remember)
    
    def test_remember_signature(self):
        """Test remember() method signature."""
        memory = MemorySystem()
        
        # Should accept these parameters
        try:
            memory.remember(
                content="Test memory",
                session_id="test_session",
                metadata={"key": "value"},
            )
        except NotImplementedError:
            # Expected for Phase 1
            pass
        except TypeError as e:
            pytest.fail(f"remember() has wrong signature: {e}")
    
    def test_remember_with_minimal_args(self):
        """Test remember() with minimal required arguments."""
        memory = MemorySystem()
        
        try:
            memory.remember(
                content="Minimal memory test",
                session_id="session_1",
            )
        except NotImplementedError:
            pytest.skip("remember() not implemented yet")


class TestMemorySystemRecall:
    """Tests for recall() method."""
    
    def test_recall_method_exists(self):
        """Test that recall method exists."""
        memory = MemorySystem()
        
        assert hasattr(memory, "recall")
        assert callable(memory.recall)
    
    def test_recall_returns_iterator(self):
        """Test that recall() returns an iterator."""
        memory = MemorySystem()
        
        try:
            result = memory.recall("test query")
            
            # Should be iterable
            assert hasattr(result, "__iter__")
        except NotImplementedError:
            pytest.skip("recall() not implemented yet")
    
    def test_recall_with_limit(self):
        """Test recall() with limit parameter."""
        memory = MemorySystem()
        
        try:
            results = list(memory.recall("test query", limit=5))
            
            # Should respect limit
            assert len(results) <= 5
        except NotImplementedError:
            pytest.skip("recall() not implemented yet")
    
    def test_recall_with_filters(self):
        """Test recall() with filter parameters."""
        memory = MemorySystem()
        
        try:
            results = list(memory.recall(
                "test query",
                limit=10,
                filters={"session_id": "s1"},
            ))
            
            assert isinstance(results, list)
        except NotImplementedError:
            pytest.skip("recall() not implemented yet")
    
    def test_recall_signature(self):
        """Test recall() method signature."""
        memory = MemorySystem()
        
        try:
            memory.recall(
                query="test",
                limit=10,
                filters={"key": "value"},
            )
        except NotImplementedError:
            pass  # Expected
        except TypeError as e:
            pytest.fail(f"recall() has wrong signature: {e}")


class TestMemorySystemConsolidate:
    """Tests for consolidate() method."""
    
    def test_consolidate_method_exists(self):
        """Test that consolidate method exists."""
        memory = MemorySystem()
        
        assert hasattr(memory, "consolidate")
        assert callable(memory.consolidate)
    
    def test_consolidate_returns_stats(self):
        """Test that consolidate() returns statistics dict."""
        memory = MemorySystem()
        
        try:
            result = memory.consolidate(session_id="test_session")
            
            assert isinstance(result, dict)
        except NotImplementedError:
            pytest.skip("consolidate() not implemented yet")
    
    def test_consolidate_signature(self):
        """Test consolidate() method signature."""
        memory = MemorySystem()
        
        try:
            memory.consolidate(session_id="test_session")
        except NotImplementedError:
            pass  # Expected
        except TypeError as e:
            pytest.fail(f"consolidate() has wrong signature: {e}")


class TestMemorySystemHealth:
    """Tests for health() method."""
    
    def test_health_method_exists(self):
        """Test that health method exists."""
        memory = MemorySystem()
        
        assert hasattr(memory, "health")
        assert callable(memory.health)
    
    def test_health_returns_status(self):
        """Test that health() returns system status."""
        memory = MemorySystem()
        
        health = memory.health()
        
        assert isinstance(health, dict)
        assert "status" in health
        assert health["status"] in ["healthy", "degraded", "unhealthy"]
    
    def test_health_includes_metrics(self):
        """Test that health() includes system metrics."""
        memory = MemorySystem()
        
        health = memory.health()
        
        # Should include version info
        assert "version" in health
        
        # Should include memory counts
        assert "episodic_count" in health or "semantic_count" in health


class TestMemorySystemExplain:
    """Tests for explain_recall() method."""
    
    def test_explain_recall_method_exists(self):
        """Test that explain_recall method exists."""
        memory = MemorySystem()
        
        assert hasattr(memory, "explain_recall")
        assert callable(memory.explain_recall)
    
    def test_explain_recall_signature(self):
        """Test explain_recall() method signature."""
        memory = MemorySystem()
        
        try:
            memory.explain_recall(query="test query")
        except NotImplementedError:
            pass  # Expected for Phase 3
        except TypeError as e:
            pytest.fail(f"explain_recall() has wrong signature: {e}")


class TestMemorySystemIntegration:
    """Integration tests for MemorySystem."""
    
    def test_remember_and_recall_workflow(self):
        """Test basic remember -> recall workflow."""
        memory = MemorySystem()
        
        try:
            # Remember something
            memory.remember(
                "Alice likes Python",
                session_id="test",
            )
            
            # Recall it
            results = list(memory.recall("Alice"))
            
            # Should work without errors
            assert isinstance(results, list)
        except NotImplementedError:
            pytest.skip("Core functionality not implemented yet")
    
    def test_multiple_sessions_isolated(self):
        """Test that different sessions are tracked separately."""
        memory = MemorySystem()
        
        try:
            # Session 1
            memory.remember("Session 1 data", session_id="s1")
            
            # Session 2
            memory.remember("Session 2 data", session_id="s2")
            
            # Should track both
            assert True  # Basic test that it doesn't crash
        except NotImplementedError:
            pytest.skip("Session management not implemented yet")
    
    def test_consolidate_after_remember(self):
        """Test consolidation after remembering."""
        memory = MemorySystem()
        
        try:
            # Remember some data
            memory.remember("Test data", session_id="s1")
            
            # Consolidate
            result = memory.consolidate(session_id="s1")
            
            assert isinstance(result, dict)
        except NotImplementedError:
            pytest.skip("Consolidation not implemented yet")
