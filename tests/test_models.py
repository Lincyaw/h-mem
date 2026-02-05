"""Unit tests for data models (models.py).

Tests Pydantic models for correct validation, serialization, and type safety.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from hmem.models import (
    Message,
    Conversation,
    Memory,
    Event,
    ConsolidationResult,
    Principle,
    SemanticTriple,
    ReflectionContext,
)


class TestMessageModel:
    """Tests for Message model (conversation-based API)."""

    def test_message_roles(self):
        """Test that role accepts valid values."""
        # Valid roles
        Message(role="system", content="test")
        Message(role="user", content="test")
        Message(role="assistant", content="test")

        # Invalid role
        with pytest.raises(ValidationError):
            Message(role="invalid", content="test")


class TestConversationModel:
    """Tests for Conversation model (session-based input)."""

    def test_conversation_message_order(self):
        """Test that messages maintain chronological order."""
        messages = [
            Message(role="user", content="First"),
            Message(role="assistant", content="Second"),
            Message(role="user", content="Third"),
        ]

        conversation = Conversation(
            session_id="ordered_session",
            messages=messages,
        )

        assert conversation.messages[0].content == "First"
        assert conversation.messages[1].content == "Second"
        assert conversation.messages[2].content == "Third"


class TestMemoryModel:
    """Tests for Memory model."""

    def test_score_validation_range(self):
        """Test that score must be between 0 and 1."""
        # Valid scores
        Memory(content="test", score=0.0, source="episodic", timestamp=datetime.now())
        Memory(content="test", score=1.0, source="semantic", timestamp=datetime.now())
        Memory(content="test", score=0.5, source="skill", timestamp=datetime.now())

        # Invalid scores
        with pytest.raises(ValidationError):
            Memory(
                content="test", score=1.5, source="episodic", timestamp=datetime.now()
            )

        with pytest.raises(ValidationError):
            Memory(
                content="test", score=-0.1, source="episodic", timestamp=datetime.now()
            )


class TestEventModel:
    """Tests for Event model."""

    def test_event_metadata_extensibility(self):
        """Test that metadata can hold arbitrary data."""
        event = Event(
            content="test",
            outcome="failure",
            metadata={
                "session_id": "s1",
                "user_query": "write scraper",
                "attempt_number": 3,
                "error_code": "BLOCKED",
            },
        )

        assert event.metadata["attempt_number"] == 3
        assert event.metadata["error_code"] == "BLOCKED"


class TestConsolidationResultModel:
    """Tests for ConsolidationResult model."""

    def test_consolidation_with_errors(self):
        """Test ConsolidationResult with error messages."""
        result = ConsolidationResult(
            success=False,
            stored_events=2,
            updated_facts=0,
            conflicts_resolved=0,
            errors=["Database connection failed", "Timeout"],
        )

        assert result.success is False
        assert len(result.errors) == 2
        assert "Database connection failed" in result.errors


class TestPrincipleModel:
    """Tests for Principle model."""

    def test_principle_confidence_range(self):
        """Test that confidence must be between 0 and 1."""
        # Valid
        Principle(content="test", evidence_count=1, confidence=0.0)
        Principle(content="test", evidence_count=1, confidence=1.0)

        # Invalid
        with pytest.raises(ValidationError):
            Principle(content="test", evidence_count=1, confidence=1.5)

        with pytest.raises(ValidationError):
            Principle(content="test", evidence_count=1, confidence=-0.1)


class TestSemanticTripleModel:
    """Tests for SemanticTriple model."""

    def test_triple_weight_validation(self):
        """Test that weight must be non-negative."""
        # Valid
        SemanticTriple(subject="A", predicate="B", object="C", weight=0.0)
        SemanticTriple(subject="A", predicate="B", object="C", weight=2.5)

        # Invalid
        with pytest.raises(ValidationError):
            SemanticTriple(subject="A", predicate="B", object="C", weight=-1.0)

    def test_triple_version_tracking(self):
        """Test version field for optimistic locking."""
        triple = SemanticTriple(
            subject="User",
            predicate="EATS",
            object="vegetarian",
            version=1,
        )

        assert triple.version == 1

        # Simulate update
        updated = SemanticTriple(
            subject=triple.subject,
            predicate=triple.predicate,
            object="pescatarian",
            version=triple.version + 1,
        )

        assert updated.version == 2


class TestReflectionContextModel:
    """Tests for ReflectionContext model."""

    def test_reflection_context_metrics(self):
        """Test that ReflectionContext tracks necessary metrics."""
        context = ReflectionContext(
            episode_count=100,
            time_span_days=14.5,
            avg_similarity=0.85,
        )

        # These metrics should be available for reflection policy
        assert isinstance(context.episode_count, int)
        assert isinstance(context.time_span_days, float)
        assert isinstance(context.avg_similarity, float)


class TestModelSerialization:
    """Tests for model serialization and deserialization."""

    def test_event_json_round_trip(self):
        """Test Event serialization round-trip."""
        original = Event(
            content="test event",
            outcome="success",
            tags=["tag1"],
            timestamp=datetime(2026, 1, 10, 10, 0, 0),
        )

        # Serialize to dict
        data = original.model_dump()

        # Deserialize back
        restored = Event(**data)

        assert restored.content == original.content
        assert restored.outcome == original.outcome
        assert restored.tags == original.tags


class TestSkillModel:
    """Tests for Skill model."""

    def test_valid_skill_creation(self):
        """Test creating a valid Skill instance."""
        from hmem.models import Skill

        skill = Skill(
            name="web_scraping_selenium",
            trigger_pattern="scrape|crawl|extract data",
            code_template={
                "steps": ["Initialize driver", "Navigate", "Extract"],
                "params": ["url", "selector"],
            },
            description="Use Selenium for dynamic sites",
        )

        assert skill.name == "web_scraping_selenium"
        assert skill.trigger_pattern == "scrape|crawl|extract data"
        assert "steps" in skill.code_template
        assert isinstance(skill.created_at, datetime)

    def test_skill_with_feedback_tracking(self):
        """Test Skill with usage feedback fields via index_profile."""
        from hmem.models import Skill, IndexProfile

        index_profile = IndexProfile(
            q_value=0.9,
            q_update_count=10,
        )
        skill = Skill(
            name="data_cleaning",
            trigger_pattern="clean|preprocess data",
            code_template={"steps": ["Remove nulls", "Normalize"]},
            index_profile=index_profile,
        )

        assert skill.index_profile is not None
        assert skill.index_profile.q_value == 0.9
        assert skill.index_profile.q_update_count == 10

    def test_skill_version_management(self):
        """Test Skill version and deprecation fields."""
        from hmem.models import Skill

        skill = Skill(
            name="old_method",
            trigger_pattern="process",
            code_template={"steps": ["old way"]},
            version=1,
            is_deprecated=True,
            successor_id="skill_002",
        )

        assert skill.version == 1
        assert skill.is_deprecated is True
        assert skill.successor_id == "skill_002"


class TestPrincipleRefinementFields:
    """Tests for Principle model refinement-related fields via index_profile."""

    def test_principle_weight_field(self):
        """Test Principle Q-value field for feedback tracking via index_profile."""
        from hmem.models import IndexProfile

        index_profile = IndexProfile(q_value=0.8)
        principle = Principle(
            content="Always validate inputs",
            evidence_count=5,
            confidence=0.8,
            index_profile=index_profile,
        )

        assert principle.index_profile is not None
        assert principle.index_profile.q_value == 0.8
        assert 0.0 <= principle.index_profile.q_value <= 1.0

    def test_principle_usage_tracking_fields(self):
        """Test Principle Q-value tracking via index_profile."""
        from hmem.models import IndexProfile

        # Q-value based IndexProfile
        index_profile = IndexProfile(
            q_value=0.75,
            q_update_count=20,
        )
        principle = Principle(
            content="Use caching for performance",
            evidence_count=8,
            confidence=0.75,
            index_profile=index_profile,
        )

        assert principle.index_profile is not None
        assert principle.index_profile.q_value == 0.75
        assert principle.index_profile.q_update_count == 20
        assert principle.index_profile.confidence == 1.0  # 20/20 = 1.0

    def test_principle_version_fields(self):
        """Test Principle version and deprecation tracking."""
        # v1 - deprecated after refinement
        v1 = Principle(
            id="prin_001",
            content="Original principle",
            evidence_count=10,
            confidence=0.7,
            version=1,
            is_deprecated=True,
            successor_id="prin_002",
        )

        assert v1.version == 1
        assert v1.is_deprecated is True
        assert v1.successor_id == "prin_002"

    def test_principle_index_profile_q_value_bounds(self):
        """Test IndexProfile Q-value validation bounds."""
        from hmem.models import IndexProfile

        # Valid Q-values
        IndexProfile(q_value=0.0)
        IndexProfile(q_value=1.0)
        IndexProfile(q_value=0.5)

        # Invalid Q-value - above max
        with pytest.raises(ValidationError):
            IndexProfile(q_value=1.5)

        # Invalid Q-value - below min
        with pytest.raises(ValidationError):
            IndexProfile(q_value=-0.5)


class TestTwoPhaseRetrievalModels:
    """Tests for models supporting two-phase retrieval."""

    def test_memory_source_types_for_marking(self):
        """Test Memory source types for recall marking."""
        sources = ["episodic", "semantic", "skill", "principle"]

        for source in sources:
            memory = Memory(
                content=f"Test {source}",
                score=0.8,
                source=source,
                timestamp=datetime.now(),
            )
            assert memory.source == source

    def test_memory_provenance_for_feedback(self):
        """Test Memory provenance fields for feedback extraction."""
        memory = Memory(
            id="mem_001",
            content="Retrieved memory with provenance",
            score=0.9,
            source="principle",
            timestamp=datetime.now(),
            parent_ids=["prin_001"],
            derivation_type="induction",
        )

        # Provenance enables linking feedback to source
        assert memory.id is not None
        assert memory.parent_ids == ["prin_001"]
        assert memory.derivation_type == "induction"
