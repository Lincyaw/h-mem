"""Pydantic models for the Skill system.

This module defines the data structures for skill metadata and summaries,
following the SKILL.md YAML frontmatter format.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class SkillMetadata(BaseModel):
    """Full metadata from SKILL.md YAML frontmatter.

    SKILL.md format:
    ```yaml
    ---
    name: entity-extraction
    description: Use when extracting entities from conversations
    trigger_pattern: "When processing a conversation for knowledge extraction"
    source_process_ids: [proc_xxx, proc_yyy]  # Provenance (generated only)
    source_fact_ids: [fact_zzz]                # Provenance (generated only)
    tags: [extraction, entity]
    version: 1
    is_protected: false
    ---

    # Skill Content (Markdown)
    ...
    ```
    """

    # Core identification
    name: str = Field(description="Unique skill name (kebab-case)")
    description: str = Field(description="When to use this skill")
    trigger_pattern: str = Field(
        default="",
        description="Pattern describing when this skill should be triggered",
    )

    # Classification
    tags: list[str] = Field(default_factory=list, description="Skill tags for search")
    skill_type: Literal["meta", "generated"] = Field(
        default="generated",
        description="meta = hand-crafted protected skills, generated = agent-created",
    )

    # Provenance (for generated skills)
    source_process_ids: list[str] = Field(
        default_factory=list,
        description="Process IDs this skill was induced from",
    )
    source_fact_ids: list[str] = Field(
        default_factory=list,
        description="Fact IDs that contributed to this skill",
    )

    # Version and status
    version: int = Field(default=1, ge=1, description="Skill version number")
    is_protected: bool = Field(
        default=False,
        description="Protected skills require confirmation to edit/delete",
    )
    is_suspended: bool = Field(
        default=False,
        description="Suspended skills are not returned in searches",
    )

    # Q-value tracking (synced with Neo4j)
    q_value: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Learned utility Q-value",
    )
    q_update_count: int = Field(
        default=0,
        ge=0,
        description="Number of Q-value updates",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this skill was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this skill was last updated",
    )

    # File path (set by loader)
    file_path: str | None = Field(
        default=None,
        description="Path to the SKILL.md file",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "entity-extraction",
                "description": "Use when extracting entities from conversations",
                "trigger_pattern": "When processing a conversation for knowledge extraction",
                "tags": ["extraction", "entity"],
                "skill_type": "generated",
                "source_process_ids": ["proc_abc123", "proc_def456"],
                "version": 1,
                "is_protected": False,
                "q_value": 0.75,
                "q_update_count": 10,
            }
        }
    }


class SkillSummary(BaseModel):
    """Lightweight skill summary for search results.

    Contains only the essential information needed to display
    search results without loading full skill content.
    """

    name: str = Field(description="Skill name")
    description: str = Field(description="Brief description")
    tags: list[str] = Field(default_factory=list)
    skill_type: Literal["meta", "generated"] = Field(default="generated")
    q_value: float = Field(default=0.5)
    version: int = Field(default=1)
    is_protected: bool = Field(default=False)

    # Search result fields
    similarity_score: float | None = Field(
        default=None,
        description="Similarity score from vector search (0-1)",
    )
    match_reason: str | None = Field(
        default=None,
        description="Why this skill matched the query",
    )

    @classmethod
    def from_metadata(
        cls,
        metadata: SkillMetadata,
        similarity_score: float | None = None,
        match_reason: str | None = None,
    ) -> "SkillSummary":
        """Create summary from full metadata."""
        return cls(
            name=metadata.name,
            description=metadata.description,
            tags=metadata.tags,
            skill_type=metadata.skill_type,
            q_value=metadata.q_value,
            version=metadata.version,
            is_protected=metadata.is_protected,
            similarity_score=similarity_score,
            match_reason=match_reason,
        )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "entity-extraction",
                "description": "Use when extracting entities from conversations",
                "tags": ["extraction", "entity"],
                "skill_type": "generated",
                "q_value": 0.75,
                "version": 1,
                "is_protected": False,
                "similarity_score": 0.92,
                "match_reason": "Matches trigger pattern for entity extraction",
            }
        }
    }


class SkillContent(BaseModel):
    """Full skill content including metadata and markdown body.

    Used when a skill is fully loaded for execution.
    """

    metadata: SkillMetadata = Field(description="Skill metadata from YAML frontmatter")
    content: str = Field(description="Markdown content body")

    @property
    def name(self) -> str:
        """Convenience accessor for skill name."""
        return self.metadata.name

    @property
    def description(self) -> str:
        """Convenience accessor for skill description."""
        return self.metadata.description

    def to_prompt(self) -> str:
        """Format skill as a prompt string for injection into agent context.

        Returns:
            Formatted skill content ready for system prompt injection
        """
        return f"""<skill name="{self.metadata.name}">
{self.content}
</skill>"""

    model_config = {
        "json_schema_extra": {
            "example": {
                "metadata": {
                    "name": "entity-extraction",
                    "description": "Use when extracting entities",
                    "tags": ["extraction"],
                },
                "content": "# Entity Extraction\n\nWhen extracting entities...",
            }
        }
    }


class ProcessSummary(BaseModel):
    """Summary of a Process for skill creation candidates.

    Used when searching for similar processes that could be
    abstracted into a new skill.
    """

    id: str = Field(description="Process ID")
    trigger: str = Field(description="Trigger condition")
    action: str = Field(description="Action description")
    outcome: str | None = Field(default=None, description="Expected outcome")
    context: str | None = Field(default=None, description="背景上下文")
    problem_statement: str | None = Field(default=None, description="问题陈述")
    key_insight: str | None = Field(default=None, description="核心洞察")
    similarity_score: float | None = Field(
        default=None,
        description="Similarity to query",
    )
    q_value: float = Field(default=0.5)
    q_update_count: int = Field(default=0)

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "proc_abc123",
                "trigger": "When encountering OOM error",
                "action": "Capture heap dump then analyze large objects",
                "outcome": "Identify memory leak source",
                "context": "Production environment with high memory usage",
                "problem_statement": "应用程序内存溢出问题",
                "key_insight": "大对象集合导致的内存泄漏",
                "similarity_score": 0.85,
                "q_value": 0.7,
            }
        }
    }
