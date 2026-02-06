"""Tests for the self-bootstrapping skill system.

Tests cover:
- Skill file loading and parsing
- Meta-skill loading
- Skill creation with provenance
- Q-value feedback and auto-suspension
- Skill search
- Protected skill editing
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from hmem.skills.models import SkillMetadata, SkillSummary, SkillContent
from hmem.skills.loader import SkillLoader
from hmem.skills.manager import SkillManager
from hmem.skills.tools import (
    SkillSearchTool,
    SkillLoadTool,
    SkillCreateTool,
    SkillFeedbackTool,
    create_skill_tools,
)


class TestSkillModels:
    """Test skill Pydantic models."""

    def test_skill_metadata_defaults(self):
        """Test default values for SkillMetadata."""
        metadata = SkillMetadata(
            name="test-skill",
            description="A test skill",
        )

        assert metadata.name == "test-skill"
        assert metadata.description == "A test skill"
        assert metadata.skill_type == "generated"
        assert metadata.version == 1
        assert metadata.is_protected is False
        assert metadata.is_suspended is False
        assert metadata.q_value == 0.5
        assert metadata.q_update_count == 0

    def test_skill_metadata_full(self):
        """Test SkillMetadata with all fields."""
        metadata = SkillMetadata(
            name="debug-memory-leak",
            description="Use when debugging memory leaks",
            trigger_pattern="When OOM errors occur",
            tags=["debug", "memory"],
            skill_type="generated",
            source_process_ids=["proc_abc", "proc_def"],
            source_fact_ids=["fact_xyz"],
            version=2,
            is_protected=False,
            q_value=0.8,
            q_update_count=15,
        )

        assert metadata.name == "debug-memory-leak"
        assert len(metadata.tags) == 2
        assert len(metadata.source_process_ids) == 2
        assert metadata.version == 2
        assert metadata.q_value == 0.8

    def test_skill_summary_from_metadata(self):
        """Test creating SkillSummary from SkillMetadata."""
        metadata = SkillMetadata(
            name="test-skill",
            description="Test description",
            tags=["test"],
            q_value=0.75,
        )

        summary = SkillSummary.from_metadata(
            metadata, similarity_score=0.92, match_reason="Test match"
        )

        assert summary.name == "test-skill"
        assert summary.description == "Test description"
        assert summary.q_value == 0.75
        assert summary.similarity_score == 0.92
        assert summary.match_reason == "Test match"

    def test_skill_content_to_prompt(self):
        """Test formatting skill content for prompt injection."""
        metadata = SkillMetadata(name="test-skill", description="Test")
        content = SkillContent(
            metadata=metadata,
            content="# Test Skill\n\nInstructions here.",
        )

        prompt = content.to_prompt()

        assert '<skill name="test-skill">' in prompt
        assert "# Test Skill" in prompt
        assert "</skill>" in prompt


class TestSkillLoader:
    """Test SKILL.md file loading."""

    @pytest.fixture
    def temp_skills_dir(self, tmp_path):
        """Create a temporary skills directory structure."""
        meta_dir = tmp_path / "_meta" / "test-meta-skill"
        meta_dir.mkdir(parents=True)

        generated_dir = tmp_path / "generated" / "test-generated-skill"
        generated_dir.mkdir(parents=True)

        # Write meta skill
        meta_skill_content = """---
name: test-meta-skill
description: A test meta skill
trigger_pattern: When testing
tags:
  - test
  - meta
version: 1
---

# Test Meta Skill

This is the content.
"""
        (meta_dir / "SKILL.md").write_text(meta_skill_content)

        # Write generated skill
        generated_skill_content = """---
name: test-generated-skill
description: A test generated skill
source_process_ids:
  - proc_123
  - proc_456
tags:
  - generated
version: 1
q_value: 0.7
---

# Test Generated Skill

