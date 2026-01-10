"""Reflection agent using LangGraph for principle extraction.

This agent implements the "systems consolidation" process from design.md,
automatically discovering topics from episodic memories and extracting
generalizable principles.

Supports multiple entry points for flexible invocation:
- full_reflection: Complete workflow (fetch -> discover -> extract -> store)
- discover_topics: Only topic discovery
- extract_principles: Only principle extraction (requires topics in state)
"""

from typing import Any, Literal

import structlog
from langgraph.graph import END

from hmem.agents.base import AgentState, BaseMemoryAgent
from hmem.agents.llm import LLMClient
from hmem.hippocampus.topic_extraction import SemanticTopicExtractor, TopicCluster
from hmem.models import Event, Principle, SemanticTriple
from hmem.storage.chroma_episodic import ChromaEpisodicStore
from hmem.storage.sqlite_semantic import SQLiteSemanticStore
from hmem.storage.skill import SkillStore

logger = structlog.get_logger()


class ReflectionAgentState(AgentState):
    """Extended state for reflection agent."""

    discovered_topics: list[TopicCluster]
    qualified_topics: list[TopicCluster]
    extracted_principles: list[Principle]
    validated_principles: list[Principle]
    skills_generated: int
    stored_count: int


class ReflectionAgent(BaseMemoryAgent):
    """LangGraph-based reflection agent for principle extraction.

    Workflow:
    1. fetch_episodes: Load recent episodic memories
    2. discover_topics: Cluster episodes into semantic topics
    3. filter_topics: Select topics that meet quality criteria
    4. extract_principles: Generate principles for each topic via LLM
    5. validate_quality: Filter low-confidence principles
    6. store_results: Persist validated principles to semantic memory

    Entry Points:
    - fetch_episodes: Full workflow from scratch
    - discover_topics: Skip fetching, use provided episodes
    - extract_principles: Skip discovery, use provided topics

    Example:
        >>> agent = ReflectionAgent(episodic_store, semantic_store)
        >>> # Full workflow
        >>> result = agent.reflect()
        >>>
        >>> # Only discover topics
        >>> result = agent.run(
        ...     initial_state={"metadata": {"episodes": my_episodes}},
        ...     entry_point="discover_topics"
        ... )
    """

    def __init__(
        self,
        episodic_store: ChromaEpisodicStore,
        semantic_store: SQLiteSemanticStore,
        skill_store: SkillStore | None = None,
        llm_client: LLMClient | None = None,
        topic_extractor: SemanticTopicExtractor | None = None,
    ) -> None:
        """Initialize reflection agent.

        Args:
            episodic_store: Source for episodic memories
            semantic_store: Target for extracted principles
            skill_store: Target for generated skills (optional)
            llm_client: LLM client for principle generation
            topic_extractor: Topic extraction strategy
        """
        super().__init__(name="reflection_agent")

        self.episodic_store = episodic_store
        self.semantic_store = semantic_store
        self.skill_store = skill_store
        self.llm = llm_client or LLMClient()
        self.topic_extractor = topic_extractor or SemanticTopicExtractor(
            llm_client=self.llm
        )

        self._build_workflow()

    def _get_entry_points(self) -> list[str]:
        """Available entry points for reflection agent."""
        return ["fetch_episodes", "discover_topics", "extract_principles"]

    def _build_workflow(self) -> None:
        """Build the reflection workflow graph."""
        self.graph.add_node("fetch_episodes", self._fetch_episodes)  # type: ignore
        self.graph.add_node("discover_topics", self._discover_topics)  # type: ignore
        self.graph.add_node("filter_topics", self._filter_topics)  # type: ignore
        self.graph.add_node("extract_principles", self._extract_principles)  # type: ignore
        self.graph.add_node("validate_quality", self._validate_quality)  # type: ignore
        self.graph.add_node("generate_skills", self._generate_skills)  # type: ignore
        self.graph.add_node("store_results", self._store_results)  # type: ignore

        self.graph.set_entry_point("fetch_episodes")
        self.graph.add_edge("fetch_episodes", "discover_topics")
        self.graph.add_edge("discover_topics", "filter_topics")
        self.graph.add_conditional_edges(
            "filter_topics",
            self._should_continue_extraction,
            {"extract": "extract_principles", "end": END},
        )
        self.graph.add_edge("extract_principles", "validate_quality")
        self.graph.add_edge("validate_quality", "generate_skills")
        self.graph.add_edge("generate_skills", "store_results")
        self.graph.add_edge("store_results", END)

    def _fetch_episodes(self, state: dict[str, Any]) -> dict[str, Any]:
        """Step 1: Fetch all recent episodic memories."""
        self.logger.info("step_start", step="fetch_episodes")

        metadata = state.get("metadata", {})
        max_episodes = metadata.get("max_episodes", 500)

        memories = self.episodic_store.search("", limit=max_episodes)

        episodes = [
            Event(
                id=mem.metadata.get("id"),
                content=mem.content,
                outcome=mem.metadata.get("outcome", "unknown"),
                tags=[],
                timestamp=mem.timestamp,
                metadata=mem.metadata,
            )
            for mem in memories
        ]

        state["metadata"]["episodes"] = episodes
        state["current_step"] = "fetch_episodes"

        self.logger.info("episodes_fetched", count=len(episodes))

        return state

    def _discover_topics(self, state: dict[str, Any]) -> dict[str, Any]:
        """Step 2: Discover topics using semantic clustering."""
        self.logger.info("step_start", step="discover_topics")

        metadata = state.get("metadata", {})
        episodes = metadata.get("episodes", [])
        min_cluster_size = metadata.get("min_cluster_size", 5)

        topics = self.topic_extractor.extract_topics(
            episodes, min_cluster_size=min_cluster_size
        )

        state["metadata"]["discovered_topics"] = topics
        state["current_step"] = "discover_topics"

        self.logger.info(
            "topics_discovered",
            count=len(topics),
            labels=[t.label for t in topics],
        )

        return state

    def _filter_topics(self, state: dict[str, Any]) -> dict[str, Any]:
        """Step 3: Filter topics based on quality criteria."""
        self.logger.info("step_start", step="filter_topics")

        metadata = state.get("metadata", {})
        topics = metadata.get("discovered_topics", [])
        min_confidence = metadata.get("min_topic_confidence", 0.3)
        min_episodes_per_topic = metadata.get("min_episodes_per_topic", 5)

        qualified_topics = [
            t
            for t in topics
            if t.confidence >= min_confidence
            and len(t.episodes) >= min_episodes_per_topic
        ]

        state["metadata"]["qualified_topics"] = qualified_topics
        state["current_step"] = "filter_topics"

        self.logger.info(
            "topics_filtered",
            original=len(topics),
            qualified=len(qualified_topics),
        )

        return state

    def _should_continue_extraction(
        self, state: dict[str, Any]
    ) -> Literal["extract", "end"]:
        """Conditional routing: proceed if qualified topics exist."""
        qualified = state.get("metadata", {}).get("qualified_topics", [])
        return "extract" if qualified else "end"

    def _extract_principles(self, state: dict[str, Any]) -> dict[str, Any]:
        """Step 4: Extract principles for each qualified topic."""
        self.logger.info("step_start", step="extract_principles")

        metadata = state.get("metadata", {})
        qualified_topics: list[TopicCluster] = metadata.get("qualified_topics", [])
        principles: list[Principle] = []

        for topic in qualified_topics:
            try:
                principle = self.llm.reflect(topic.episodes)
                principle.parent_ids = [
                    e.id for e in topic.episodes if e.id is not None
                ]
                principle.metadata = {
                    "topic": topic.label,
                    "cluster_confidence": topic.confidence,
                    "episode_count": len(topic.episodes),
                }

                principles.append(principle)

                self.logger.info(
                    "principle_extracted",
                    topic=topic.label,
                    confidence=principle.confidence,
                    evidence_count=len(topic.episodes),
                )

            except Exception as e:
                self.logger.warning(
                    "principle_extraction_failed",
                    topic=topic.label,
                    error=str(e),
                )
                continue

        state["metadata"]["extracted_principles"] = principles
        state["current_step"] = "extract_principles"

        return state

    def _validate_quality(self, state: dict[str, Any]) -> dict[str, Any]:
        """Step 5: Validate principle quality."""
        self.logger.info("step_start", step="validate_quality")

        metadata = state.get("metadata", {})
        principles: list[Principle] = metadata.get("extracted_principles", [])
        min_confidence = metadata.get("validation_threshold", 0.5)

        validated = [p for p in principles if p.confidence >= min_confidence]

        state["metadata"]["validated_principles"] = validated
        state["current_step"] = "validate_quality"

        self.logger.info(
            "principles_validated",
            extracted=len(principles),
            validated=len(validated),
        )

        return state

    def _generate_skills(self, state: dict[str, Any]) -> dict[str, Any]:
        """Step 6: Convert actionable principles to executable skills.

        Uses LLM to determine if a principle is actionable (can be decomposed
        into concrete steps). Only actionable principles become skills.

        Non-actionable principles (observations, abstract rules) remain
        as semantic memory for guidance during planning.
        """
        self.logger.info("step_start", step="generate_skills")

        if not self.skill_store:
            self.logger.info("skill_generation_skipped", reason="no_skill_store")
            state["metadata"]["skills_generated"] = 0
            state["current_step"] = "generate_skills"
            return state

        metadata = state.get("metadata", {})
        principles: list[Principle] = metadata.get("validated_principles", [])
        skills_generated = 0

        for principle in principles:
            try:
                topic = principle.metadata.get("topic", "general")
                skill_template = self.llm.generate_skill(principle, topic)

                if skill_template:  # Only if LLM determined it's actionable
                    skill_id = self.skill_store.add_skill(
                        name=skill_template["name"],
                        trigger_pattern=skill_template["trigger_pattern"],
                        code_template={"steps": skill_template.get("steps", [])},
                        description=skill_template.get(
                            "description", principle.content
                        ),
                        parent_ids=principle.parent_ids,
                        derivation_type="induction",
                    )
                    skills_generated += 1

                    self.logger.info(
                        "skill_generated",
                        skill_id=skill_id,
                        skill_name=skill_template["name"],
                        from_principle=principle.content[:50],
                        topic=topic,
                    )
                else:
                    self.logger.debug(
                        "principle_not_actionable",
                        principle=principle.content[:50],
                        topic=topic,
                    )

            except Exception as e:
                self.logger.warning(
                    "skill_generation_failed",
                    principle=principle.content[:50],
                    error=str(e),
                )
                continue

        state["metadata"]["skills_generated"] = skills_generated
        state["current_step"] = "generate_skills"

        self.logger.info(
            "skills_generation_complete",
            principles_count=len(principles),
            skills_generated=skills_generated,
        )

        return state

    def _store_results(self, state: dict[str, Any]) -> dict[str, Any]:
        """Step 7: Store validated principles to semantic memory."""
        self.logger.info("step_start", step="store_results")

        metadata = state.get("metadata", {})
        principles: list[Principle] = metadata.get("validated_principles", [])
        stored_count = 0

        for principle in principles:
            try:
                topic = principle.metadata.get("topic", "general")
                triple = SemanticTriple(
                    subject="agent",
                    predicate="follows_principle",
                    object=principle.content,
                    weight=principle.confidence,
                    parent_ids=principle.parent_ids,
                )
                self.semantic_store.add_or_update(triple)
                stored_count += 1

                self.logger.info(
                    "principle_stored",
                    topic=topic,
                    content=principle.content[:100],
                )

            except Exception as e:
                self.logger.warning(
                    "principle_storage_failed",
                    content=principle.content[:50],
                    error=str(e),
                )
                continue

        state["metadata"]["stored_count"] = stored_count
        state["current_step"] = "store_results"

        self.logger.info("store_complete", stored_count=stored_count)

        return state

    def reflect(
        self,
        max_episodes: int = 500,
        min_cluster_size: int = 5,
        min_confidence: float = 0.5,
    ) -> list[Principle]:
        """Convenience method to run reflection with common parameters.

        Args:
            max_episodes: Maximum episodes to analyze
            min_cluster_size: Minimum episodes per topic cluster
            min_confidence: Minimum confidence for principle validation

        Returns:
            List of validated and stored principles
        """
        result = self.run(
            {
                "metadata": {
                    "max_episodes": max_episodes,
                    "min_cluster_size": min_cluster_size,
                    "validation_threshold": min_confidence,
                }
            }
        )

        return result.get("metadata", {}).get("validated_principles", [])
