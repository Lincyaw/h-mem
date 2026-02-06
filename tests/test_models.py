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
    ReflectionContext,
    Entity,
    Attribute,
    Process,
    IndexProfile,
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
            description="Use Selenium for dynamic sites",
            trigger_pattern="scrape|crawl|extract data",
            action_template="1. Initialize driver\n2. Navigate\n3. Extract",
        )

        assert skill.name == "web_scraping_selenium"
        assert skill.trigger_pattern == "scrape|crawl|extract data"
        assert "Initialize" in skill.action_template
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
            description="Clean and preprocess data",
            trigger_pattern="clean|preprocess data",
            action_template="1. Remove nulls\n2. Normalize",
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
            description="Old processing method",
            trigger_pattern="process",
            action_template="1. Old way",
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


class TestEntityModel:
    """Tests for Entity model (entity-centric memory)."""

    def test_valid_entity_creation(self):
        """Test creating a valid Entity instance."""
        entity = Entity(
            canonical_name="张三",
            aliases=["我的上级", "领导"],
            entity_type="PERSON",
        )

        assert entity.canonical_name == "张三"
        assert "我的上级" in entity.aliases
        assert entity.entity_type == "PERSON"
        assert entity.needs_resolution is False
        assert isinstance(entity.created_at, datetime)

    def test_entity_with_reference_flag(self):
        """Test Entity with needs_resolution flag."""
        entity = Entity(
            canonical_name="我的上级",
            entity_type="PERSON",
            needs_resolution=True,
        )

        assert entity.needs_resolution is True
        assert entity.aliases == []

    def test_entity_types(self):
        """Test all valid entity types."""
        for entity_type in ["PERSON", "PROJECT", "ORGANIZATION", "CONCEPT", "TOOL"]:
            entity = Entity(
                canonical_name=f"Test {entity_type}",
                entity_type=entity_type,
            )
            assert entity.entity_type == entity_type


class TestAttributeModel:
    """Tests for Attribute model (entity-slot-value)."""

    def test_valid_attribute_creation(self):
        """Test creating a valid Attribute instance."""
        attr = Attribute(
            entity_id="entity_001",
            slot="爱好",
            value="网球",
            cardinality="multi",
            confidence=0.9,
        )

        assert attr.entity_id == "entity_001"
        assert attr.slot == "爱好"
        assert attr.value == "网球"
        assert attr.cardinality == "multi"
        assert attr.confidence == 0.9
        assert attr.is_superseded is False

    def test_single_cardinality_attribute(self):
        """Test single-cardinality attribute."""
        attr = Attribute(
            entity_id="entity_001",
            slot="职位",
            value="技术总监",
            cardinality="single",
        )

        assert attr.cardinality == "single"

    def test_attribute_with_index_profile(self):
        """Test Attribute with Q-value tracking."""
        profile = IndexProfile(q_value=0.8, q_update_count=5)
        attr = Attribute(
            entity_id="entity_001",
            slot="偏好.主题",
            value="dark",
            index_profile=profile,
        )

        assert attr.index_profile.q_value == 0.8
        assert attr.index_profile.q_update_count == 5


class TestProcessModel:
    """Tests for Process model (trigger-action-outcome)."""

    def test_valid_process_creation(self):
        """Test creating a valid Process instance."""
        proc = Process(
            trigger="遇到OOM错误",
            action="先抓heap dump，再分析大对象",
            outcome="定位内存泄漏源",
            confidence=0.85,
        )

        assert proc.trigger == "遇到OOM错误"
        assert proc.action == "先抓heap dump，再分析大对象"
        assert proc.outcome == "定位内存泄漏源"
        assert proc.confidence == 0.85
        assert proc.is_deprecated is False

    def test_process_without_outcome(self):
        """Test Process with optional outcome."""
        proc = Process(
            trigger="需要调试",
            action="打开调试工具",
        )

        assert proc.outcome is None

    def test_process_with_involved_facts(self):
        """Test Process with involved fact IDs."""
        proc = Process(
            trigger="部署到生产环境",
            action="运行测试套件 → 构建 → 灰度发布",
            involved_fact_ids=["fact_001", "fact_002"],
        )

        assert len(proc.involved_fact_ids) == 2
        assert "fact_001" in proc.involved_fact_ids

    def test_process_linked_to_skill(self):
        """Test Process linked to an induced Skill."""
        proc = Process(
            trigger="API返回500错误",
            action="检查日志 → 定位错误 → 修复",
            skill_id="skill_001",
        )

        assert proc.skill_id == "skill_001"

    def test_process_with_q_value(self):
        """Test Process with Q-value tracking."""
        profile = IndexProfile(q_value=0.95, q_update_count=20)
        proc = Process(
            trigger="代码审查",
            action="检查命名、逻辑、测试覆盖",
            index_profile=profile,
        )

        assert proc.index_profile.q_value == 0.95
        assert proc.index_profile.q_update_count == 20