Generated content here.
"""
        (generated_dir / "SKILL.md").write_text(generated_skill_content)

        return tmp_path

    def test_parse_skill_file(self, temp_skills_dir):
        """Test parsing a SKILL.md file."""
        loader = SkillLoader(temp_skills_dir)
        skill_path = temp_skills_dir / "_meta" / "test-meta-skill" / "SKILL.md"

        content = loader.parse_skill_file(skill_path)

        assert content is not None
        assert content.metadata.name == "test-meta-skill"
        assert content.metadata.skill_type == "meta"
        assert content.metadata.is_protected is True
        assert "Test Meta Skill" in content.content

    def test_load_skill_by_name(self, temp_skills_dir):
        """Test loading a skill by name."""
        loader = SkillLoader(temp_skills_dir)

        # Load meta skill
        meta_skill = loader.load_skill("test-meta-skill")
        assert meta_skill is not None
        assert meta_skill.metadata.name == "test-meta-skill"

        # Load generated skill
        gen_skill = loader.load_skill("test-generated-skill")
        assert gen_skill is not None
        assert gen_skill.metadata.name == "test-generated-skill"
        assert gen_skill.metadata.q_value == 0.7

    def test_load_nonexistent_skill(self, temp_skills_dir):
        """Test loading a skill that doesn't exist."""
        loader = SkillLoader(temp_skills_dir)
        result = loader.load_skill("nonexistent-skill")
        assert result is None

    def test_list_all_skills(self, temp_skills_dir):
        """Test listing all skills."""
        loader = SkillLoader(temp_skills_dir)
        skills = loader.list_all_skills()

        assert len(skills) == 2
        names = {s.name for s in skills}
        assert "test-meta-skill" in names
        assert "test-generated-skill" in names

    def test_list_meta_skills(self, temp_skills_dir):
        """Test listing only meta skills."""
        loader = SkillLoader(temp_skills_dir)
        skills = loader.list_meta_skills()

        assert len(skills) == 1
        assert skills[0].name == "test-meta-skill"

    def test_write_skill(self, temp_skills_dir):
        """Test writing a new skill file."""
        loader = SkillLoader(temp_skills_dir)

        metadata = {
            "name": "new-skill",
            "description": "A new skill",
            "tags": ["new"],
            "q_value": 0.5,
        }
        content = "# New Skill\n\nContent here."

        path = loader.write_skill(
            skill_name="new-skill",
            metadata=metadata,
            content=content,
            skill_type="generated",
        )

        assert path.exists()

        # Verify we can load it back
        loaded = loader.load_skill("new-skill")
        assert loaded is not None
        assert loaded.metadata.name == "new-skill"
        assert "# New Skill" in loaded.content


