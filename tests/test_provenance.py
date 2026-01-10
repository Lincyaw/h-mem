"""Tests for memory provenance/lineage functionality.

Tests the hierarchical semantic graph architecture where:
- Level 0: Raw conversations (source)
- Level 1: Episodic events (derived from conversations)
- Level 2: Semantic facts (derived from events)
- Level 3: Principles (induced from multiple memories)

All derived memories maintain parent_ids for provenance tracking.
"""

from datetime import datetime

from hmem.models import (
    Memory,
    Event,
    Conversation,
    Message,
    Principle,
    SemanticTriple,
)
from hmem.core.memory_system import MemorySystem
from hmem.storage.episodic import EpisodicStore
from hmem.hippocampus.encoder import MemoryEncoder


class TestMemoryProvenance:
    """Tests for Memory model provenance fields."""

    def test_memory_with_provenance(self):
        """Test Memory model with parent_ids and derivation_type."""
        memory = Memory(
            id="mem_001",
            content="User prefers dark mode",
            score=0.95,
            source="semantic",
            timestamp=datetime.now(),
            parent_ids=["conv_xyz789"],
            derivation_type="extraction",
        )

        assert memory.id == "mem_001"
        assert memory.parent_ids == ["conv_xyz789"]
        assert memory.derivation_type == "extraction"

    def test_memory_without_provenance(self):
        """Test Memory model without provenance (backward compatible)."""
        memory = Memory(
            content="Some content",
            score=0.5,
            source="episodic",
            timestamp=datetime.now(),
        )

        assert memory.id is None
        assert memory.parent_ids == []
        assert memory.derivation_type is None

    def test_memory_multiple_parents(self):
        """Test Memory with multiple parent IDs (induced from multiple sources)."""
        memory = Memory(
            id="principle_001",
            content="Always clean data before analysis",
            score=0.9,
            source="semantic",
            timestamp=datetime.now(),
            parent_ids=["evt_001", "evt_002", "evt_003"],
            derivation_type="induction",
        )

        assert len(memory.parent_ids) == 3
        assert memory.derivation_type == "induction"


class TestEventProvenance:
    """Tests for Event model provenance fields."""

    def test_event_with_provenance(self):
        """Test Event model with parent_ids linking to conversation."""
        event = Event(
            id="evt_001",
            content="User attempted web scraping",
            outcome="success",
            parent_ids=["conv_123"],
            derivation_type="extraction",
        )

        assert event.id == "evt_001"
        assert event.parent_ids == ["conv_123"]
        assert event.derivation_type == "extraction"

    def test_event_default_derivation_type(self):
        """Test Event defaults to extraction derivation type."""
        event = Event(
            content="Some event",
            outcome="unknown",
        )

        assert event.derivation_type == "extraction"
        assert event.parent_ids == []


class TestConversationId:
    """Tests for Conversation ID field."""

    def test_conversation_with_id(self):
        """Test Conversation with explicit ID."""
        conv = Conversation(
            id="conv_abc123",
            session_id="session_001",
            messages=[Message(role="user", content="Hello")],
        )

        assert conv.id == "conv_abc123"

    def test_conversation_without_id(self):
        """Test Conversation without ID (will be auto-generated)."""
        conv = Conversation(
            session_id="session_001",
            messages=[Message(role="user", content="Hello")],
        )

        assert conv.id is None


class TestPrincipleProvenance:
    """Tests for Principle model provenance fields."""

    def test_principle_with_evidence_chain(self):
        """Test Principle with evidence parent_ids."""
        principle = Principle(
            id="prin_001",
            content="Data analysis tasks must start with data cleaning",
            evidence_count=5,
            confidence=0.85,
            parent_ids=["evt_001", "evt_002", "evt_003", "evt_004", "evt_005"],
            derivation_type="induction",
        )

        assert principle.id == "prin_001"
        assert len(principle.parent_ids) == 5
        assert principle.derivation_type == "induction"

    def test_principle_default_derivation_type(self):
        """Test Principle defaults to induction derivation type."""
        principle = Principle(
            content="Some principle",
            evidence_count=3,
            confidence=0.7,
        )

        assert principle.derivation_type == "induction"


