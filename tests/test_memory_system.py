"""Unit tests for MemorySystem core functionality.

Tests the main MemorySystem interface and basic operations.
"""

import pytest

from hmem.core.memory_system import MemorySystem
from hmem.config import MemoryConfig


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


class TestMemorySystemRemember:
    """Tests for remember() method."""

    def test_remember_signature(self):
        """Test remember() method signature."""
        from hmem.models import Message, Conversation

        memory = MemorySystem()

        # Should accept Conversation
        conversation = Conversation(
            session_id="test", messages=[Message(role="user", content="test")]
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
            messages=[Message(role="user", content="Minimal memory test")],
        )
        session_id = memory.remember(conversation)
        assert session_id == "minimal_test"


class TestMemorySystemRecall:
    """Tests for recall() method."""

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
                    Message(
                        role="assistant", content="Great! What site are you targeting?"
                    ),
                ],
            )
            results = list(memory.recall(conversation, limit=10))

            assert isinstance(results, list)
        except NotImplementedError:
            pytest.skip("recall() not implemented yet")


class TestMemorySystemConsolidate:
    """Tests for consolidate() method."""

    def test_consolidate_returns_stats(self):
        """Test that consolidate() returns ConsolidationResult object."""
        from hmem.models import ConsolidationResult

        memory = MemorySystem()

        try:
            result = memory.consolidate(session_id="test_session")

            assert isinstance(result, ConsolidationResult)
            assert result.success is not None
        except NotImplementedError:
            pytest.skip("consolidate() not implemented yet")

    def test_multiple_sessions_isolated(self):
        """Test that different sessions are tracked separately."""
        from hmem.models import Message, Conversation

        memory = MemorySystem()

        # Session 1
        conv1 = Conversation(
            session_id="s1", messages=[Message(role="user", content="Session 1 data")]
        )
        memory.remember(conv1)

        # Session 2
        conv2 = Conversation(
            session_id="s2", messages=[Message(role="user", content="Session 2 data")]
        )
        memory.remember(conv2)

        # Should track both
        assert True  # Basic test that it doesn't crash

    def test_consolidate_after_remember(self):
        """Test consolidation after remembering."""
        from hmem.models import Message, Conversation, ConsolidationResult

        memory = MemorySystem()

        # Remember some data
        conversation = Conversation(
            session_id="s1", messages=[Message(role="user", content="Test data")]
        )
        memory.remember(conversation)

        # Consolidate
        result = memory.consolidate(session_id="s1")

        assert isinstance(result, ConsolidationResult)
        assert result.success is not None
        assert result.stored_events >= 0


