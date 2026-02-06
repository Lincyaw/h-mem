"""Task definitions and output schemas for ReAct agents.

Defines standard tasks (Extraction, Induction, Retrieval) with
their objectives, available tools, and output schemas.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractionOutput(BaseModel):
    """Output schema for knowledge extraction tasks."""

    entities: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted entities",
    )
    attributes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted attributes with entity references",
    )
    processes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted processes",
    )
    summary: str = Field(
        default="",
        description="Brief summary of what was extracted",
    )


class InductionOutput(BaseModel):
    """Output schema for skill induction tasks."""

    induced_skills: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Skills induced from processes",
    )
    clusters_analyzed: int = Field(
        default=0,
        description="Number of process clusters analyzed",
    )
    processes_used: int = Field(
        default=0,
        description="Total processes considered",
    )
    summary: str = Field(
        default="",
        description="Summary of induction results",
    )


class MemoryResult(BaseModel):
    """A single memory retrieval result."""

    id: str
    content: str
    score: float = Field(ge=0.0, le=1.0)
    source: str  # "entity", "fact", "process", "principle", "skill"
    relevance_reason: str = ""


class RetrievalOutput(BaseModel):
    """Output schema for memory retrieval tasks."""

    memories: list[MemoryResult] = Field(
        default_factory=list,
        description="Retrieved memories ranked by relevance",
    )
    total_found: int = Field(
        default=0,
        description="Total number of potential matches found",
    )
    query_refinements: list[str] = Field(
        default_factory=list,
        description="Query refinements tried during search",
    )
    summary: str = Field(
        default="",
        description="Summary of retrieval results",
    )


class TaskConfig(BaseModel):
    """Configuration for a specific task type."""

    task_type: Literal["extraction", "induction", "retrieval", "custom"]
    available_tools: list[str]
    max_iterations: int = Field(default=15, ge=1, le=50)
    timeout_seconds: int = Field(default=300, ge=30, le=3600)
    objective_template: str


# Predefined task configurations
EXTRACTION_TASK = TaskConfig(
    task_type="extraction",
    available_tools=[
        "skill_search",
        "skill_load",
        "entity_lookup",
        "fact_search",
        "fact_exists",
    ],
    max_iterations=15,
    timeout_seconds=300,
    objective_template="""\
Extract structured knowledge from the following conversation.

Identify:
1. **Entities**: People, projects, tools, organizations, concepts
2. **Attributes**: Facts about entities (with scope: universal/project/task)
3. **Processes**: Trigger → Action → Outcome patterns (mark if generalizable)

Conversation:
{conversation_text}

Use the available tools to:
- Check if entities already exist (entity_lookup)
- Avoid duplicate facts (fact_exists)
- Search for relevant skills (skill_search)
- Load applicable skills for guidance (skill_load)

Return a complete extraction result.""",
)

INDUCTION_TASK = TaskConfig(
    task_type="induction",
    available_tools=[
        "find_similar_processes",
        "skill_search",
        "skill_create",
        "skill_load",
    ],
    max_iterations=20,
    timeout_seconds=300,
    objective_template="""\
Induce reusable skills from accumulated processes.

Your goal:
1. Search for similar processes with common trigger patterns
2. Identify clusters of 2+ processes that follow the same pattern
3. Create skills that generalize these patterns
4. Only create skills for truly reusable patterns

Focus on patterns that would help future tasks.

{context}

Use the available tools to:
- Find similar processes (find_similar_processes)
- Check existing skills to avoid duplicates (skill_search)
- Create new skills from process clusters (skill_create)
- Load skills for reference (skill_load)

Return a summary of induced skills.""",
)

RETRIEVAL_TASK = TaskConfig(
    task_type="retrieval",
    available_tools=[
        "memory_vector_search",
        "memory_fulltext_search",
        "skill_search",
        "skill_load",
        "entity_lookup",
    ],
    max_iterations=10,
    timeout_seconds=120,
    objective_template="""\
Find relevant memories to answer the following query:

Query: {query}

Context: {context}

Use the available search tools to:
1. Find semantically similar memories (memory_vector_search)
2. Find keyword matches (memory_fulltext_search)
3. Look up specific entities (entity_lookup)
4. Search for applicable skills (skill_search)

Rank and filter results by relevance.
Return the most relevant memories with explanations.""",
)


def get_task_config(task_type: str) -> TaskConfig:
    """Get the configuration for a task type.

    Args:
        task_type: "extraction", "induction", or "retrieval"

    Returns:
        TaskConfig for the specified type

    Raises:
        ValueError: If task type is unknown
    """
    configs = {
        "extraction": EXTRACTION_TASK,
        "induction": INDUCTION_TASK,
        "retrieval": RETRIEVAL_TASK,
    }
    if task_type not in configs:
        raise ValueError(
            f"Unknown task type: {task_type}. Available: {list(configs.keys())}"
        )
    return configs[task_type]


def get_output_schema(task_type: str) -> type[BaseModel]:
    """Get the output schema for a task type.

    Args:
        task_type: "extraction", "induction", or "retrieval"

    Returns:
        Pydantic model class for the output

    Raises:
        ValueError: If task type is unknown
    """
    schemas: dict[str, type[BaseModel]] = {
        "extraction": ExtractionOutput,
        "induction": InductionOutput,
        "retrieval": RetrievalOutput,
    }
    if task_type not in schemas:
        raise ValueError(
            f"Unknown task type: {task_type}. Available: {list(schemas.keys())}"
        )
    return schemas[task_type]