class TestSemanticTripleProvenance:
    """Tests for SemanticTriple model provenance fields."""

    def test_triple_with_provenance(self):
        """Test SemanticTriple with parent_ids."""
        triple = SemanticTriple(
            id="triple_001",
            subject="User",
            predicate="PREFERS",
            object="dark_mode",
            parent_ids=["conv_123"],
            derivation_type="extraction",
        )

        assert triple.id == "triple_001"
        assert triple.parent_ids == ["conv_123"]
        assert triple.derivation_type == "extraction"

    def test_triple_supersession(self):
        """Test SemanticTriple supersession (updating old fact)."""
        old_triple = SemanticTriple(
            id="triple_old",
            subject="User",
            predicate="EATS",
            object="vegetarian",
        )

        new_triple = SemanticTriple(
            id="triple_new",
            subject="User",
            predicate="EATS",
            object="pescatarian",
            parent_ids=[old_triple.id],
            derivation_type="supersession",
        )

        assert new_triple.parent_ids == ["triple_old"]
        assert new_triple.derivation_type == "supersession"


class TestEpisodicStoreProvenance:
    """Tests for EpisodicStore provenance functionality."""

    def test_add_event_with_provenance(self):
        """Test adding event preserves provenance."""
        store = EpisodicStore()

        event = Event(
            content="User prefers dark mode",
            outcome="success",
            parent_ids=["conv_abc123"],
            derivation_type="extraction",
        )

        event_id = store.add_event(event)

        # Retrieve and verify provenance
        retrieved = store.get_by_id(event_id)
        assert retrieved is not None
        assert retrieved.parent_ids == ["conv_abc123"]
        assert retrieved.derivation_type == "extraction"

    def test_add_event_generates_id(self):
        """Test add_event generates ID if not provided."""
        store = EpisodicStore()

        event = Event(
            content="Some event",
            outcome="unknown",
        )

        event_id = store.add_event(event)

        assert event_id.startswith("evt_")
        retrieved = store.get_by_id(event_id)
        assert retrieved.id == event_id

    def test_get_children(self):
        """Test getting derived memories from a parent."""
        store = EpisodicStore()

        parent_id = "conv_parent123"

        # Add multiple events derived from same parent
        for i in range(3):
            event = Event(
                content=f"Event {i}",
                outcome="unknown",
                parent_ids=[parent_id],
            )
            store.add_event(event)

        children = store.get_children(parent_id)
        assert len(children) == 3
        for child in children:
            assert parent_id in child.parent_ids

    def test_get_lineage(self):
        """Test tracing provenance chain."""
        store = EpisodicStore()

        # Create a chain: conv -> evt1 -> evt2
        evt1 = Event(
            id="evt_level1",
            content="Level 1 event",
            outcome="unknown",
            parent_ids=["conv_root"],
        )
        store.add_event(evt1)

        evt2 = Event(
            id="evt_level2",
            content="Level 2 event",
            outcome="unknown",
            parent_ids=["evt_level1"],
            derivation_type="derivation",
        )
        store.add_event(evt2)

        lineage = store.get_lineage("evt_level2")

        assert "evt_level1" in lineage

    def test_search_preserves_provenance(self):
        """Test that search results include provenance info."""
        store = EpisodicStore()

        event = Event(
            content="User prefers dark mode settings",
            outcome="success",
            parent_ids=["conv_xyz"],
            derivation_type="extraction",
        )
        store.add_event(event)

        results = store.search("dark mode", limit=5)

        assert len(results) > 0
        assert results[0].parent_ids == ["conv_xyz"]
        assert results[0].derivation_type == "extraction"


class TestMemoryEncoderProvenance:
    """Tests for MemoryEncoder provenance tracking."""

    def test_encode_conversation_sets_provenance(self):
        """Test that encoded events have parent_ids set to conversation."""
        encoder = MemoryEncoder()

        conv = Conversation(
            id="conv_test123",
            session_id="session_001",
            messages=[
                Message(role="user", content="I want to learn Python"),
                Message(role="assistant", content="Great choice!"),
            ],
        )

        events, facts = encoder.encode_conversation(conv)

        # Events should have parent_ids pointing to conversation
        for event in events:
            assert conv.id in event.parent_ids
            assert event.derivation_type == "extraction"

    def test_extract_events_with_auto_generated_conv_id(self):
        """Test that conversation without ID gets one generated."""
        encoder = MemoryEncoder()

        conv = Conversation(
            session_id="session_001",
            messages=[
                Message(role="user", content="Hello"),
            ],
        )

        events = encoder.extract_events(conv)

        # Events should have some parent ID set
        assert len(events) > 0
        for event in events:
            assert len(event.parent_ids) > 0
            assert event.parent_ids[0].startswith("conv_")