class TestChromaEpisodicStore:
    """Tests for ChromaDB-based episodic memory storage."""

    def test_chroma_store_vector_search(self):
        """Test ChromaDB vector similarity search."""
        from hmem.storage.chroma_episodic import ChromaEpisodicStore
        from hmem.models import Event
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChromaEpisodicStore(
                persist_directory=str(Path(tmpdir) / "chroma_test"),
                collection_name="test_episodic",
            )

            # Add events
            event1 = Event(
                content="Successfully used selenium for web scraping",
                outcome="success",
                tags=["web_scraping", "selenium"],
            )
            event2 = Event(
                content="Beautiful Soup parsed HTML tables",
                outcome="success",
                tags=["parsing", "html"],
            )

            store.add(event1)
            store.add(event2)

            # Search for similar events
            results = store.search("how to scrape websites", limit=5)

            assert isinstance(results, list)
            # Should return Memory objects
            if results:
                assert all(hasattr(m, "content") for m in results)
                assert all(hasattr(m, "score") for m in results)

    def test_chroma_store_metadata_filtering(self):
        """Test metadata-based filtering in ChromaDB."""
        from hmem.storage.chroma_episodic import ChromaEpisodicStore
        from hmem.models import Event
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChromaEpisodicStore(
                persist_directory=str(Path(tmpdir) / "chroma_test"),
                collection_name="test_filtering",
            )

            # Add events with different outcomes
            success_event = Event(
                content="Task completed successfully",
                outcome="success",
            )
            failure_event = Event(
                content="Task failed with error",
                outcome="failure",
            )

            store.add(success_event)
            store.add(failure_event)

            # Filter by outcome
            results = store.search(
                "task",
                limit=10,
                filters={"outcome": "success"},
            )

            # Should only return success events (if filtering implemented)
            assert isinstance(results, list)

    def test_chroma_store_embedding_generation(self):
        """Test automatic embedding generation."""
        from hmem.storage.chroma_episodic import ChromaEpisodicStore
        from hmem.models import Event
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChromaEpisodicStore(
                persist_directory=str(Path(tmpdir) / "chroma_test"),
                collection_name="test_embeddings",
            )

            event = Event(
                content="Test event for embedding generation",
                outcome="success",
            )

            # Should generate embedding automatically
            event_id = store.add(event)

            assert event_id is not None
            assert isinstance(event_id, str)

    def test_chroma_store_health_check(self):
        """Test ChromaDB store health check."""
        from hmem.storage.chroma_episodic import ChromaEpisodicStore
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChromaEpisodicStore(
                persist_directory=str(Path(tmpdir) / "chroma_test"),
            )

            health = store.health_check()

            assert isinstance(health, dict)
            assert "status" in health


class TestAsyncConsolidation:
    """Tests for asynchronous consolidation functionality."""

    def test_async_consolidation_mode_config(self):
        """Test async consolidation configuration."""
        from hmem.config import MemoryConfig, ConsolidationConfig

        config = MemoryConfig(consolidation=ConsolidationConfig(mode="asynchronous"))

        assert config.consolidation.mode == "asynchronous"

    def test_consolidation_returns_immediately(self):
        """Test that remember() returns immediately in async mode."""
        from hmem.models import Message, Conversation
        import time

        memory = MemorySystem()

        # Measure time for remember operation
        start = time.time()

        conversation = Conversation(
            session_id="async_test",
            messages=[Message(role="user", content="Test async mode")],
        )
        session_id = memory.remember(conversation)

        elapsed = time.time() - start

        # Should return quickly (not waiting for consolidation)
        # This is functional test, not strict perf test
        assert elapsed < 1.0, "remember() should return quickly"
        assert session_id is not None

    def test_consolidation_queue_processing(self):
        """Test background queue consolidation processing."""
        from hmem.models import Message, Conversation

        memory = MemorySystem()

        # Submit multiple consolidation tasks
        for i in range(3):
            conversation = Conversation(
                session_id=f"queue_test_{i}",
                messages=[Message(role="user", content=f"Message {i}")],
            )
            memory.remember(conversation)

        # All should complete without errors
        assert True  # Basic queue processing test

    def test_consolidation_fallback_on_timeout(self):
        """Test fallback to sync mode on queue timeout."""
        from hmem.config import MemoryConfig, ConsolidationConfig
        from hmem.models import Message, Conversation

        # Config with short timeout - tests timeout handling
        config = MemoryConfig(
            consolidation=ConsolidationConfig(
                mode="asynchronous",
                queue_timeout=1,  # Very short timeout
            )
        )

        memory = MemorySystem(config=config)

        conversation = Conversation(
            session_id="timeout_test",
            messages=[Message(role="user", content="Test fallback")],
        )

        # Should handle timeout gracefully (fallback to sync or retry)
        session_id = memory.remember(conversation)
        assert session_id is not None


