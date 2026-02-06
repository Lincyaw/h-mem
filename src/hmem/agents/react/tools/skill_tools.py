"""Skill tools adapted for the ReAct Agent Loop.

These adapters wrap the existing skill tools to conform to the
BaseTool interface for use in the ReAct agent loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from hmem.agents.react.errors import ToolError
from hmem.agents.react.tool_base import BaseTool, ToolConfig, ToolSchema

if TYPE_CHECKING:
    from hmem.skills.manager import SkillManager


class SkillSearchToolAdapter(BaseTool[list[dict[str, Any]]]):
    """Search for relevant skills by query.

    Returns a list of skill summaries with name, description,
    similarity score, and match reason.
    """

    def __init__(
        self,
        manager: SkillManager,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="skill_search",
            description="Search for relevant skills by query text. Returns skill names, descriptions, and relevance scores.",
            config=config,
        )
        self.manager = manager

    def run(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search for skills matching the query.

        Args:
            query: Search query text
            limit: Maximum number of results (default 5)

        Returns:
            List of skill summary dicts with name, description, score, reason
        """
        try:
            results = self.manager.search(query, limit=limit)
            return [
                {
                    "name": r.name,
                    "description": r.description,
                    "similarity_score": r.similarity_score,
                    "match_reason": r.match_reason,
                    "tags": r.tags,
                    "q_value": r.q_value,
                }
                for r in results
            ]
        except Exception as e:
            raise ToolError(
                message=f"Skill search failed: {e}",
                tool_name=self.name,
            ) from e

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "query": {
                    "type": "string",
                    "description": "Search query text",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default 5)",
                },
            },
            required=["query"],
        )


class SkillLoadToolAdapter(BaseTool[dict[str, str] | None]):
    """Load full skill content by name.

    Returns the skill name and content formatted for prompt injection,
    or None if the skill is not found.
    """

    def __init__(
        self,
        manager: SkillManager,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="skill_load",
            description="Load full skill content by name. Returns the skill content formatted for use in the current task.",
            config=config,
        )
        self.manager = manager

    def run(self, skill_name: str) -> dict[str, str] | None:
        """Load full skill content.

        Args:
            skill_name: Skill name (kebab-case)

        Returns:
            Dict with "name" and "content" keys, or None if not found
        """
        try:
            content = self.manager.load(skill_name)
            if content:
                return {
                    "name": content.metadata.name,
                    "content": content.to_prompt(),
                }
            return None
        except Exception as e:
            raise ToolError(
                message=f"Skill load failed: {e}",
                tool_name=self.name,
            ) from e

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "skill_name": {
                    "type": "string",
                    "description": "Skill name in kebab-case (e.g., 'entity-extraction')",
                },
            },
            required=["skill_name"],
        )


class SkillCreateToolAdapter(BaseTool[str | None]):
    """Create a new skill from learned patterns.

    Returns the skill name if created successfully, or None if
    validation failed (e.g., insufficient source processes, rate limit).
    """

    def __init__(
        self,
        manager: SkillManager,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="skill_create",
            description="Create a new skill from learned patterns. Requires at least 2 source processes.",
            config=config,
        )
        self.manager = manager

    def run(
        self,
        name: str,
        description: str,
        content: str,
        trigger_pattern: str = "",
        tags: list[str] | None = None,
        source_process_ids: list[str] | None = None,
        source_fact_ids: list[str] | None = None,
    ) -> str | None:
        """Create a new generated skill.

        Args:
            name: Skill name (will be normalized to kebab-case)
            description: When to use this skill
            content: Markdown content body with instructions
            trigger_pattern: Pattern for when to trigger
            tags: Classification tags
            source_process_ids: Process IDs this skill was induced from
            source_fact_ids: Fact IDs that contributed

        Returns:
            Skill name if created, None if validation failed
        """
        try:
            # Normalize name to kebab-case
            normalized_name = name.lower().replace(" ", "-").replace("_", "-")

            return self.manager.create(
                name=normalized_name,
                description=description,
                content=content,
                trigger_pattern=trigger_pattern,
                tags=tags,
                source_process_ids=source_process_ids,
                source_fact_ids=source_fact_ids,
            )
        except Exception as e:
            raise ToolError(
                message=f"Skill create failed: {e}",
                tool_name=self.name,
            ) from e

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "name": {
                    "type": "string",
                    "description": "Skill name (kebab-case)",
                },
                "description": {
                    "type": "string",
                    "description": "When to use this skill",
                },
                "content": {
                    "type": "string",
                    "description": "Markdown content body with instructions",
                },
                "trigger_pattern": {
                    "type": "string",
                    "description": "Pattern for when to trigger",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Classification tags",
                },
                "source_process_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Process IDs this skill was induced from",
                },
                "source_fact_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fact IDs that contributed",
                },
            },
            required=["name", "description", "content"],
        )


