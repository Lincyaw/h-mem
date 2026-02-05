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


class TestProvenanceIntegration:
    """Integration tests for provenance across the system."""

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
