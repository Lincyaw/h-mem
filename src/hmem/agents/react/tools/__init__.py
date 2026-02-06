"""Tools for the ReAct Agent Loop."""

from hmem.agents.react.tools.extraction_tools import (
    FactDeduplicationTool,
    ProcessSimilarityTool,
)
from hmem.agents.react.tools.memory_tools import (
    EntityLookupTool,
    FactSearchTool,
    MemoryFulltextSearchTool,
    MemoryVectorSearchTool,
)
from hmem.agents.react.tools.skill_tools import (
    ProcessSearchToolAdapter,
    SkillCreateToolAdapter,
    SkillFeedbackToolAdapter,
    SkillLoadToolAdapter,
    SkillSearchToolAdapter,
)

__all__ = [
    # Skill tools
    "SkillSearchToolAdapter",
    "SkillLoadToolAdapter",
    "SkillCreateToolAdapter",
    "SkillFeedbackToolAdapter",
    "ProcessSearchToolAdapter",
    # Memory tools
    "MemoryVectorSearchTool",
    "MemoryFulltextSearchTool",
    "EntityLookupTool",
    "FactSearchTool",
    # Extraction tools
    "FactDeduplicationTool",
    "ProcessSimilarityTool",
]