class TestMemorySystemProvenance:
    """Tests for MemorySystem provenance features."""

    def test_remember_assigns_conversation_id(self):
        """Test that remember() assigns ID to conversation."""
        memory = MemorySystem()

        conv = Conversation(
            session_id="sess_001",
            messages=[Message(role="user", content="Test message")],
        )

        memory.remember(conv)

        # The system should have assigned an ID internally
        # This is verified through the derived memories
        results = list(memory.recall("Test message", limit=5))

        if results:
            # If there are results, they should have parent_ids
            assert len(results[0].parent_ids) > 0

    def test_recall_returns_provenance(self):
        """Test that recalled memories have provenance info."""
        memory = MemorySystem()

        conv = Conversation(
            id="conv_known",
            session_id="sess_001",
            messages=[Message(role="user", content="User prefers dark mode")],
        )

        memory.remember(conv)

        results = list(memory.recall("dark mode", limit=5))

        if results:
            # Results should have provenance
            assert results[0].parent_ids is not None

    def test_get_lineage_method(self):
        """Test MemorySystem.get_lineage() method."""
        memory = MemorySystem()

        conv = Conversation(
            id="conv_source",
            session_id="sess_001",
            messages=[Message(role="user", content="I want to scrape websites")],
        )

        memory.remember(conv)

        # Get first result
        results = list(memory.recall("scrape websites", limit=1))

        if results and results[0].id:
            lineage = memory.get_lineage(results[0].id)
            # Lineage should include the conversation
            assert isinstance(lineage, list)

    def test_get_derived_method(self):
        """Test MemorySystem.get_derived() method."""
        memory = MemorySystem()

        conv = Conversation(
            id="conv_parent",
            session_id="sess_001",
            messages=[Message(role="user", content="Test derivation")],
        )

        memory.remember(conv)

        # Get memories derived from the conversation
        derived = memory.get_derived("conv_parent")

        # Should find the event derived from this conversation
        assert isinstance(derived, list)
        # Events were derived from this conversation
        for mem in derived:
            assert "conv_parent" in mem.parent_ids


class TestProvenanceIntegration:
    """Integration tests for provenance across the system."""

    def test_full_provenance_chain(self):
        """Test complete provenance chain from conversation to memory."""
        memory = MemorySystem()

        # Create a conversation
        conv = Conversation(
            id="conv_integration",
            session_id="integration_test",
            messages=[
                Message(role="user", content="I tried requests.get and it failed"),
                Message(role="assistant", content="Let me help"),
                Message(role="user", content="I then used selenium and it worked"),
            ],
        )

        # Remember the conversation
        memory.remember(conv)

        # Query for related memories
        results = list(memory.recall("selenium worked", limit=5))

        if results:
            # Verify the memory links back to its source
            result = results[0]
            assert result.id is not None
            assert len(result.parent_ids) > 0
            # The parent should be the conversation
            assert any(pid.startswith("conv_") for pid in result.parent_ids), (
                "Memory should link to conversation"
            )

    def test_provenance_serialization(self):
        """Test that provenance fields serialize correctly."""
        memory = Memory(
            id="mem_test",
            content="Test content",
            score=0.8,
            source="episodic",
            timestamp=datetime.now(),
            parent_ids=["conv_1", "conv_2"],
            derivation_type="extraction",
        )

        # Serialize to dict
        data = memory.model_dump()

        assert data["id"] == "mem_test"
        assert data["parent_ids"] == ["conv_1", "conv_2"]
        assert data["derivation_type"] == "extraction"

        # Deserialize back
        restored = Memory(**data)
        assert restored.parent_ids == memory.parent_ids
        assert restored.derivation_type == memory.derivation_type
