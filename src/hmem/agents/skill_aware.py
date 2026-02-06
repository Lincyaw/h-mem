"""Skill-aware agent with dynamic prompt building.

Provides a base class for agents that can discover, load, and use
skills from the self-bootstrapping skill system. Skills are injected
into the agent's system prompt dynamically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from hmem.skills.models import SkillContent, SkillSummary

if TYPE_CHECKING:
    from hmem.skills.manager import SkillManager

logger = structlog.get_logger()


class SkillAwarePromptBuilder:
    """Builds system prompts with dynamically loaded skills.

    Injects skill listings and loaded skill content into agent prompts.
    Supports two injection modes:
    1. Skills index: List of available skills (always included)
    2. Active skills: Full content of loaded skills (on demand)

    Example:
        >>> builder = SkillAwarePromptBuilder(manager)
        >>> prompt = builder.build(
        ...     base_prompt="You are a memory assistant.",
        ...     active_skills=["entity-extraction", "debug-memory-leak"],
        ... )
    """

    def __init__(self, skill_manager: SkillManager):
        self.skill_manager = skill_manager
        self.logger = logger.bind(component="skill_prompt_builder")

    def build(
        self,
        base_prompt: str = "",
        active_skills: list[str] | None = None,
        include_meta_skills: bool = True,
        include_skill_index: bool = True,
    ) -> str:
        """Build a system prompt with skill injections.

        Args:
            base_prompt: Base system prompt text
            active_skills: List of skill names to load fully
            include_meta_skills: Whether to include meta-skill content
            include_skill_index: Whether to include available skills listing

        Returns:
            Complete system prompt with skills injected
        """
        parts: list[str] = []

        # Base prompt
        if base_prompt:
            parts.append(base_prompt)

        # Skills index section
        if include_skill_index:
            index = self._build_skills_index()
            if index:
                parts.append(index)

        # Meta-skills section
        if include_meta_skills:
            meta = self._build_meta_skills_section()
            if meta:
                parts.append(meta)

        # Active skills section
        if active_skills:
            active = self._build_active_skills_section(active_skills)
            if active:
                parts.append(active)

        return "\n\n".join(parts)

    def _build_skills_index(self) -> str:
        """Build a listing of all available skills.

        Returns:
            Formatted skills index text
        """
        available = self.skill_manager.list_available()
        if not available:
            return ""

        lines = ["## Available Skills", ""]
        lines.append("| Skill | Description | Q-Value | Type |")
        lines.append("|-------|-------------|---------|------|")

        for skill in available:
            q_display = f"{skill.q_value:.2f}"
            lines.append(
                f"| {skill.name} | {skill.description[:60]} | {q_display} | {skill.skill_type} |"
            )

        lines.append("")
        lines.append(
            "Use `skill_search` to find relevant skills and `skill_load` to load full content."
        )

        return "\n".join(lines)

    def _build_meta_skills_section(self) -> str:
        """Build meta-skills content section.

        Returns:
            Formatted meta-skills text
        """
        meta_skills = self.skill_manager.load_meta_skills()
        if not meta_skills:
            return ""

        parts = ["## Core Skills (Meta)", ""]
        for skill in meta_skills:
            parts.append(skill.to_prompt())
            parts.append("")

        return "\n".join(parts)

    def _build_active_skills_section(self, skill_names: list[str]) -> str:
        """Build active skills content section.

        Args:
            skill_names: Skills to load fully

        Returns:
            Formatted active skills text
        """
        parts = ["## Active Skills", ""]

        for name in skill_names:
            content = self.skill_manager.load(name)
            if content:
                parts.append(content.to_prompt())
                parts.append("")
            else:
                self.logger.warning("active_skill_not_found", name=name)

        return "\n".join(parts)


class SkillAwareContextMixin:
    """Mixin for adding skill awareness to existing agents.

    Provides methods for skill discovery, loading, and feedback
    that can be mixed into any agent class.

    Example:
        >>> class MyAgent(BaseMemoryAgent, SkillAwareContextMixin):
        ...     def __init__(self, store, skill_manager):
        ...         super().__init__(name="my_agent")
        ...         self.init_skill_awareness(skill_manager)
    """

    _skill_manager: SkillManager | None
    _prompt_builder: SkillAwarePromptBuilder | None
    _active_skills: list[str]
    _skills_used_in_session: list[str]

    def init_skill_awareness(self, skill_manager: SkillManager) -> None:
        """Initialize skill awareness for this agent.

        Args:
            skill_manager: SkillManager instance
        """
        self._skill_manager = skill_manager
        self._prompt_builder = SkillAwarePromptBuilder(skill_manager)
        self._active_skills = []
        self._skills_used_in_session = []

    @property
    def skill_manager(self) -> SkillManager | None:
        """Access the skill manager."""
        return self._skill_manager

    def discover_skills(self, query: str, limit: int = 5) -> list[SkillSummary]:
        """Search for relevant skills.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching skills
        """
        if not self._skill_manager:
            return []
        return self._skill_manager.search(query, limit=limit)

    def activate_skill(self, skill_name: str) -> SkillContent | None:
        """Load and activate a skill for the current session.

        Args:
            skill_name: Skill to activate

        Returns:
            Loaded SkillContent or None
        """
        if not self._skill_manager:
            return None

        content = self._skill_manager.load(skill_name)
        if content:
            if skill_name not in self._active_skills:
                self._active_skills.append(skill_name)
            if skill_name not in self._skills_used_in_session:
                self._skills_used_in_session.append(skill_name)
        return content

    def deactivate_skill(self, skill_name: str) -> None:
        """Deactivate a skill from the current session.

        Args:
            skill_name: Skill to deactivate
        """
        if skill_name in self._active_skills:
            self._active_skills.remove(skill_name)

    def provide_skill_feedback(self, skill_name: str, outcome: str) -> None:
        """Provide feedback on a skill's effectiveness.

        Args:
            skill_name: Skill to provide feedback for
            outcome: "success", "failure", or "partial"
        """
        if self._skill_manager:
            self._skill_manager.apply_feedback(skill_name, outcome)

    def provide_session_feedback(self, outcome: str) -> None:
        """Provide feedback for all skills used in this session.

        Args:
            outcome: "success", "failure", or "partial"
        """
        for skill_name in self._skills_used_in_session:
            self.provide_skill_feedback(skill_name, outcome)

    def build_skill_aware_prompt(self, base_prompt: str = "") -> str:
        """Build a prompt with current skill context.

        Args:
            base_prompt: Base system prompt

        Returns:
            Prompt with skills injected
        """
        if not self._prompt_builder:
            return base_prompt

        return self._prompt_builder.build(
            base_prompt=base_prompt,
            active_skills=self._active_skills,
        )

    def get_active_skills(self) -> list[str]:
        """Get list of currently active skills.

        Returns:
            List of active skill names
        """
        return list(self._active_skills)