class SkillFeedbackToolAdapter(BaseTool[None]):
    """Provide feedback on skill effectiveness.

    Updates the skill's Q-value based on whether it was helpful.
    """

    def __init__(
        self,
        manager: SkillManager,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="skill_feedback",
            description="Provide feedback on whether a skill was helpful. This updates the skill's Q-value.",
            config=config,
        )
        self.manager = manager

    def run(
        self,
        skill_name: str,
        outcome: Literal["success", "failure", "partial"],
    ) -> None:
        """Apply feedback to a skill.

        Args:
            skill_name: Skill to provide feedback for
            outcome: "success", "failure", or "partial"
        """
        try:
            self.manager.apply_feedback(skill_name, outcome)
        except Exception as e:
            raise ToolError(
                message=f"Skill feedback failed: {e}",
                tool_name=self.name,
            ) from e

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "skill_name": {
                    "type": "string",
                    "description": "Skill to provide feedback for",
                },
                "outcome": {
                    "type": "string",
                    "enum": ["success", "failure", "partial"],
                    "description": "Outcome of using the skill",
                },
            },
            required=["skill_name", "outcome"],
        )


class ProcessSearchToolAdapter(BaseTool[list[dict[str, Any]]]):
    """Search for similar processes (for skill creation candidates).

    Helps find clusters of similar processes that could be
    abstracted into a new skill.
    """

    def __init__(
        self,
        manager: SkillManager,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="find_similar_processes",
            description="Search for similar processes that could become a skill. Use to find clusters of 2+ processes with similar triggers.",
            config=config,
        )
        self.manager = manager

    def run(self, trigger_pattern: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search for similar processes.

        Args:
            trigger_pattern: Trigger text to search by
            limit: Maximum results

        Returns:
            List of process summary dicts
        """
        try:
            results = self.manager.search_processes(trigger_pattern, limit=limit)
            return [
                {
                    "id": r.id,
                    "trigger": r.trigger,
                    "action": r.action,
                    "outcome": r.outcome,
                    "similarity_score": r.similarity_score,
                    "q_value": r.q_value,
                }
                for r in results
            ]
        except Exception as e:
            raise ToolError(
                message=f"Process search failed: {e}",
                tool_name=self.name,
            ) from e

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "trigger_pattern": {
                    "type": "string",
                    "description": "Trigger text to search by",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 10)",
                },
            },
            required=["trigger_pattern"],
        )


def create_skill_tool_adapters(manager: SkillManager) -> list[BaseTool]:
    """Create all skill tool adapters from a SkillManager instance.

    Args:
        manager: SkillManager instance

    Returns:
        List of BaseTool instances ready for registration
    """
    return [
        SkillSearchToolAdapter(manager),
        SkillLoadToolAdapter(manager),
        SkillCreateToolAdapter(manager),
        SkillFeedbackToolAdapter(manager),
        ProcessSearchToolAdapter(manager),
    ]
