"""Skill tools for agent interaction with the skill system.

These tools provide the interface for agents to search, load, create,
edit, and provide feedback on skills. They follow the LangChain tool
pattern for easy integration with agent frameworks.

Tools:
    - SkillSearchTool: Search for relevant skills by query
    - SkillLoadTool: Load full skill content by name
    - SkillCreateTool: Create a new skill from learned patterns
    - SkillEditTool: Edit an existing skill
    - SkillFeedbackTool: Provide feedback on skill effectiveness
    - ProcessSearchTool: Search for similar processes
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import structlog

from hmem.skills.models import SkillSummary, ProcessSummary

if TYPE_CHECKING:
    from hmem.skills.manager import SkillManager

logger = structlog.get_logger()


class SkillSearchTool:
    """Search for relevant skills by query.

    Searches across skill names, descriptions, trigger patterns,
    and tags using keyword matching. For semantic search, the manager
    will use Neo4j vector search if available.

    Example:
        >>> tool = SkillSearchTool(manager)
        >>> results = tool.run("entity extraction from conversations")
        >>> for r in results:
        ...     print(f"{r.name}: {r.description} (score={r.similarity_score})")
    """

    name = "skill_search"
    description = "Search for relevant skills by query text"

    def __init__(self, manager: SkillManager):
        self.manager = manager
        self.logger = logger.bind(tool="skill_search")

    def run(self, query: str, limit: int = 5) -> list[SkillSummary]:
        """Search for skills matching the query.

        Args:
            query: Search query text
            limit: Maximum number of results

        Returns:
            List of SkillSummary objects sorted by relevance
        """
        self.logger.debug("skill_search", query=query[:50], limit=limit)
        return self.manager.search(query, limit=limit)


class SkillLoadTool:
    """Load full skill content by name.

    Returns the complete SKILL.md content formatted for prompt injection.

    Example:
        >>> tool = SkillLoadTool(manager)
        >>> content = tool.run("entity-extraction")
        >>> # content is ready for system prompt injection
    """

    name = "skill_load"
    description = "Load full skill content by name for use in current task"

    def __init__(self, manager: SkillManager):
        self.manager = manager
        self.logger = logger.bind(tool="skill_load")

    def run(self, skill_name: str) -> str | None:
        """Load full skill content.

        Args:
            skill_name: Skill name (kebab-case)

        Returns:
            Formatted skill content string, or None if not found
        """
        self.logger.debug("skill_load", name=skill_name)

        content = self.manager.load(skill_name)
        if content:
            return content.to_prompt()

        self.logger.warning("skill_not_found", name=skill_name)
        return None


class SkillCreateTool:
    """Create a new skill from learned patterns.

    Validates that sufficient similar processes exist before
    creating a new skill. Enforces rate limits and naming conventions.

    Example:
        >>> tool = SkillCreateTool(manager)
        >>> name = tool.run(
        ...     name="debug-memory-leak",
        ...     description="Use when debugging memory leaks in any system",
        ...     content="# Debug Memory Leak\\n...",
        ...     source_process_ids=["proc_abc", "proc_def"],
        ... )
    """

    name = "skill_create"
    description = "Create a new skill from learned patterns"

    def __init__(self, manager: SkillManager):
        self.manager = manager
        self.logger = logger.bind(tool="skill_create")

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
            name: Skill name (kebab-case, e.g., "debug-memory-leak")
            description: When to use this skill
            content: Markdown content body with instructions
            trigger_pattern: Pattern for when to trigger
            tags: Classification tags
            source_process_ids: Process IDs this skill was induced from
            source_fact_ids: Fact IDs that contributed

        Returns:
            Skill name if created, None if validation failed
        """
        # Normalize name to kebab-case
        name = name.lower().replace(" ", "-").replace("_", "-")

        self.logger.info(
            "skill_create_request",
            name=name,
            source_processes=len(source_process_ids or []),
        )

        return self.manager.create(
            name=name,
            description=description,
            content=content,
            trigger_pattern=trigger_pattern,
            tags=tags,
            source_process_ids=source_process_ids,
            source_fact_ids=source_fact_ids,
        )


