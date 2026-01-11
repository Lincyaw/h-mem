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

    def test_valid_message_creation(self):
        """Test creating a valid Message instance."""
        message = Message(
            role="user",
            content="What's the weather like?",
        )

        assert message.role == "user"
        assert message.content == "What's the weather like?"
        assert isinstance(message.timestamp, datetime)
        assert message.metadata == {}

    def test_message_roles(self):
        """Test that role accepts valid values."""
        # Valid roles
        Message(role="system", content="test")
        Message(role="user", content="test")
        Message(role="assistant", content="test")

        # Invalid role
        with pytest.raises(ValidationError):
            Message(role="invalid", content="test")

    def test_message_with_metadata(self):
        """Test Message with metadata."""
        message = Message(
            role="assistant",
            content="The weather is sunny",
            metadata={"model": "gpt-4", "token_count": 10},
        )

        assert message.metadata["model"] == "gpt-4"
        assert message.metadata["token_count"] == 10


class TestConversationModel:
    """Tests for Conversation model (session-based input)."""

    def test_valid_conversation_creation(self):
        """Test creating a valid Conversation."""
        conversation = Conversation(
            session_id="session_123",
            messages=[
                Message(role="user", content="Hello"),
                Message(role="assistant", content="Hi there!"),
            ],
        )

        assert conversation.session_id == "session_123"
        assert len(conversation.messages) == 2
        assert conversation.messages[0].role == "user"
        assert conversation.messages[1].role == "assistant"

    def test_conversation_empty_messages(self):
        """Test Conversation with empty messages list."""
        conversation = Conversation(
            session_id="empty_session",
            messages=[],
        )

        assert len(conversation.messages) == 0

    def test_conversation_with_metadata(self):
        """Test Conversation with session-level metadata."""
        conversation = Conversation(
            session_id="session_456",
            messages=[Message(role="user", content="test")],
            metadata={"user_id": "user_001", "topic": "weather"},
        )

        assert conversation.metadata["user_id"] == "user_001"
        assert conversation.metadata["topic"] == "weather"

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

    def test_valid_memory_creation(self):
        """Test creating a valid Memory instance."""
        memory = Memory(
            content="User prefers dark mode",
            score=0.95,
            source="semantic",
            timestamp=datetime.now(),
            metadata={"session_id": "s1"},
        )

        assert memory.content == "User prefers dark mode"
        assert memory.score == 0.95
        assert memory.source == "semantic"
        assert isinstance(memory.timestamp, datetime)
        assert memory.metadata["session_id"] == "s1"

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

    def test_memory_default_metadata(self):
        """Test that metadata defaults to empty dict."""
        memory = Memory(
            content="test",
            score=0.5,
            source="episodic",
            timestamp=datetime.now(),
        )

        assert memory.metadata == {}
        assert isinstance(memory.metadata, dict)


class TestEventModel:
    """Tests for Event model."""

    def test_valid_event_creation(self):
        """Test creating a valid Event instance."""
        event = Event(
            content="User attempted web scraping",
            outcome="success",
            tags=["web_scraping", "selenium"],
            timestamp=datetime.now(),
            metadata={"session_id": "s1"},
        )

        assert event.content == "User attempted web scraping"
        assert event.outcome == "success"
        assert "web_scraping" in event.tags
        assert "selenium" in event.tags

    def test_event_default_values(self):
        """Test Event model defaults."""
        event = Event(
            content="test event",
            outcome="unknown",
        )

        assert event.tags == []
        assert isinstance(event.timestamp, datetime)
        assert event.metadata == {}

    def test_event_tags_as_list(self):
        """Test that tags must be a list."""
        event = Event(
            content="test",
            outcome="success",
            tags=["tag1", "tag2"],
        )

        assert len(event.tags) == 2
        assert event.tags == ["tag1", "tag2"]

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

    def test_valid_consolidation_result(self):
        """Test creating a valid ConsolidationResult."""
        result = ConsolidationResult(
            success=True,
            stored_events=5,
            updated_facts=3,
            conflicts_resolved=1,
            errors=[],
        )

        assert result.success is True
        assert result.stored_events == 5
        assert result.updated_facts == 3
        assert result.conflicts_resolved == 1
        assert result.errors == []

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

    def test_consolidation_default_values(self):
        """Test ConsolidationResult defaults."""
        result = ConsolidationResult(
            success=True,
            stored_events=0,
            updated_facts=0,
            conflicts_resolved=0,
        )

        assert result.errors == []
        assert result.metadata == {}


