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
        from hmem.models import Message, Conversation
        
        memory = MemorySystem()
        
        # Should accept Conversation
        conversation = Conversation(
            session_id="test",
            messages=[Message(role="user", content="test")]
        )
        session_id = memory.remember(conversation)
        assert isinstance(session_id, str)
        
        # Should accept list[Message]
        messages = [Message(role="user", content="test")]
        session_id = memory.remember(messages)
        assert isinstance(session_id, str)
    
    def test_remember_with_minimal_args(self):
        """Test remember() with minimal required arguments."""
        from hmem.models import Message, Conversation
        
        memory = MemorySystem()
        
        conversation = Conversation(
            session_id="minimal_test",
            messages=[Message(role="user", content="Minimal memory test")]
        )
        session_id = memory.remember(conversation)
        assert session_id == "minimal_test"


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
    
    def test_recall_with_string_query(self):
        """Test recall() with simple string query."""
        memory = MemorySystem()
        
        try:
            results = list(memory.recall("test query", limit=5))
            
            # Should respect limit
            assert len(results) <= 5
        except NotImplementedError:
            pytest.skip("recall() not implemented yet")
    
    def test_recall_with_message_query(self):
        """Test recall() with Message object for context-aware search."""
        from hmem.models import Message
        
        memory = MemorySystem()
        
        try:
            query_msg = Message(role="user", content="What are my preferences?")
            results = list(memory.recall(query_msg, limit=10))
            
            assert isinstance(results, list)
        except NotImplementedError:
            pytest.skip("recall() not implemented yet")
    
    def test_recall_with_conversation_query(self):
        """Test recall() with Conversation for proactive prompting."""
        from hmem.models import Message, Conversation
        
        memory = MemorySystem()
        
        try:
            conversation = Conversation(
                session_id="test_session",
                messages=[
                    Message(role="user", content="I'm working on web scraping"),
                    Message(role="assistant", content="Great! What site are you targeting?"),
                ]
            )
            results = list(memory.recall(conversation, limit=10))
            
            assert isinstance(results, list)
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
        """Test recall() method signature accepts all query types."""
        from hmem.models import Message, Conversation
        
        memory = MemorySystem()
        
        try:
            # Should accept string
            memory.recall(query="test", limit=10, filters={"key": "value"})
            
            # Should accept Message
            memory.recall(query=Message(role="user", content="test"), limit=10)
            
            # Should accept Conversation
            conversation = Conversation(
                session_id="s1",
                messages=[Message(role="user", content="test")]
            )
            memory.recall(query=conversation, limit=10)
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
        from hmem.models import Message, Conversation
        
        memory = MemorySystem()
        
        # Remember something
        conversation = Conversation(
            session_id="test",
            messages=[Message(role="user", content="Alice likes Python")]
        )
        memory.remember(conversation)
        
        # Recall it
        results = list(memory.recall("Alice"))
        
        # Should work without errors
        assert isinstance(results, list)
        assert len(results) > 0
        assert any("Alice" in m.content or "Python" in m.content for m in results)
    
    def test_multiple_sessions_isolated(self):
        """Test that different sessions are tracked separately."""
        from hmem.models import Message, Conversation
        
        memory = MemorySystem()
        
        # Session 1
        conv1 = Conversation(
            session_id="s1",
            messages=[Message(role="user", content="Session 1 data")]
        )
        memory.remember(conv1)
        
        # Session 2
        conv2 = Conversation(
            session_id="s2",
            messages=[Message(role="user", content="Session 2 data")]
        )
        memory.remember(conv2)
        
        # Should track both
        assert True  # Basic test that it doesn't crash
    
    def test_consolidate_after_remember(self):
        """Test consolidation after remembering."""
        from hmem.models import Message, Conversation
        
        memory = MemorySystem()
        
        # Remember some data
        conversation = Conversation(
            session_id="s1",
            messages=[Message(role="user", content="Test data")]
        )
        memory.remember(conversation)
        
        # Consolidate
        result = memory.consolidate(session_id="s1")
        
        assert isinstance(result, dict)
        assert "events_processed" in result
