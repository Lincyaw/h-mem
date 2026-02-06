"""Self-bootstrapping Skill System for h-mem.

This package implements a Claude Code-like skill system that allows agents
to dynamically load, create, edit, and evolve their own skills.

Directory Structure:
    skills/
    ├── _meta/                    # Protected meta-skills (hand-crafted)
    │   ├── skill-discovery/SKILL.md
    │   ├── skill-creation/SKILL.md
    │   ├── skill-editing/SKILL.md
    │   └── learning-from-experience/SKILL.md
    └── generated/                # Agent-generated skills from Process/Fact induction
        └── {skill-name}/SKILL.md

Key Classes:
    - SkillManager: Main interface for loading, creating, and managing skills
    - SkillMetadata: Pydantic model for skill YAML frontmatter
    - SkillSummary: Lightweight summary for search results
    - SkillLoader: File system loader for SKILL.md files

Tools:
    - SkillSearchTool: Vector search for relevant skills
    - SkillLoadTool: Load full skill content by name
    - SkillCreateTool: Create new skills from patterns
    - SkillEditTool: Edit existing skills
    - SkillFeedbackTool: Provide feedback on skill effectiveness
    - ProcessSearchTool: Search for similar processes
"""

from hmem.skills.models import SkillMetadata, SkillSummary
from hmem.skills.loader import SkillLoader
from hmem.skills.manager import SkillManager

__all__ = [
    "SkillManager",
    "SkillMetadata",
    "SkillSummary",
    "SkillLoader",
]
