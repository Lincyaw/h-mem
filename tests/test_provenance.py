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


class TestMemoryEncoderProvenance:
    """Tests for MemoryEncoder provenance tracking."""

    def test_encode_conversation_returns_entity_centric_structure(self):
        """Test that encode_conversation returns entities, attributes, processes."""
        encoder = MemoryEncoder()

        conv = Conversation(
            id="conv_test123",
            session_id="session_001",
            messages=[
                Message(role="user", content="I want to learn Python"),
                Message(role="assistant", content="Great choice!"),
            ],
        )

        result = encoder.encode_conversation(conv)

        # Result should contain entity-centric structure (no events)
        assert "entities" in result
        assert "attributes" in result
        assert "processes" in result
        assert "conversation_id" in result
        assert result["conversation_id"] == "conv_test123"
        assert "events" not in result

    def test_encode_conversation_with_auto_generated_conv_id(self):
        """Test that conversation without ID still produces a conversation_id in result."""
        encoder = MemoryEncoder()

        conv = Conversation(
            session_id="session_001",
            messages=[
                Message(role="user", content="Hello"),
            ],
        )

        result = encoder.encode_conversation(conv)

        # conversation_id should be present (empty string if conv.id was None)
        assert "conversation_id" in result
        assert isinstance(result["entities"], list)
        assert isinstance(result["attributes"], list)
        assert isinstance(result["processes"], list)


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
