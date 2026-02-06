"""Skill Manager - Main interface for the self-bootstrapping skill system.

The SkillManager orchestrates skill loading, creation, editing, search,
and lifecycle management. It bridges the file system (SKILL.md files)
with Neo4j (embeddings, q_values) for a hybrid storage approach.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from hmem.skills.loader import SkillLoader
from hmem.skills.models import (
    SkillContent,
    SkillMetadata,
    SkillSummary,
    ProcessSummary,
)

if TYPE_CHECKING:
    from hmem.storage.neo4j_unified import Neo4jUnifiedStore

logger = structlog.get_logger()


class SkillManager:
    """Main interface for skill loading, creation, search, and lifecycle management.

    Bridges file system (SKILL.md content) with Neo4j (embeddings, q_values):
    - File system: skill content, metadata, version history
    - Neo4j: vector embeddings for search, q_value tracking, provenance links

    Safety boundaries:
    - Protected (meta) skills require force=True to edit/delete
    - Skills with q_value < 0.1 are auto-suspended
    - Creation rate limiting (max N skills per hour)
    - Minimum 2 processes required to induce a new skill

    Example:
        >>> manager = SkillManager(store=neo4j_store)
        >>> results = manager.search("entity extraction")
        >>> skill = manager.load("entity-extraction")
        >>> print(skill.to_prompt())
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore | None = None,
        skills_dir: Path | str | None = None,
        min_processes_for_creation: int = 2,
        max_creations_per_hour: int = 10,
        suspend_q_threshold: float = 0.1,
    ):
        """Initialize the SkillManager.

        Args:
            store: Neo4j unified store for vector search and q_value tracking
            skills_dir: Path to skills directory (defaults to package dir)
            min_processes_for_creation: Minimum similar processes to induce a skill
            max_creations_per_hour: Rate limit for skill creation
            suspend_q_threshold: Q-value below which skills are auto-suspended
        """
        if skills_dir is None:
            skills_dir = Path(__file__).parent
        self.loader = SkillLoader(skills_dir)
        self.store = store
        self.min_processes_for_creation = min_processes_for_creation
        self.max_creations_per_hour = max_creations_per_hour
        self.suspend_q_threshold = suspend_q_threshold
        self._creation_timestamps: list[datetime] = []
        self.logger = logger.bind(component="skill_manager")

        # Ensure directories exist
        self.loader.ensure_directories()

    def load(self, skill_name: str) -> SkillContent | None:
        """Load full skill content by name.

        Args:
            skill_name: Skill name (kebab-case)

        Returns:
            SkillContent with metadata and markdown body, or None
        """
        content = self.loader.load_skill(skill_name)
        if content and content.metadata.is_suspended:
            self.logger.debug("loading_suspended_skill", name=skill_name)
        return content

    def load_meta_skills(self) -> list[SkillContent]:
        """Load all meta (protected) skills.

        Used during agent initialization to inject meta-skills into system prompt.

        Returns:
            List of SkillContent objects for all meta skills
        """
        results: list[SkillContent] = []
        meta_skills = self.loader.list_meta_skills()

        for metadata in meta_skills:
            content = self.loader.load_skill(metadata.name)
            if content:
                results.append(content)

        return results

    def list_available(self, include_suspended: bool = False) -> list[SkillSummary]:
        """List all available skills as summaries.

        Args:
            include_suspended: Include suspended skills

        Returns:
            List of SkillSummary objects
        """
        all_metadata = self.loader.list_all_skills(include_suspended=include_suspended)
        return [SkillSummary.from_metadata(m) for m in all_metadata]

    def search(self, query: str, limit: int = 5) -> list[SkillSummary]:
        """Search for relevant skills using keyword matching on metadata.

        For vector similarity search, use search_by_embedding() with Neo4j.

        Args:
            query: Search query text
            limit: Maximum results

        Returns:
            List of SkillSummary objects sorted by relevance
        """
        query_lower = query.lower()
        all_skills = self.loader.list_all_skills()
        scored: list[tuple[float, SkillMetadata]] = []

        for skill in all_skills:
            score = self._keyword_match_score(query_lower, skill)
            if score > 0:
                scored.append((score, skill))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            SkillSummary.from_metadata(m, similarity_score=s) for s, m in scored[:limit]
        ]

    def search_by_embedding(
        self, query_embedding: list[float], limit: int = 5
    ) -> list[SkillSummary]:
        """Search for relevant skills using Neo4j vector similarity.

        Requires Neo4j store to be configured.

        Args:
            query_embedding: Query embedding vector
            limit: Maximum results

        Returns:
            List of SkillSummary objects with similarity scores
        """
        if not self.store:
            self.logger.warning("search_by_embedding_no_store")
            return []

        memories = self.store.vector_search(
            query_embedding=query_embedding,
            node_type="Skill",
            limit=limit,
        )

        results: list[SkillSummary] = []
        for mem in memories:
            skill_name = mem.metadata.get("name", "")
            if not skill_name:
                continue

            # Load file-based metadata for full information
            content = self.loader.load_skill(skill_name)
            if content and not content.metadata.is_suspended:
                results.append(
                    SkillSummary.from_metadata(
                        content.metadata,
                        similarity_score=mem.score,
                    )
                )

        return results

    def create(
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

        Validates creation constraints:
        - Rate limiting
        - Minimum source processes (if provided)
        - No duplicate names

        Args:
            name: Skill name (kebab-case)
            description: When to use this skill
            content: Markdown content body
            trigger_pattern: Pattern for triggering
            tags: Classification tags
            source_process_ids: Provenance process IDs
            source_fact_ids: Provenance fact IDs

        Returns:
            Skill name if created, None if validation failed
        """
        # Validate rate limit
        if not self._check_rate_limit():
            self.logger.warning("skill_creation_rate_limited", name=name)
            return None

        # Validate no duplicate
        if self.loader.skill_exists(name):
            self.logger.warning("skill_already_exists", name=name)
            return None

        # Validate minimum processes
        if (
            source_process_ids is not None
            and len(source_process_ids) < self.min_processes_for_creation
        ):
            self.logger.warning(
                "insufficient_source_processes",
                name=name,
                count=len(source_process_ids),
                required=self.min_processes_for_creation,
            )
            return None

        now = datetime.now(timezone.utc)

        metadata: dict[str, Any] = {
            "name": name,
            "description": description,
            "trigger_pattern": trigger_pattern,
            "tags": tags or [],
            "skill_type": "generated",
            "source_process_ids": source_process_ids or [],
            "source_fact_ids": source_fact_ids or [],
            "version": 1,
            "is_protected": False,
            "is_suspended": False,
            "q_value": 0.5,
            "q_update_count": 0,
            "created_at": now,
            "updated_at": now,
        }

        # Write to file system
        self.loader.write_skill(
            skill_name=name,
            metadata=metadata,
            content=content,
            skill_type="generated",
        )

        # Track creation for rate limiting
        self._creation_timestamps.append(now)

        # Sync to Neo4j if available
        if self.store:
            from hmem.models import Skill as SkillModel

            skill_model = SkillModel(
                name=name,
                description=description,
                trigger_pattern=trigger_pattern,
                action_template="",
                tags=tags or [],
                source_process_ids=source_process_ids or [],
            )
            self.store.add_skill(
                skill_model,
                source_process_ids=source_process_ids,
            )

        self.logger.info(
            "skill_created",
            name=name,
            source_processes=len(source_process_ids or []),
        )

        return name

    def edit(
        self,
        skill_name: str,
        new_content: str | None = None,
        metadata_updates: dict[str, Any] | None = None,
        version_bump: bool = False,
        reason: str = "",
        force: bool = False,
    ) -> bool:
        """Edit an existing skill.

        Args:
            skill_name: Skill to edit
            new_content: New markdown content (None to keep current)
            metadata_updates: Fields to update in metadata
            version_bump: Whether to increment version
            reason: Reason for the edit
            force: Required for protected skills

        Returns:
            True if edit successful
        """
        skill = self.loader.load_skill(skill_name)
        if not skill:
            self.logger.warning("skill_not_found_for_edit", name=skill_name)
            return False

        # Check protection
        if skill.metadata.is_protected and not force:
            self.logger.warning(
                "cannot_edit_protected_skill",
                name=skill_name,
                hint="Use force=True to edit protected skills",
            )
            return False

        # Prepare updates
        updates = metadata_updates or {}
        updates["updated_at"] = datetime.now(timezone.utc)

        if version_bump:
            updates["version"] = skill.metadata.version + 1

        if reason:
            updates["edit_reason"] = reason

        # Update content if provided
        content = new_content if new_content is not None else skill.content
        current_data = skill.metadata.model_dump()
        current_data.update(updates)

        # Rewrite file
        self.loader.write_skill(
            skill_name=skill_name,
            metadata=current_data,
            content=content,
            skill_type=skill.metadata.skill_type,
        )

        self.logger.info(
            "skill_edited",
            name=skill_name,
            version_bumped=version_bump,
            reason=reason,
        )

        return True

    def apply_feedback(
        self,
        skill_name: str,
        outcome: str,
        alpha: float = 0.1,
    ) -> None:
        """Apply feedback to a skill's Q-value.

        Updates Q-value in both file system metadata and Neo4j.
        Auto-suspends skills with Q-value below threshold.

        Args:
            skill_name: Skill to update
            outcome: "success", "failure", or "partial"
            alpha: Learning rate
        """
        skill = self.loader.load_skill(skill_name)
        if not skill:
            return

        # Map outcome to reward
        reward_map = {
            "success": 1.0,
            "failure": 0.0,
            "partial": 0.5,
        }
        reward = reward_map.get(outcome, 0.5)

        # Q-learning update
        q_old = skill.metadata.q_value
        q_new = q_old + alpha * (reward - q_old)
        q_update_count = skill.metadata.q_update_count + 1

        updates: dict[str, Any] = {
            "q_value": q_new,
            "q_update_count": q_update_count,
        }

        # Auto-suspend if Q-value drops below threshold
        if q_new < self.suspend_q_threshold and q_update_count >= 5:
            updates["is_suspended"] = True
            self.logger.info(
                "skill_auto_suspended",
                name=skill_name,
                q_value=q_new,
                updates=q_update_count,
            )

        self.loader.update_skill_metadata(skill_name, updates)

        # Sync Q-value to Neo4j
        if self.store:
            self.store.update_q_value(
                node_id=f"skill_{skill_name}",
                node_type="Skill",
                delta_q=reward,
                alpha=alpha,
            )

        self.logger.debug(
            "skill_feedback_applied",
            name=skill_name,
            outcome=outcome,
            q_old=q_old,
            q_new=q_new,
        )

    def search_processes(
        self, trigger_pattern: str, limit: int = 10
    ) -> list[ProcessSummary]:
        """Search for similar processes in Neo4j.

        Used to find candidate processes for skill creation.

        Args:
            trigger_pattern: Trigger text to search by
            limit: Maximum results

        Returns:
            List of ProcessSummary objects
        """
        if not self.store:
            self.logger.warning("search_processes_no_store")
            return []

        # Use fulltext search for processes
        memories = self.store.fulltext_search(
            query=trigger_pattern,
            node_types=["Process"],
            limit=limit,
        )

        results: list[ProcessSummary] = []
        for mem in memories:
            metadata = mem.metadata
            results.append(
                ProcessSummary(
                    id=metadata.get("id", ""),
                    trigger=metadata.get("trigger", ""),
                    action=metadata.get("action", ""),
                    outcome=metadata.get("outcome"),
                    similarity_score=mem.score,
                    q_value=metadata.get("q_value", 0.5),
                    q_update_count=metadata.get("q_update_count", 0),
                )
            )

        return results

    def _keyword_match_score(self, query: str, skill: SkillMetadata) -> float:
        """Calculate keyword match score between query and skill metadata.

        Simple TF-based scoring: counts keyword matches across name,
        description, trigger_pattern, and tags.

        Args:
            query: Lowercased search query
            skill: Skill metadata to score

        Returns:
            Match score (0.0 = no match, higher = better match)
        """
        score = 0.0
        query_terms = query.split()

        (
            f"{skill.name} {skill.description} "
            f"{skill.trigger_pattern} {' '.join(skill.tags)}"
        ).lower()

        for term in query_terms:
            if term in skill.name.lower():
                score += 3.0  # Name match weighted highest
            if term in skill.description.lower():
                score += 2.0
            if term in skill.trigger_pattern.lower():
                score += 1.5
            if any(term in tag.lower() for tag in skill.tags):
                score += 1.0

        # Boost by Q-value for quality ranking
        score *= 0.5 + (skill.q_value * 0.5)

        return score

    def _check_rate_limit(self) -> bool:
        """Check if skill creation is within rate limits.

        Returns:
            True if creation is allowed
        """
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        # Clean old timestamps
        self._creation_timestamps = [
            ts for ts in self._creation_timestamps if ts > one_hour_ago
        ]

        return len(self._creation_timestamps) < self.max_creations_per_hour