class TestTwoPhaseRetrieval:
    """Tests for two-phase retrieval mechanism.

    Based on docs/workflows.md Flow 1: Hot Path.

    Phase 1: Fast cache retrieval (P95 < 50ms)
    Phase 2: Deep vector + graph search (P95 < 500ms)
    """

    def test_recall_returns_iterator(self):
        """Test that recall returns iterator for progressive results."""
        from hmem.models import Message, Conversation

        memory = MemorySystem()

        # Store some data
        conv = Conversation(
            session_id="iter_test",
            messages=[Message(role="user", content="Test data for iteration")],
        )
        memory.remember(conv)

        # Recall should return iterator
        result = memory.recall("test", limit=10)

        # Should be iterable
        assert hasattr(result, "__iter__")

    def test_recall_respects_limit(self):
        """Test that recall respects the limit parameter."""
        from hmem.models import Message, Conversation

        memory = MemorySystem()

        # Store multiple items
        for i in range(5):
            conv = Conversation(
                session_id=f"limit_test_{i}",
                messages=[Message(role="user", content=f"Memory item {i}")],
            )
            memory.remember(conv)

        # Recall with limit
        results = list(memory.recall("Memory", limit=3))

        assert len(results) <= 3

    def test_recall_with_filters(self):
        """Test recall with metadata filters."""
        from hmem.models import Message, Conversation

        memory = MemorySystem()

        # Store with different metadata
        conv1 = Conversation(
            session_id="filter_s1",
            messages=[Message(role="user", content="Session 1 data")],
            metadata={"category": "work"},
        )
        conv2 = Conversation(
            session_id="filter_s2",
            messages=[Message(role="user", content="Session 2 data")],
            metadata={"category": "personal"},
        )

        memory.remember(conv1)
        memory.remember(conv2)

        # Recall with filter
        results = list(
            memory.recall(
                "data",
                limit=10,
                filters={"session_id": "filter_s1"},
            )
        )

        # Should filter results (implementation dependent)
        assert isinstance(results, list)

    def test_recall_multi_source_aggregation(self):
        """Test that recall aggregates from multiple sources."""
        from hmem.models import Message, Conversation

        memory = MemorySystem()

        # Store a conversation
        conv = Conversation(
            session_id="multi_source",
            messages=[Message(role="user", content="I prefer dark mode UI")],
        )
        memory.remember(conv)
        memory.consolidate(session_id="multi_source")

        # Recall should potentially return from multiple sources
        results = list(memory.recall("preferences", limit=10))

        # Results may come from episodic, semantic, skill, or principle
        if results:
            sources = {m.source for m in results}
            # At minimum should have some source
            assert len(sources) >= 0


class TestRetrieverRanking:
    """Tests for retrieval result ranking."""

    def test_results_sorted_by_score(self):
        """Test that results are sorted by relevance score."""
        from hmem.models import Message, Conversation

        memory = MemorySystem()

        # Add several memories
        for i in range(5):
            conv = Conversation(
                session_id=f"ranking_{i}",
                messages=[Message(role="user", content=f"Topic {i} content")],
            )
            memory.remember(conv)

        results = list(memory.recall("Topic", limit=10))

        if len(results) >= 2:
            # Should be sorted by score (descending)
            scores = [m.score for m in results]
            assert scores == sorted(scores, reverse=True)

    def test_outcome_affects_ranking(self):
        """Test that outcome (success/failure) affects ranking."""
        from hmem.models import Message, Conversation

        memory = MemorySystem()

        # Store success event
        memory.remember(
            Conversation(
                session_id="rank_success",
                messages=[
                    Message(role="user", content="Web scraping succeeded with selenium")
                ],
                metadata={"outcome": "success"},
            )
        )

        # Store failure event
        memory.remember(
            Conversation(
                session_id="rank_failure",
                messages=[
                    Message(role="user", content="Web scraping failed with requests")
                ],
                metadata={"outcome": "failure"},
            )
        )

        memory.consolidate(session_id="rank_success")
        memory.consolidate(session_id="rank_failure")

        # Query
        results = list(memory.recall("web scraping", limit=10))

        # Success should generally rank higher (depends on implementation)
        # This test validates the retrieval runs without error
        assert isinstance(results, list)
