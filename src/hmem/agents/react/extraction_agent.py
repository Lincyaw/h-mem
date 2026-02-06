"""Extraction Agent - Skill-aware knowledge extraction from conversations.

Provides a factory function to create a ReAct agent configured for
knowledge extraction tasks. The agent can:
- Load and follow the knowledge-extraction skill
- Check for duplicate entities/facts
- Extract structured knowledge with proper scope classification
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, Field

from hmem.agents.llm import LLMClient
from hmem.agents.react.loop import AgentLoop, AgentLoopConfig
from hmem.agents.react.prompts import EXTRACTION_OBJECTIVE
from hmem.agents.react.tasks import ExtractionOutput
from hmem.agents.react.tool_base import ToolRegistry
from hmem.agents.react.tools.extraction_tools import (
    FactDeduplicationTool,
    ProcessSimilarityTool,
)
from hmem.agents.react.tools.memory_tools import (
    EntityLookupTool,
    FactSearchTool,
)
from hmem.agents.react.tools.skill_tools import (
    SkillLoadToolAdapter,
    SkillSearchToolAdapter,
)
from hmem.models import Attribute, Entity, Process

if TYPE_CHECKING:
    from hmem.config import AgentConfig
    from hmem.skills.manager import SkillManager
    from hmem.storage.neo4j_unified import Neo4jUnifiedStore

logger = structlog.get_logger()


class ExtractedKnowledge(BaseModel):
    """Result of knowledge extraction from a conversation."""

    entities: list[Entity] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {attribute: Attribute, entity_name: str}",
    )
    processes: list[Process] = Field(default_factory=list)
    summary: str = ""


class ExtractionAgent:
    """Skill-aware knowledge extraction agent.

    Uses the ReAct loop with tools for:
    - Skill search and loading (to follow extraction guidelines)
    - Entity lookup (to avoid duplicates)
    - Fact deduplication
    - Process similarity checking

    Example:
        >>> agent = ExtractionAgent(store=neo4j_store, skill_manager=manager)
        >>> result = agent.extract(conversation_text, conv_id="conv123")
        >>> print(f"Found {len(result.entities)} entities")
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore,
        skill_manager: SkillManager,
        llm_client: LLMClient | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        """Initialize the extraction agent.

        Args:
            store: Neo4j unified store for memory operations
            skill_manager: Skill manager for loading extraction skills
            llm_client: LLM client (creates default if None)
            config: Agent configuration
        """
        self.store = store
        self.skill_manager = skill_manager
        self.llm = llm_client or LLMClient()

        # Build tool registry
        self.registry = self._build_registry()

        # Create agent loop config with extraction-specific defaults
        # Extraction should complete quickly - 10 iterations max
        if config:
            loop_config = AgentLoopConfig(
                max_iterations=min(
                    config.max_iterations, 10
                ),  # Cap at 10 for extraction
                timeout_seconds=config.timeout_seconds,
                stuck_threshold=config.stuck_threshold,
                max_format_retries=config.max_format_retries,
                tool_retry_default=config.tool_retry_default,
                enable_parallel_tools=config.enable_parallel_tools,
                max_workers=config.max_workers,
            )
        else:
            loop_config = AgentLoopConfig(
                max_iterations=10,  # Extraction should complete in 10 iterations
                timeout_seconds=120,  # 2 minute timeout for extraction
            )

        self.loop = AgentLoop(
            llm=self.llm,
            registry=self.registry,
            config=loop_config,
        )

    def _build_registry(self) -> ToolRegistry:
        """Build the tool registry with extraction tools."""
        registry = ToolRegistry()

        # Skill tools - for loading the knowledge-extraction skill
        registry.register(SkillSearchToolAdapter(self.skill_manager))
        registry.register(SkillLoadToolAdapter(self.skill_manager))

        # Memory tools - for checking existing entities/facts
        registry.register(EntityLookupTool(self.store))
        registry.register(FactSearchTool(self.store))

        # Extraction tools - for deduplication
        registry.register(FactDeduplicationTool(self.store))
        registry.register(ProcessSimilarityTool(self.store))

        return registry

    def extract(
        self,
        conversation_text: str,
        conv_id: str = "",
        context: str = "",
    ) -> ExtractedKnowledge:
        """Extract structured knowledge from conversation text.

        The agent will:
        1. Search for and load the knowledge-extraction skill
        2. Follow the skill's guidance for extraction
        3. Check for duplicate entities and facts
        4. Return structured knowledge with proper scope classification

        Args:
            conversation_text: Full conversation text to analyze
            conv_id: Conversation ID for provenance tracking
            context: Optional additional context

        Returns:
            ExtractedKnowledge with entities, attributes, and processes
        """
        # Build the objective
        objective = EXTRACTION_OBJECTIVE.format(
            conversation_text=conversation_text,  # Limit length
        )

        # Add context
        agent_context = {
            "conversation_id": conv_id,
            "task": "knowledge_extraction",
        }
        if context:
            agent_context["additional_context"] = context

        logger.info(
            "starting_extraction_agent",
            conv_id=conv_id,
            text_length=len(conversation_text),
        )

        try:
            # Run the agent
            result = self.loop.run(
                objective=objective,
                context=agent_context,
                output_schema=ExtractionOutput,
            )

            logger.info(
                "extraction_agent_result",
                conv_id=conv_id,
                result_type=type(result).__name__,
                has_result=result is not None,
            )

            # Convert agent output to ExtractedKnowledge
            return self._parse_result(result, conv_id)

        except Exception as e:
            logger.warning(
                "extraction_agent_failed",
                conv_id=conv_id,
                error=str(e),
                exc_info=True,
            )
            # Return empty result on failure
            return ExtractedKnowledge()

    def _parse_result(
        self,
        result: ExtractionOutput | dict | None,
        conv_id: str,
    ) -> ExtractedKnowledge:
        """Parse agent result into ExtractedKnowledge.

        Args:
            result: Agent output (ExtractionOutput or dict)
            conv_id: Conversation ID for provenance

        Returns:
            ExtractedKnowledge with converted models
        """
        if result is None:
            return ExtractedKnowledge()

        # Handle both ExtractionOutput model and dict
        if isinstance(result, ExtractionOutput):
            raw_entities = result.entities
            raw_attributes = result.attributes
            raw_processes = result.processes
            summary = result.summary
        elif isinstance(result, dict):
            raw_entities = result.get("entities", [])
            raw_attributes = result.get("attributes", [])
            raw_processes = result.get("processes", [])
            summary = result.get("summary", "")
        else:
            return ExtractedKnowledge()

        # Convert to model objects
        entities = []
        for e in raw_entities:
            if isinstance(e, Entity):
                e.metadata = {"source_conv_id": conv_id}
                entities.append(e)
            elif isinstance(e, dict) and "name" in e:
                entity = Entity(
                    canonical_name=e.get("name", e.get("canonical_name", "")),
                    entity_type=e.get("type", e.get("entity_type", "CONCEPT")),
                    needs_resolution=e.get(
                        "is_reference", e.get("needs_resolution", False)
                    ),
                    metadata={"source_conv_id": conv_id},
                )
                entities.append(entity)

        attributes = []
        for a in raw_attributes:
            if isinstance(a, dict):
                # Check if it's already in the expected format
                if "attribute" in a and "entity_name" in a:
                    attr = a["attribute"]
                    if isinstance(attr, Attribute):
                        attr.parent_ids = [conv_id]
                        attributes.append(a)
                    elif isinstance(attr, dict):
                        attribute = Attribute(
                            entity_id="",
                            slot=attr.get("slot", ""),
                            value=attr.get("value", ""),
                            cardinality=attr.get("cardinality", "single"),
                            scope=attr.get("scope", "universal"),
                            scope_context=attr.get("scope_context"),
                            parent_ids=[conv_id],
                        )
                        attributes.append(
                            {"attribute": attribute, "entity_name": a["entity_name"]}
                        )
                # Direct format from agent output
                elif "entity_name" in a and "slot" in a and "value" in a:
                    # Skip session-scoped attributes
                    scope = a.get("scope", "universal")
                    if scope == "session":
                        continue

                    attribute = Attribute(
                        entity_id="",
                        slot=a["slot"],
                        value=a["value"],
                        cardinality=a.get("cardinality", "single"),
                        scope=scope,
                        scope_context=a.get("scope_context"),
                        parent_ids=[conv_id],
                    )
                    attributes.append(
                        {"attribute": attribute, "entity_name": a["entity_name"]}
                    )

        processes = []
        for p in raw_processes:
            if isinstance(p, Process):
                p.parent_ids = [conv_id]
                processes.append(p)
            elif isinstance(p, dict) and "trigger" in p and "action" in p:
                # Skip non-generalizable processes
                is_generalizable = p.get("is_generalizable", True)
                if not is_generalizable:
                    continue

                process = Process(
                    trigger=p["trigger"],
                    action=p["action"],
                    outcome=p.get("outcome"),
                    context=p.get("context"),
                    problem_statement=p.get("problem_statement"),
                    key_insight=p.get("key_insight"),
                    is_generalizable=True,
                    parent_ids=[conv_id],
                )
                processes.append(process)

        logger.info(
            "extraction_parsing_completed",
            conv_id=conv_id,
            entities=len(entities),
            attributes=len(attributes),
            processes=len(processes),
        )

        return ExtractedKnowledge(
            entities=entities,
            attributes=attributes,
            processes=processes,
            summary=summary,
        )


def create_extraction_agent(
    store: Neo4jUnifiedStore,
    skill_manager: SkillManager,
    llm_client: LLMClient | None = None,
    config: AgentConfig | None = None,
) -> ExtractionAgent:
    """Factory function to create an extraction agent.

    Args:
        store: Neo4j unified store
        skill_manager: Skill manager instance
        llm_client: Optional LLM client
        config: Optional agent configuration

    Returns:
        Configured ExtractionAgent
    """
    return ExtractionAgent(
        store=store,
        skill_manager=skill_manager,
        llm_client=llm_client,
        config=config,
    )