class SkillEditTool:
    """Edit an existing skill.

    Supports content updates, metadata changes, and version bumping.
    Protected skills require explicit force flag.

    Example:
        >>> tool = SkillEditTool(manager)
        >>> success = tool.run(
        ...     skill_name="debug-memory-leak",
        ...     new_content="# Updated Content\\n...",
        ...     version_bump=True,
        ...     reason="Added step for heap analysis",
        ... )
    """

    name = "skill_edit"
    description = "Edit an existing skill's content or metadata"

    def __init__(self, manager: SkillManager):
        self.manager = manager
        self.logger = logger.bind(tool="skill_edit")

    def run(
        self,
        skill_name: str,
        new_content: str | None = None,
        metadata_updates: dict | None = None,
        version_bump: bool = False,
        reason: str = "",
        force: bool = False,
    ) -> bool:
        """Edit a skill.

        Args:
            skill_name: Skill to edit
            new_content: New markdown content (None to keep current)
            metadata_updates: Metadata fields to update
            version_bump: Whether to increment version number
            reason: Reason for the edit
            force: Required for editing protected skills

        Returns:
            True if edit successful
        """
        self.logger.info(
            "skill_edit_request",
            name=skill_name,
            version_bump=version_bump,
            reason=reason,
        )

        return self.manager.edit(
            skill_name=skill_name,
            new_content=new_content,
            metadata_updates=metadata_updates,
            version_bump=version_bump,
            reason=reason,
            force=force,
        )


class SkillFeedbackTool:
    """Provide feedback on skill effectiveness.

    Updates the skill's Q-value based on whether it was helpful.
    Skills with consistently low Q-values are auto-suspended.

    Example:
        >>> tool = SkillFeedbackTool(manager)
        >>> tool.run("debug-memory-leak", "success")
    """

    name = "skill_feedback"
    description = "Provide feedback on whether a skill was helpful"

    def __init__(self, manager: SkillManager):
        self.manager = manager
        self.logger = logger.bind(tool="skill_feedback")

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
        self.logger.info(
            "skill_feedback",
            name=skill_name,
            outcome=outcome,
        )

        self.manager.apply_feedback(skill_name, outcome)


class ProcessSearchTool:
    """Search for similar processes (for skill creation candidates).

    Helps agents find clusters of similar processes that could
    be abstracted into a new skill.

    Example:
        >>> tool = ProcessSearchTool(manager)
        >>> processes = tool.run("encountering OOM errors")
        >>> if len(processes) >= 2:
        ...     # Enough similar processes to induce a skill
        ...     create_skill(processes)
    """

    name = "process_search"
    description = "Search for similar processes that could become a skill"

    def __init__(self, manager: SkillManager):
        self.manager = manager
        self.logger = logger.bind(tool="process_search")

    def run(self, trigger_pattern: str, limit: int = 10) -> list[ProcessSummary]:
        """Search for similar processes.

        Args:
            trigger_pattern: Trigger text to search by
            limit: Maximum results

        Returns:
            List of ProcessSummary objects
        """
        self.logger.debug(
            "process_search",
            trigger=trigger_pattern[:50],
            limit=limit,
        )

        return self.manager.search_processes(trigger_pattern, limit=limit)


def create_skill_tools(manager: SkillManager) -> dict[str, object]:
    """Create all skill tools from a SkillManager instance.

    Convenience function to instantiate all tools at once.

    Args:
        manager: SkillManager instance

    Returns:
        Dictionary mapping tool names to tool instances
    """
    return {
        "skill_search": SkillSearchTool(manager),
        "skill_load": SkillLoadTool(manager),
        "skill_create": SkillCreateTool(manager),
        "skill_edit": SkillEditTool(manager),
        "skill_feedback": SkillFeedbackTool(manager),
        "process_search": ProcessSearchTool(manager),
    }