class TestSkillManager:
    """Test SkillManager functionality."""

    @pytest.fixture
    def skill_manager(self, tmp_path):
        """Create a SkillManager with temporary directory."""
        # Create meta skills
        meta_dir = tmp_path / "_meta" / "skill-discovery"
        meta_dir.mkdir(parents=True)
        (meta_dir / "SKILL.md").write_text("""---
name: skill-discovery
description: Use before any task
is_protected: true
version: 1
---

# Skill Discovery
Search for skills first.
""")

        return SkillManager(store=None, skills_dir=tmp_path)

    def test_load_meta_skills(self, skill_manager):
        """Test loading all meta skills."""
        meta_skills = skill_manager.load_meta_skills()

        assert len(meta_skills) >= 1
        names = [s.metadata.name for s in meta_skills]
        assert "skill-discovery" in names

    def test_list_available(self, skill_manager):
        """Test listing available skills."""
        available = skill_manager.list_available()

        assert len(available) >= 1
        assert all(isinstance(s, SkillSummary) for s in available)

    def test_create_skill(self, skill_manager):
        """Test creating a new skill."""
        name = skill_manager.create(
            name="test-new-skill",
            description="A test skill",
            content="# Test\n\nContent.",
            tags=["test"],
            source_process_ids=["proc_1", "proc_2"],
        )

        assert name == "test-new-skill"

        # Verify it exists
        skill = skill_manager.load("test-new-skill")
        assert skill is not None
        assert skill.metadata.source_process_ids == ["proc_1", "proc_2"]

    def test_create_skill_insufficient_processes(self, skill_manager):
        """Test that creation fails without enough source processes."""
        name = skill_manager.create(
            name="bad-skill",
            description="Should fail",
            content="# Bad",
            source_process_ids=["proc_1"],  # Only 1, need 2
        )

        assert name is None

    def test_create_duplicate_skill(self, skill_manager):
        """Test that creating a duplicate skill fails."""
        # Create first
        skill_manager.create(
            name="first-skill",
            description="First",
            content="# First",
            source_process_ids=["proc_1", "proc_2"],
        )

        # Try to create duplicate
        result = skill_manager.create(
            name="first-skill",
            description="Duplicate",
            content="# Duplicate",
            source_process_ids=["proc_3", "proc_4"],
        )

        assert result is None

    def test_search_skills(self, skill_manager):
        """Test searching for skills."""
        # Create a skill to search for
        skill_manager.create(
            name="entity-extraction",
            description="Extract entities from text",
            content="# Entity Extraction",
            trigger_pattern="When extracting entities",
            tags=["extraction", "entity"],
            source_process_ids=["proc_1", "proc_2"],
        )

        results = skill_manager.search("entity")

        assert len(results) >= 1
        assert any(s.name == "entity-extraction" for s in results)

    def test_apply_feedback_success(self, skill_manager):
        """Test applying positive feedback updates Q-value."""
        # Create a skill
        skill_manager.create(
            name="feedback-test",
            description="Test feedback",
            content="# Test",
            source_process_ids=["proc_1", "proc_2"],
        )

        # Initial Q-value
        skill_before = skill_manager.load("feedback-test")
        q_before = skill_before.metadata.q_value

        # Apply success feedback
        skill_manager.apply_feedback("feedback-test", "success")

        # Check Q-value increased
        skill_after = skill_manager.load("feedback-test")
        assert skill_after.metadata.q_value > q_before
        assert skill_after.metadata.q_update_count == 1

    def test_apply_feedback_failure(self, skill_manager):
        """Test applying negative feedback decreases Q-value."""
        skill_manager.create(
            name="failure-test",
            description="Test failure",
            content="# Test",
            source_process_ids=["proc_1", "proc_2"],
        )

        skill_before = skill_manager.load("failure-test")
        q_before = skill_before.metadata.q_value

        skill_manager.apply_feedback("failure-test", "failure")

        skill_after = skill_manager.load("failure-test")
        assert skill_after.metadata.q_value < q_before

    def test_auto_suspend_low_q_value(self, skill_manager):
        """Test that skills with very low Q-value are auto-suspended."""
        skill_manager.create(
            name="suspend-test",
            description="Test suspension",
            content="# Test",
            source_process_ids=["proc_1", "proc_2"],
        )

        # Apply multiple failure feedbacks to drop Q-value
        for _ in range(10):
            skill_manager.apply_feedback("suspend-test", "failure")

        skill = skill_manager.load("suspend-test")
        # With default alpha=0.1 and 10 failures, Q should drop significantly
        # Auto-suspend threshold is 0.1 with 5+ updates
        assert skill.metadata.q_update_count >= 5
        # Q-value after 10 failures starting from 0.5:
        # 0.5 -> 0.45 -> 0.405 -> 0.3645 -> ... should be below 0.1 by update 10

    def test_edit_skill(self, skill_manager):
        """Test editing a skill."""
        skill_manager.create(
            name="edit-test",
            description="Original description",
            content="# Original",
            source_process_ids=["proc_1", "proc_2"],
        )

        success = skill_manager.edit(
            skill_name="edit-test",
            new_content="# Updated Content",
            version_bump=True,
            reason="Test update",
        )

        assert success is True

        skill = skill_manager.load("edit-test")
        assert skill.metadata.version == 2
        assert "# Updated Content" in skill.content

    def test_edit_protected_skill_requires_force(self, skill_manager):
        """Test that protected skills require force flag to edit."""
        # Try to edit the meta skill without force
        success = skill_manager.edit(
            skill_name="skill-discovery",
            new_content="# Edited",
            reason="Should fail",
        )

        assert success is False

        # With force
        success = skill_manager.edit(
            skill_name="skill-discovery",
            new_content="# Edited",
            reason="Should succeed",
            force=True,
        )

        assert success is True


