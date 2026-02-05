"""Tests for SkillStore implementation."""

import tempfile
from pathlib import Path

import pytest

from hmem.storage.skill import SkillStore


class TestSkillStoreBasics:
    """Basic SkillStore functionality tests."""

    def test_add_and_get_skill(self):
        """Test adding and retrieving a skill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SkillStore(Path(tmpdir) / "skills.db")

            skill_id = store.add_skill(
                name="web_scraping",
                trigger_pattern="parse HTML|scrape website",
                code_template={"steps": ["fetch", "parse", "extract"]},
                description="Web scraping workflow",
            )

            assert skill_id.startswith("skill_")

            skill = store.get_skill("web_scraping")
            assert skill is not None
            assert skill.name == "web_scraping"
            assert skill.trigger_pattern == "parse HTML|scrape website"
            assert skill.code_template["steps"] == ["fetch", "parse", "extract"]

    def test_search_by_trigger(self):
        """Test searching skills by trigger pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SkillStore(Path(tmpdir) / "skills.db")

            store.add_skill(
                name="web_scraping",
                trigger_pattern="parse HTML|scrape website|extract data",
                code_template={"steps": ["fetch", "parse"]},
            )

            matches = store.search_by_trigger("how to scrape a website")
            assert len(matches) > 0
            assert matches[0].name == "web_scraping"

    def test_success_rate_tracking(self):
        """Test recording success/failure updates Q-value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SkillStore(Path(tmpdir) / "skills.db")

            skill_id = store.add_skill(
                name="test_skill",
                trigger_pattern="test pattern",
                code_template={},
            )

            # Initial Q-value is 0.5 (default for new skills)
            skill = store.get_skill("test_skill")
            assert skill is not None
            assert skill.index_profile.q_value == pytest.approx(0.5)

            # Record 2 successes, 1 failure -> Q-value should adjust
            store.record_success(skill_id)
            store.record_success(skill_id)
            store.record_failure(skill_id)

            updated = store.get_skill("test_skill")
            assert updated is not None
            # After 2 successes and 1 failure with alpha=0.1:
            # Q0=0.5, Q1=0.55, Q2=0.595, Q3=0.5355
            assert updated.index_profile.q_value == pytest.approx(0.5355, rel=0.01)
            assert updated.index_profile.q_update_count == 3

    def test_skill_store_stats(self):
        """Test getting store statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SkillStore(Path(tmpdir) / "skills.db")

            assert store.get_stats()["total_skills"] == 0

            store.add_skill("skill1", "pattern1", {})
            store.add_skill("skill2", "pattern2", {})

            stats = store.get_stats()
            assert stats["total_skills"] == 2

    def test_skill_store_health_check(self):
        """Test health check returns proper status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SkillStore(Path(tmpdir) / "skills.db")

            health = store.health_check()
            assert health["status"] == "healthy"

    def test_search_returns_memory_objects(self):
        """Test that search() returns Memory objects for RetrievalEngine."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SkillStore(Path(tmpdir) / "skills.db")

            store.add_skill(
                name="search_skill",
                trigger_pattern="search and find",
                code_template={"action": "search"},
            )

            memories = store.search("find something", limit=10)
            assert len(memories) > 0
            assert memories[0].source == "skill"
            assert "search_skill" in memories[0].content

    def test_list_all_skills(self):
        """Test listing all skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SkillStore(Path(tmpdir) / "skills.db")

            store.add_skill("skill_a", "pattern_a", {})
            store.add_skill("skill_b", "pattern_b", {})
            store.add_skill("skill_c", "pattern_c", {})

            all_skills = store.list_all()
            assert len(all_skills) == 3
            names = [s.name for s in all_skills]
            assert "skill_a" in names
            assert "skill_b" in names
            assert "skill_c" in names

    def test_delete_skill(self):
        """Test deleting a skill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SkillStore(Path(tmpdir) / "skills.db")

            store.add_skill("to_delete", "pattern", {})
            assert store.get_skill("to_delete") is not None

            deleted = store.delete_skill("to_delete")
            assert deleted is True
            assert store.get_skill("to_delete") is None