class TestPrincipleModel:
    """Tests for Principle model."""

    def test_valid_principle_creation(self):
        """Test creating a valid Principle."""
        principle = Principle(
            content="Data analysis tasks must start with data cleaning",
            evidence_count=5,
            confidence=0.85,
        )

        assert principle.content == "Data analysis tasks must start with data cleaning"
        assert principle.evidence_count == 5
        assert principle.confidence == 0.85
        assert isinstance(principle.created_at, datetime)

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

    def test_principle_evidence_count(self):
        """Test that evidence_count is tracked."""
        principle = Principle(
            content="Always validate input",
            evidence_count=10,
            confidence=0.9,
        )

        assert principle.evidence_count == 10


class TestSemanticTripleModel:
    """Tests for SemanticTriple model."""

    def test_valid_triple_creation(self):
        """Test creating a valid SemanticTriple."""
        triple = SemanticTriple(
            subject="User",
            predicate="PREFERS",
            object="dark_mode",
            weight=1.0,
        )

        assert triple.subject == "User"
        assert triple.predicate == "PREFERS"
        assert triple.object == "dark_mode"
        assert triple.weight == 1.0
        assert triple.version == 1

    def test_triple_default_values(self):
        """Test SemanticTriple defaults."""
        triple = SemanticTriple(
            subject="A",
            predicate="B",
            object="C",
        )

        assert triple.weight == 1.0
        assert triple.version == 1
        assert isinstance(triple.created_at, datetime)
        assert isinstance(triple.updated_at, datetime)

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

    def test_valid_reflection_context(self):
        """Test creating a valid ReflectionContext."""
        context = ReflectionContext(
            episode_count=10,
            time_span_days=7.0,
            avg_similarity=0.8,
        )

        assert context.episode_count == 10
        assert context.time_span_days == 7.0
        assert context.avg_similarity == 0.8
        assert context.last_reflection_time is None

    def test_reflection_context_with_last_reflection(self):
        """Test ReflectionContext with last_reflection_time."""
        last_time = datetime(2026, 1, 1, 10, 0, 0)
        context = ReflectionContext(
            episode_count=50,
            time_span_days=30.0,
            avg_similarity=0.75,
            last_reflection_time=last_time,
        )

        assert context.last_reflection_time == last_time

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

    def test_memory_json_serialization(self):
        """Test Memory can be serialized to JSON."""
        memory = Memory(
            content="test",
            score=0.9,
            source="episodic",
            timestamp=datetime(2026, 1, 10, 10, 0, 0),
        )

        json_data = memory.model_dump_json()
        assert isinstance(json_data, str)
        assert "test" in json_data
        assert "0.9" in json_data

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

    def test_semantic_triple_serialization(self):
        """Test SemanticTriple serialization."""
        triple = SemanticTriple(
            subject="User",
            predicate="LIKES",
            object="Python",
        )

        data = triple.model_dump()

        assert data["subject"] == "User"
        assert data["predicate"] == "LIKES"
        assert data["object"] == "Python"
        assert "created_at" in data
        assert "updated_at" in data