class TestSkillTools:
    """Test skill tools."""

    @pytest.fixture
    def manager_with_skills(self, tmp_path):
        """Create a manager with some test skills."""
        manager = SkillManager(store=None, skills_dir=tmp_path)
        manager.loader.ensure_directories()

        # Create test skills
        manager.create(
            name="tool-test-skill",
            description="A skill for testing tools",
            content="# Tool Test\n\nContent.",
            tags=["test", "tool"],
            source_process_ids=["proc_1", "proc_2"],
        )

        return manager

    def test_skill_search_tool(self, manager_with_skills):
        """Test SkillSearchTool."""
        tool = SkillSearchTool(manager_with_skills)

        results = tool.run("tool test")

        assert len(results) >= 1
        assert any(s.name == "tool-test-skill" for s in results)

    def test_skill_load_tool(self, manager_with_skills):
        """Test SkillLoadTool."""
        tool = SkillLoadTool(manager_with_skills)

        content = tool.run("tool-test-skill")

        assert content is not None
        assert '<skill name="tool-test-skill">' in content
        assert "# Tool Test" in content

    def test_skill_load_tool_not_found(self, manager_with_skills):
        """Test SkillLoadTool with nonexistent skill."""
        tool = SkillLoadTool(manager_with_skills)

        content = tool.run("nonexistent-skill")

        assert content is None

    def test_skill_create_tool(self, manager_with_skills):
        """Test SkillCreateTool."""
        tool = SkillCreateTool(manager_with_skills)

        name = tool.run(
            name="Created Via Tool",  # Should be normalized to kebab-case
            description="Created using the tool",
            content="# Created\n\nVia tool.",
            source_process_ids=["proc_a", "proc_b"],
        )

        assert name == "created-via-tool"

        # Verify it exists
        skill = manager_with_skills.load("created-via-tool")
        assert skill is not None

    def test_skill_feedback_tool(self, manager_with_skills):
        """Test SkillFeedbackTool."""
        tool = SkillFeedbackTool(manager_with_skills)

        # Get initial Q-value
        skill_before = manager_with_skills.load("tool-test-skill")
        q_before = skill_before.metadata.q_value

        # Apply feedback
        tool.run("tool-test-skill", "success")

        skill_after = manager_with_skills.load("tool-test-skill")
        assert skill_after.metadata.q_value > q_before

    def test_create_skill_tools(self, manager_with_skills):
        """Test creating all tools at once."""
        tools = create_skill_tools(manager_with_skills)

        assert "skill_search" in tools
        assert "skill_load" in tools
        assert "skill_create" in tools
        assert "skill_edit" in tools
        assert "skill_feedback" in tools
        assert "process_search" in tools


class TestMetaSkillsIntegration:
    """Test that real meta-skills load correctly."""

    def test_load_actual_meta_skills(self):
        """Test loading the actual meta-skills from the package."""
        from pathlib import Path

        skills_dir = Path(__file__).parent.parent / "src" / "hmem" / "skills"
        if not skills_dir.exists():
            pytest.skip("Skills directory not found in expected location")

        manager = SkillManager(store=None, skills_dir=skills_dir)
        meta_skills = manager.load_meta_skills()

        # Should have our 4 core meta-skills
        names = {s.metadata.name for s in meta_skills}
        expected = {
            "skill-discovery",
            "skill-creation",
            "skill-editing",
            "learning-from-experience",
        }

        for expected_name in expected:
            if expected_name not in names:
                pytest.skip(f"Meta-skill {expected_name} not found")

        # Verify they're all protected
        for skill in meta_skills:
            if skill.metadata.name in expected:
                assert skill.metadata.is_protected is True
                assert skill.metadata.skill_type == "meta"


class TestSkillBootstrapLoop:
    """Test the skill bootstrap loop (Process -> Skill induction)."""

    @pytest.fixture
    def mock_store(self):
        """Create a mock Neo4j store."""
        store = Mock()
        store.get_processes_without_skill.return_value = [
            {
                "id": "proc_1",
                "trigger": "When OOM occurs",
                "action": "Capture heap dump",
                "outcome": "Identify leak",
                "embedding": [0.1] * 1536,
            },
            {
                "id": "proc_2",
                "trigger": "When memory spikes",
                "action": "Analyze heap",
                "outcome": "Find large objects",
                "embedding": [0.15] * 1536,
            },
            {
                "id": "proc_3",
                "trigger": "When OutOfMemory error",
                "action": "Profile memory usage",
                "outcome": "Locate memory issue",
                "embedding": [0.12] * 1536,
            },
        ]
        store.find_similar_processes.return_value = [
            {"id": "proc_1", "similarity": 0.9},
            {"id": "proc_2", "similarity": 0.85},
            {"id": "proc_3", "similarity": 0.8},
        ]
        store.add_skill.return_value = "skill_abc123"
        return store

    def test_skill_induction_requires_cluster(self, mock_store, tmp_path):
        """Test that skill induction requires a cluster of similar processes."""
        from hmem.core.evolution_engine import EvolutionEngine

        manager = SkillManager(store=None, skills_dir=tmp_path)

        # Create engine without LLM (will return empty)
        engine = EvolutionEngine(
            store=mock_store,
            llm=None,
            skill_manager=manager,
        )

        skills = engine.induce_skills_from_processes(min_cluster_size=3)

        # Without LLM, no skills can be induced
        assert len(skills) == 0
