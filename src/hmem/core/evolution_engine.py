"""Unified self-evolution engine for the memory system.

This module consolidates all evolution logic:
- Q-value feedback and reinforcement learning
- Evolution trigger checking
- Refinement and deprecation decisions
- Feedback propagation along provenance chains
- Principle and skill induction
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

import structlog

from hmem.constants import (
    Q_LEARNING_DEFAULT_ALPHA,
    REWARD_FAILURE,
    REWARD_SUCCESS,
    REWARD_UNKNOWN_IGNORED,
    REWARD_UNKNOWN_USED,
)
from hmem.models import Principle, Skill

if TYPE_CHECKING:
    from hmem.agents.llm import LLMClient
    from hmem.storage.neo4j_unified import Neo4jUnifiedStore

logger = structlog.get_logger(__name__)


class EvolutionEngine:
    """Unified self-evolution engine for the memory system.

    Integrates all evolution logic:
    - Q-value feedback (from strategies/q_learning.py)
    - Trigger checking (from strategies/evolution.py)
    - Refinement/deprecation (from strategies/refine.py)
    - Feedback propagation along provenance chain
    - Principle and skill induction
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore,
        llm: LLMClient | None = None,
        alpha: float = Q_LEARNING_DEFAULT_ALPHA,
        batch_trigger_size: int = 50,
        time_trigger_hours: int = 24,
    ):
        """Initialize the evolution engine.

        Args:
            store: Neo4j unified store for graph operations
            llm: LLM client for induction tasks (optional)
            alpha: Learning rate for Q-value updates
            batch_trigger_size: Number of remember operations before triggering evolution
            time_trigger_hours: Hours between time-based evolution triggers
        """
        self.store = store
        self.llm = llm
        self.alpha = alpha
        self.batch_trigger_size = batch_trigger_size
        self.time_trigger_hours = time_trigger_hours

        # Evolution thresholds
        self.refine_q_threshold = 0.3
        self.refine_min_usage = 5
        self.deprecate_q_threshold = 0.2
        self.deprecate_min_usage = 10

        self.logger = logger.bind(component="evolution_engine")

    def reward_from_outcome(self, outcome: str) -> float:
        """Map outcome to reward signal.

        Args:
            outcome: One of "success", "failure", "unknown_used", "unknown_ignored"

        Returns:
            Reward value corresponding to the outcome
        """
        reward_map = {
            "success": REWARD_SUCCESS,
            "failure": REWARD_FAILURE,
            "unknown_used": REWARD_UNKNOWN_USED,
            "unknown_ignored": REWARD_UNKNOWN_IGNORED,
        }
        return reward_map.get(outcome, 0.0)

    def apply_feedback(self, memory_id: str, node_type: str, outcome: str) -> None:
        """Apply feedback to a single memory.

        Updates the Q-value using the Q-learning rule:
        Q_new = Q_old + alpha * (reward - Q_old)

        Args:
            memory_id: ID of the memory node
            node_type: Type of the node (Event, Fact, Principle, Skill)
            outcome: Outcome string ("success", "failure", etc.)
        """
        reward = self.reward_from_outcome(outcome)

        # Get current Q-value from store
        try:
            properties = self.store.get_node_properties(memory_id, node_type)
            if not properties:
                self.logger.warning(
                    "Node not found for feedback",
                    memory_id=memory_id,
                    node_type=node_type,
                )
                return

            q_old = properties.get("q_value", 0.5)
            q_update_count = properties.get("q_update_count", 0)

            # Apply Q-learning update rule
            q_new = q_old + self.alpha * (reward - q_old)

            # Update in store
            self.store.update_node_properties(
                memory_id,
                node_type,
                {
                    "q_value": q_new,
                    "q_update_count": q_update_count + 1,
                    "last_q_update": datetime.utcnow().isoformat(),
                },
            )

            self.logger.info(
                "Applied feedback",
                memory_id=memory_id,
                node_type=node_type,
                outcome=outcome,
                reward=reward,
                q_old=q_old,
                q_new=q_new,
                update_count=q_update_count + 1,
            )

        except Exception as e:
            self.logger.error(
                "Failed to apply feedback",
                memory_id=memory_id,
                node_type=node_type,
                error=str(e),
            )

    def propagate_feedback(
        self,
        memory_id: str,
        success: bool,
        max_depth: int = 3,
        decay_factor: float = 0.8,
    ) -> None:
        """Propagate feedback along provenance chain.

        Walks up the provenance graph (DERIVED_FROM edges) and applies
        decayed rewards to ancestor nodes.

        Args:
            memory_id: Starting memory ID
            success: Whether the feedback is positive
            max_depth: Maximum depth to propagate
            decay_factor: Factor to decay reward at each level
        """
        outcome = "success" if success else "failure"
        base_reward = self.reward_from_outcome(outcome)

        try:
            # Get lineage from store
            lineage = self.store.get_lineage(memory_id, max_depth=max_depth)

            for depth, ancestor in enumerate(lineage):
                if depth == 0:
                    continue  # Skip the original node (already updated)

                # Apply decayed reward
                decayed_reward = base_reward * (decay_factor**depth)

                # Convert decayed reward back to outcome for apply_feedback
                if decayed_reward > 0:
                    decayed_outcome = "success"
                elif decayed_reward < 0:
                    decayed_outcome = "failure"
                else:
                    decayed_outcome = "unknown_ignored"

                self.apply_feedback(ancestor["id"], ancestor["type"], decayed_outcome)

            self.logger.info(
                "Propagated feedback",
                memory_id=memory_id,
                success=success,
                ancestors_updated=len(lineage) - 1,
            )

        except Exception as e:
            self.logger.error(
                "Failed to propagate feedback",
                memory_id=memory_id,
                error=str(e),
            )

    def should_trigger(
        self, remember_count: int, last_evolution_at: datetime | None
    ) -> bool:
        """Check if evolution should be triggered.

        Evolution triggers when:
        1. Batch size threshold is reached, OR
        2. Time threshold has elapsed since last evolution

        Args:
            remember_count: Number of remember operations since last evolution
            last_evolution_at: Timestamp of last evolution run

        Returns:
            True if evolution should be triggered
        """
        # Batch size trigger
        if remember_count >= self.batch_trigger_size:
            self.logger.info(
                "Batch trigger activated",
                remember_count=remember_count,
                threshold=self.batch_trigger_size,
            )
            return True

        # Time-based trigger
        if last_evolution_at is not None:
            time_since_last = datetime.utcnow() - last_evolution_at
            threshold = timedelta(hours=self.time_trigger_hours)
            if time_since_last >= threshold:
                self.logger.info(
                    "Time trigger activated",
                    hours_since_last=time_since_last.total_seconds() / 3600,
                    threshold_hours=self.time_trigger_hours,
                )
                return True

        return False

    def execute_evolution(self) -> dict[str, int]:
        """Execute the evolution process.

        Main evolution loop:
        1. Collect candidates (low Q-value + high usage)
        2. Determine action for each (refine, deprecate, keep)
        3. Apply actions
        4. Return statistics

        Returns:
            Dictionary with evolution statistics
        """
        self.logger.info("Starting evolution cycle")

        stats = {
            "candidates_found": 0,
            "refined": 0,
            "deprecated": 0,
            "kept": 0,
            "errors": 0,
        }

        try:
            # Collect candidates
            candidates = self._collect_candidates()
            stats["candidates_found"] = len(candidates)

            self.logger.info("Collected evolution candidates", count=len(candidates))

            # Process each candidate
            for candidate in candidates:
                memory_id = candidate["id"]
                node_type = candidate["type"]
                q_value = candidate["q_value"]
                q_update_count = candidate["q_update_count"]

                # Determine action
                action = self._determine_action(q_value, q_update_count)

                try:
                    if action == "refine":
                        result = self.refine(memory_id, node_type)
                        if result:
                            stats["refined"] += 1
                    elif action == "deprecate":
                        self.deprecate(
                            memory_id,
                            node_type,
                            reason="Low Q-value with sufficient usage",
                        )
                        stats["deprecated"] += 1
                    else:  # keep
                        stats["kept"] += 1

                except Exception as e:
                    self.logger.error(
                        "Failed to apply evolution action",
                        memory_id=memory_id,
                        node_type=node_type,
                        action=action,
                        error=str(e),
                    )
                    stats["errors"] += 1

            self.logger.info("Evolution cycle completed", stats=stats)

        except Exception as e:
            self.logger.error("Evolution cycle failed", error=str(e))
            stats["errors"] += 1

        return stats

    def _collect_candidates(self) -> list[dict]:
        """Collect evolution candidates from the graph.

        Queries Neo4j for nodes with:
        - Low Q-value (below refine threshold)
        - High usage (above minimum usage)

        Returns:
            List of candidate node dictionaries
        """
        candidates = []

        try:
            # Query across all node types
            node_types = ["Event", "Fact", "Principle", "Skill"]

            for node_type in node_types:
                nodes = self.store.query_nodes_by_q_value(
                    node_type=node_type,
                    max_q_value=self.refine_q_threshold,
                    min_usage=self.refine_min_usage,
                )

                for node in nodes:
                    candidates.append(
                        {
                            "id": node["id"],
                            "type": node_type,
                            "q_value": node.get("q_value", 0.5),
                            "q_update_count": node.get("q_update_count", 0),
                        }
                    )

        except Exception as e:
            self.logger.error("Failed to collect candidates", error=str(e))

        return candidates

    def _determine_action(
        self, q_value: float, q_update_count: int
    ) -> Literal["refine", "deprecate", "keep"]:
        """Determine evolution action based on Q-value and usage.

        Args:
            q_value: Current Q-value
            q_update_count: Number of Q-value updates

        Returns:
            Action to take: "refine", "deprecate", or "keep"
        """
        # Deprecate if Q-value is very low with high usage
        if (
            q_value < self.deprecate_q_threshold
            and q_update_count >= self.deprecate_min_usage
        ):
            return "deprecate"

        # Refine if Q-value is low with moderate usage
        if (
            q_value < self.refine_q_threshold
            and q_update_count >= self.refine_min_usage
        ):
            return "refine"

        # Otherwise keep
        return "keep"

    def refine(self, memory_id: str, node_type: str) -> str | None:
        """Refine a memory by creating an improved version.

        Creates a new version of the memory via the supersede relationship.
        The new version starts with a fresh Q-value.

        Args:
            memory_id: ID of the memory to refine
            node_type: Type of the node

        Returns:
            ID of the new refined memory, or None if refinement failed
        """
        self.logger.info("Refining memory", memory_id=memory_id, node_type=node_type)

        try:
            # Get original node properties
            properties = self.store.get_node_properties(memory_id, node_type)
            if not properties:
                self.logger.warning(
                    "Node not found for refinement",
                    memory_id=memory_id,
                    node_type=node_type,
                )
                return None

            # TODO: Use LLM to generate refined version
            # For now, create a copy with reset Q-value
            new_id = f"{memory_id}_refined_{datetime.utcnow().timestamp()}"

            refined_properties = properties.copy()
            refined_properties.update(
                {
                    "id": new_id,
                    "q_value": 0.5,  # Reset Q-value
                    "q_update_count": 0,
                    "created_at": datetime.utcnow().isoformat(),
                    "refined_from": memory_id,
                }
            )

            # Create new node
            self.store.create_node(node_type, refined_properties)

            # Create supersede relationship
            self.store.create_relationship(
                new_id,
                node_type,
                memory_id,
                node_type,
                "SUPERSEDES",
                {"created_at": datetime.utcnow().isoformat()},
            )

            self.logger.info(
                "Memory refined",
                original_id=memory_id,
                new_id=new_id,
                node_type=node_type,
            )

            return new_id

        except Exception as e:
            self.logger.error(
                "Failed to refine memory",
                memory_id=memory_id,
                node_type=node_type,
                error=str(e),
            )
            return None

    def deprecate(self, memory_id: str, node_type: str, reason: str) -> None:
        """Mark a memory as deprecated.

        Args:
            memory_id: ID of the memory to deprecate
            node_type: Type of the node
            reason: Reason for deprecation
        """
        self.logger.info(
            "Deprecating memory",
            memory_id=memory_id,
            node_type=node_type,
            reason=reason,
        )

        try:
            self.store.update_node_properties(
                memory_id,
                node_type,
                {
                    "deprecated": True,
                    "deprecated_at": datetime.utcnow().isoformat(),
                    "deprecation_reason": reason,
                },
            )

            self.logger.info(
                "Memory deprecated", memory_id=memory_id, node_type=node_type
            )

        except Exception as e:
            self.logger.error(
                "Failed to deprecate memory",
                memory_id=memory_id,
                node_type=node_type,
                error=str(e),
            )

    def merge(self, memory_ids: list[str], node_type: str) -> str | None:
        """Merge multiple similar memories into one.

        Args:
            memory_ids: IDs of memories to merge
            node_type: Type of the nodes

        Returns:
            ID of the merged memory, or None if merge failed
        """
        self.logger.info(
            "Merge requested",
            memory_ids=memory_ids,
            node_type=node_type,
        )

        # TODO: Implement sophisticated LLM-based merging
        # For now, log and return None
        self.logger.warning("Merge not yet implemented - requires LLM integration")
        return None

    def split(self, memory_id: str, node_type: str) -> list[str]:
        """Split a coarse memory into multiple fine-grained memories.

        Args:
            memory_id: ID of the memory to split
            node_type: Type of the node

        Returns:
            List of IDs of the new split memories
        """
        self.logger.info("Split requested", memory_id=memory_id, node_type=node_type)

        # TODO: Implement sophisticated LLM-based splitting
        # For now, log and return empty list
        self.logger.warning("Split not yet implemented - requires LLM integration")
        return []

    def induce_principles(self, event_ids: list[str]) -> list[Principle]:
        """Extract principles from a cluster of events.

        Uses LLM to analyze events and generate general principles.

        Args:
            event_ids: List of event IDs to analyze

        Returns:
            List of induced principles
        """
        if not self.llm:
            self.logger.warning("LLM not available for principle induction")
            return []

        self.logger.info("Inducing principles", event_count=len(event_ids))

        try:
            # Get event contents from store
            events = []
            for event_id in event_ids:
                properties = self.store.get_node_properties(event_id, "Event")
                if properties:
                    events.append(properties)

            if not events:
                self.logger.warning("No events found for induction")
                return []

            # Convert event properties to Event objects for LLM.reflect()
            from hmem.models import Event as EventModel

            event_objects: list[EventModel] = []
            for props in events:
                event_objects.append(
                    EventModel(
                        id=props.get("id"),
                        content=props.get("content", props.get("description", "")),
                        outcome=props.get("outcome", "unknown"),
                        tags=props.get("tags", []),
                    )
                )

            # Use LLM to extract principles
            if event_objects:
                principle = self.llm.reflect(event_objects)
                principles: list[Principle] = [principle]
            else:
                principles = []

            self.logger.info("Principles induced", count=len(principles))
            return principles

        except Exception as e:
            self.logger.error("Failed to induce principles", error=str(e))
            return []

    def induce_skills(self, event_ids: list[str]) -> list[Skill]:
        """Generate skills from a cluster of events.

        Uses LLM to analyze events and generate procedural knowledge.

        Args:
            event_ids: List of event IDs to analyze

        Returns:
            List of induced skills
        """
        if not self.llm:
            self.logger.warning("LLM not available for skill induction")
            return []

        self.logger.info("Inducing skills", event_count=len(event_ids))

        try:
            # Get event contents from store
            events = []
            for event_id in event_ids:
                properties = self.store.get_node_properties(event_id, "Event")
                if properties:
                    events.append(properties)

            if not events:
                self.logger.warning("No events found for induction")
                return []

            # Convert event properties to Event objects
            from hmem.models import Event as EventModel

            event_objects: list[EventModel] = []
            for props in events:
                event_objects.append(
                    EventModel(
                        id=props.get("id"),
                        content=props.get("content", props.get("description", "")),
                        outcome=props.get("outcome", "unknown"),
                        tags=props.get("tags", []),
                    )
                )

            # Use LLM to extract skills via principle -> skill pipeline
            skills: list[Skill] = []
            if event_objects:
                principle = self.llm.reflect(event_objects)
                skill_template = self.llm.generate_skill(principle, "general")
                if skill_template:
                    skill = Skill(
                        name=skill_template["name"],
                        trigger_pattern=skill_template.get("trigger_pattern", ""),
                        code_template={"steps": skill_template.get("steps", [])},
                        description=skill_template.get("description", ""),
                    )
                    skills.append(skill)

            self.logger.info("Skills induced", count=len(skills))
            return skills

        except Exception as e:
            self.logger.error("Failed to induce skills", error=str(e))
            return []