class TestUsageFeedbackModel:
    """Tests for UsageFeedback model (Flow 4 support)."""

    def test_valid_usage_feedback_creation(self):
        """Test creating a valid UsageFeedback instance."""
        from hmem.models import UsageFeedback

        feedback = UsageFeedback(
            memory_id="skill_001",
            memory_type="skill",
            outcome="success",
            confidence=0.9,
            context={"task": "web_scraping"},
        )

        assert feedback.memory_id == "skill_001"
        assert feedback.memory_type == "skill"
        assert feedback.outcome == "success"
        assert feedback.confidence == 0.9
        assert isinstance(feedback.timestamp, datetime)

    def test_usage_feedback_with_failure_reason(self):
        """Test UsageFeedback with failure details."""
        from hmem.models import UsageFeedback

        feedback = UsageFeedback(
            memory_id="prin_001",
            memory_type="principle",
            outcome="failure",
            confidence=0.85,
            failure_reason="Edge case not covered: empty input list",
            context={
                "task": "data_processing",
                "input_size": 0,
            },
            session_id="conv_123",
        )

        assert feedback.outcome == "failure"
        assert feedback.failure_reason is not None
        assert "empty input" in feedback.failure_reason
        assert feedback.session_id == "conv_123"

    def test_usage_feedback_memory_type_validation(self):
        """Test memory_type accepts valid values."""
        from hmem.models import UsageFeedback

        # Valid types
        UsageFeedback(memory_id="x", memory_type="skill", outcome="success")
        UsageFeedback(memory_id="x", memory_type="principle", outcome="success")

        # Invalid type should fail
        with pytest.raises(ValidationError):
            UsageFeedback(memory_id="x", memory_type="invalid", outcome="success")

    def test_usage_feedback_confidence_range(self):
        """Test confidence must be between 0 and 1."""
        from hmem.models import UsageFeedback

        # Valid confidence
        UsageFeedback(
            memory_id="x", memory_type="skill", outcome="success", confidence=0.0
        )
        UsageFeedback(
            memory_id="x", memory_type="skill", outcome="success", confidence=1.0
        )

        # Invalid confidence
        with pytest.raises(ValidationError):
            UsageFeedback(
                memory_id="x", memory_type="skill", outcome="success", confidence=1.5
            )

        with pytest.raises(ValidationError):
            UsageFeedback(
                memory_id="x", memory_type="skill", outcome="success", confidence=-0.1
            )


class TestPrincipleRefinementFields:
    """Tests for Principle model refinement-related fields."""

    def test_principle_weight_field(self):
        """Test Principle weight field for feedback tracking."""
        principle = Principle(
            content="Always validate inputs",
            evidence_count=5,
            confidence=0.8,
            weight=2.5,
        )

        assert principle.weight == 2.5
        assert 0.0 <= principle.weight <= 10.0

    def test_principle_usage_tracking_fields(self):
        """Test Principle usage count and success count."""
        principle = Principle(
            content="Use caching for performance",
            evidence_count=8,
            confidence=0.75,
            usage_count=20,
            success_count=15,
        )

        assert principle.usage_count == 20
        assert principle.success_count == 15

        success_rate = principle.success_count / principle.usage_count
        assert success_rate == 0.75

    def test_principle_version_fields(self):
        """Test Principle version and deprecation tracking."""
        # v1 - deprecated after refinement
        v1 = Principle(
            id="prin_001",
            content="Original principle",
            evidence_count=10,
            confidence=0.7,
            version="v1",
            deprecated=True,
            successor_id="prin_002",
        )

        assert v1.version == "v1"
        assert v1.deprecated is True
        assert v1.successor_id == "prin_002"

    def test_principle_weight_bounds(self):
        """Test Principle weight validation bounds."""
        # Valid weights
        Principle(content="x", evidence_count=1, confidence=0.5, weight=0.0)
        Principle(content="x", evidence_count=1, confidence=0.5, weight=10.0)

        # Invalid weight - above max
        with pytest.raises(ValidationError):
            Principle(content="x", evidence_count=1, confidence=0.5, weight=11.0)

        # Invalid weight - below min
        with pytest.raises(ValidationError):
            Principle(content="x", evidence_count=1, confidence=0.5, weight=-0.5)


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
