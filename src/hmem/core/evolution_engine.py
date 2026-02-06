"""Unified self-evolution engine for the memory system.

This module consolidates all evolution logic:
- Q-value feedback and reinforcement learning
- Evolution trigger checking
- Refinement and deprecation decisions
- Feedback propagation along provenance chains
- Skill induction from similar processes
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
from hmem.models import Skill

if TYPE_CHECKING:
    from hmem.agents.llm import LLMClient
    from hmem.skills.manager import SkillManager
    from hmem.storage.neo4j_unified import Neo4jUnifiedStore

logger = structlog.get_logger(__name__)


class EvolutionEngine:
    """Unified self-evolution engine for the memory system.

    Integrates all evolution logic:
    - Q-value feedback (from strategies/q_learning.py)
    - Trigger checking (from strategies/evolution.py)
    - Refinement/deprecation (from strategies/refine.py)
    - Feedback propagation along provenance chain
    - Skill induction from similar processes
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore,
        llm: LLMClient | None = None,
        skill_manager: SkillManager | None = None,
        alpha: float = Q_LEARNING_DEFAULT_ALPHA,
        batch_trigger_size: int = 50,
        time_trigger_hours: int = 24,
    ):
        """Initialize the evolution engine.

        Args:
            store: Neo4j unified store for graph operations
            llm: LLM client for induction tasks (optional)
            skill_manager: Skill manager for file system output (optional)
            alpha: Learning rate for Q-value updates
            batch_trigger_size: Number of remember operations before triggering evolution
            time_trigger_hours: Hours between time-based evolution triggers
        """
        self.store = store
        self.llm = llm
        self.skill_manager = skill_manager
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

    def induce_skills_from_processes(
        self,
        min_cluster_size: int = 3,
        similarity_threshold: float = 0.75,
    ) -> list[Skill]:
        """Induce skills from clusters of similar processes.

        This is the new skill induction pathway:
        1. Find processes not yet linked to any skill
        2. Cluster them by trigger similarity
        3. For each cluster, use LLM to abstract a general skill
        4. Link processes to the induced skill via INSTANCE_OF

        Args:
            min_cluster_size: Minimum processes needed to induce a skill
            similarity_threshold: Minimum embedding similarity for clustering

        Returns:
            List of induced skills
        """
        if not self.llm:
            self.logger.warning("LLM not available for skill induction from processes")
            return []

        self.logger.info("Starting skill induction from processes")

        try:
            # Get processes without skills
            candidates = self.store.get_processes_without_skill(limit=100)

            if len(candidates) < min_cluster_size:
                self.logger.debug(
                    "Not enough process candidates",
                    count=len(candidates),
                    required=min_cluster_size,
                )
                return []

            # Simple clustering by trigger similarity
            # For now, use greedy clustering. A more sophisticated approach
            # would use proper clustering algorithms (DBSCAN, hierarchical).
            clusters: list[list[dict]] = []
            used: set[str] = set()

            for proc in candidates:
                if proc["id"] in used:
                    continue

                proc_embedding = proc.get("embedding")
                if not proc_embedding:
                    continue

                # Find similar processes
                similar = self.store.find_similar_processes(
                    trigger_embedding=proc_embedding,
                    limit=20,
                    min_score=similarity_threshold,
                )

                # Filter to only unused candidates
                cluster = [
                    p
                    for p in similar
                    if p["id"] not in used and p["id"] in {c["id"] for c in candidates}
                ]

                if len(cluster) >= min_cluster_size:
                    clusters.append(cluster)
                    for p in cluster:
                        used.add(p["id"])

            self.logger.info(
                "Found process clusters for skill induction", count=len(clusters)
            )

            # Induce skill from each cluster
            induced_skills: list[Skill] = []

            for cluster in clusters:
                skill = self._induce_skill_from_cluster(cluster)
                if skill:
                    induced_skills.append(skill)

            self.logger.info("Skills induced from processes", count=len(induced_skills))

            return induced_skills

        except Exception as e:
            self.logger.error("Failed to induce skills from processes", error=str(e))
            return []

    def _induce_skill_from_cluster(self, cluster: list[dict]) -> Skill | None:
        """Induce a single skill from a cluster of similar processes.

        Outputs to both Neo4j and the file system (if SkillManager is available).

        Args:
            cluster: List of similar process dicts

        Returns:
            Induced Skill or None
        """
        if not self.llm or not cluster:
            return None

        try:
            # Format processes for LLM
            processes_text = "\n".join(
                [
                    f"Process {i + 1}:\n  Trigger: {p.get('trigger', '')}\n  Action: {p.get('action', '')}\n  Outcome: {p.get('outcome', 'N/A')}"
                    for i, p in enumerate(cluster[:10])
                ]
            )

            # Use LLM to abstract the common pattern
            from langchain_core.messages import HumanMessage, SystemMessage

            system_prompt = """Analyze these similar processes and extract a GENERAL SKILL.

A skill is an abstracted, reusable procedure that captures the common pattern across multiple concrete examples.

Return JSON:
{
    "name": "short_skill_name (2-4 words)",
    "description": "Clear description of when and how to apply this skill",
    "trigger_pattern": "Generalized trigger condition",
    "action_template": "Step-by-step general procedure",
    "confidence": 0.0-1.0
}

IMPORTANT:
- Abstract away specifics, keep the general pattern
- The skill should be applicable to similar new situations
- If the processes are too diverse to generalize, return {"skip": true}"""

            messages = [
                SystemMessage(content=[{"type": "text", "text": system_prompt}]),
                HumanMessage(content=[{"type": "text", "text": processes_text}]),
            ]

            response = self.llm.llm.invoke(messages)
            response_text = self.llm._extract_text(response.content)

            # Parse JSON
            import json

            if response_text.startswith("```"):
                lines = response_text.split("\n")
                json_lines = []
                in_block = False
                for line in lines:
                    if line.startswith("```"):
                        in_block = not in_block
                        continue
                    if in_block:
                        json_lines.append(line)
                response_text = "\n".join(json_lines)

            result = json.loads(response_text)

            if result.get("skip"):
                self.logger.debug("Cluster too diverse for skill induction")
                return None

            source_process_ids = [p["id"] for p in cluster]

            # Create Skill model
            skill = Skill(
                name=result.get("name", "auto_skill"),
                description=result.get("description", ""),
                trigger_pattern=result.get("trigger_pattern", ""),
                action_template=result.get("action_template", ""),
                source_process_ids=source_process_ids,
            )

            # Store skill in Neo4j and link to processes
            skill_id = self.store.add_skill(
                skill, source_process_ids=source_process_ids
            )
            skill.id = skill_id

            # Also write to file system via SkillManager
            if self.skill_manager:
                skill_name = (
                    result.get("name", "auto-skill")
                    .lower()
                    .replace(" ", "-")
                    .replace("_", "-")
                )

                content = self._format_as_skill_md(result, cluster)
                self.skill_manager.create(
                    name=skill_name,
                    description=result.get("description", ""),
                    content=content,
                    trigger_pattern=result.get("trigger_pattern", ""),
                    tags=["auto-induced"],
                    source_process_ids=source_process_ids,
                )

            self.logger.info(
                "Skill induced from processes",
                skill_id=skill_id,
                name=skill.name,
                process_count=len(cluster),
            )

            return skill

        except Exception as e:
            self.logger.error(
                "Failed to induce skill from cluster",
                error=str(e),
                cluster_size=len(cluster),
            )
            return None

    def _format_as_skill_md(self, llm_result: dict, cluster: list[dict]) -> str:
        """Format LLM induction result as SKILL.md markdown content.

        Args:
            llm_result: Parsed JSON from LLM
            cluster: Source process cluster

        Returns:
            Markdown content for SKILL.md body
        """
        name = llm_result.get("name", "Auto Skill")
        description = llm_result.get("description", "")
        trigger_pattern = llm_result.get("trigger_pattern", "")
        action_template = llm_result.get("action_template", "")

        lines = [
            f"# {name}",
            "",
            f"## When to Use",
            f"{description}",
            "",
            f"## Trigger",
            f"{trigger_pattern}",
            "",
            f"## Steps",
            f"{action_template}",
            "",
            f"## Source Evidence",
            f"Induced from {len(cluster)} similar processes:",
            "",
        ]

        for i, proc in enumerate(cluster[:5], 1):
            trigger = proc.get("trigger", "N/A")
            lines.append(f"{i}. Trigger: {trigger}")

        if len(cluster) > 5:
            lines.append(f"... and {len(cluster) - 5} more")

        return "\n".join(lines)

    def run_skill_induction_task(self) -> dict[str, int]:
        """Run skill induction as an async/scheduled task.

        This can be called periodically (e.g., after batch imports or on schedule).

        Returns:
            Stats dict with induction results
        """
        stats = {
            "processes_scanned": 0,
            "clusters_found": 0,
            "skills_induced": 0,
        }

        try:
            candidates = self.store.get_processes_without_skill(limit=100)
            stats["processes_scanned"] = len(candidates)

            skills = self.induce_skills_from_processes()
            stats["skills_induced"] = len(skills)

            self.logger.info("Skill induction task completed", stats=stats)

        except Exception as e:
            self.logger.error("Skill induction task failed", error=str(e))

        return stats
