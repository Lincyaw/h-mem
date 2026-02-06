"""Skill-aware agent with dynamic prompt building.

Provides SkillAwarePromptBuilder for building system prompts with
dynamically loaded skills from the self-bootstrapping skill system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

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
