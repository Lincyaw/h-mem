"""Skill Store - Procedural memory templates (Phase 3 Implementation).

Implements the Skill Store from design.md with:
- SQLite-based persistent storage
- Trigger pattern matching for skill activation
- Success rate tracking for adaptive skill selection
- Provenance tracking (parent_ids) for skill derivation
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import uuid
import structlog

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Float,
    Boolean,
    Index,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker  # type: ignore
from sqlalchemy.exc import IntegrityError  # type: ignore

from hmem.models import Memory, Skill, IndexProfile

logger = structlog.get_logger()

Base = declarative_base()  # type: ignore


class SkillRow(Base):  # type: ignore
    """SQLite table for skill templates with usage statistics."""

    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    trigger_pattern = Column(Text, nullable=False)
    code_template = Column(Text, nullable=False)  # JSON
    description = Column(Text, nullable=True)
    q_value = Column(Float, default=0.5)
    q_update_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)  # Legacy, kept for migration
    failure_count = Column(Integer, default=0)  # Legacy, kept for migration
    weight = Column(Float, default=1.0)  # Legacy, kept for migration
    version = Column(String, default="v1")
    deprecated = Column(Boolean, default=False)
    successor_id = Column(String, nullable=True)
    parent_ids = Column(Text, default=None)  # JSON array of source memory IDs
    derivation_type = Column(String, default="extraction")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_skill_name", "name"),
        Index("idx_trigger_pattern", "trigger_pattern"),
    )


class SkillStore:
    """SQLite-based skill template storage (Phase 3 Implementation).

    Stores reusable procedural patterns (e.g., "search-summarize workflow").

    Features:
    - Trigger pattern matching for skill activation
    - Success/failure tracking for adaptive selection
    - Provenance tracking (parent_ids, derivation_type)
    - Search by trigger pattern or name

    Example:
        >>> store = SkillStore(db_path=Path("./.hmem/skills.db"))
        >>> store.add_skill(
        ...     name="web_scraping",
        ...     trigger_pattern="parse HTML|scrape website|extract data",
        ...     code_template={"steps": ["fetch_url", "parse_html", "extract_data"]}
        ... )
        >>> skill = store.get_skill("web_scraping")
        >>> matching = store.search_by_trigger("how to scrape a website")
    """

    def __init__(self, db_path: Path | str) -> None:
        """Initialize skill store.

        Args:
            db_path: SQLite database path (can be Path or str)
        """
        if isinstance(db_path, str):
            if db_path.startswith("sqlite://"):
                database_url = db_path
            else:
                db_path = Path(db_path)
                db_path.parent.mkdir(parents=True, exist_ok=True)
                database_url = f"sqlite:///{db_path}"
        else:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            database_url = f"sqlite:///{db_path}"

        self.engine = create_engine(database_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._ensure_schema_migration()

    def _ensure_schema_migration(self) -> None:
        """Ensure database schema is up to date with current model.

        Adds missing columns to existing tables for backward compatibility.
        """
        with self.SessionLocal() as session:
            # Define columns to check and add if missing
            columns_to_add = [
                ("weight", "ALTER TABLE skills ADD COLUMN weight REAL DEFAULT 1.0"),
                ("version", "ALTER TABLE skills ADD COLUMN version TEXT DEFAULT 'v1'"),
                (
                    "deprecated",
                    "ALTER TABLE skills ADD COLUMN deprecated INTEGER DEFAULT 0",
                ),
                (
                    "successor_id",
                    "ALTER TABLE skills ADD COLUMN successor_id TEXT DEFAULT NULL",
                ),
                (
                    "parent_ids",
                    "ALTER TABLE skills ADD COLUMN parent_ids TEXT DEFAULT NULL",
                ),
                (
                    "derivation_type",
                    "ALTER TABLE skills ADD COLUMN derivation_type TEXT DEFAULT 'extraction'",
                ),
                (
                    "q_value",
                    "ALTER TABLE skills ADD COLUMN q_value REAL DEFAULT 0.5",
                ),
                (
                    "q_update_count",
                    "ALTER TABLE skills ADD COLUMN q_update_count INTEGER DEFAULT 0",
                ),
            ]

            for column_name, alter_sql in columns_to_add:
                try:
                    # Check if column exists
                    session.execute(text(f"SELECT {column_name} FROM skills LIMIT 1"))
                except Exception:
                    # Column missing, add it
                    try:
                        session.execute(text(alter_sql))
                        session.commit()
                        logger.info(
                            "skill_store_schema_migration", added_column=column_name
                        )
                    except Exception as e:
                        logger.warning(
                            "skill_store_schema_migration_failed",
                            column=column_name,
                            error=str(e),
                        )
                        session.rollback()

    def _row_to_skill(self, row: SkillRow) -> Skill:
        """Convert SkillRow to Skill Pydantic model.

        Args:
            row: SQLAlchemy row object

        Returns:
            Skill Pydantic model instance
        """
        # Access row attributes (SQLAlchemy returns Python types at runtime)
        skill_id: str = row.skill_id  # type: ignore[assignment]
        name: str = row.name  # type: ignore[assignment]
        trigger_pattern: str = row.trigger_pattern  # type: ignore[assignment]
        code_template_str: str = row.code_template  # type: ignore[assignment]
        description: str | None = row.description  # type: ignore[assignment]
        q_value: float = getattr(row, "q_value", None) or 0.5  # type: ignore[assignment]
        q_update_count: int = getattr(row, "q_update_count", None) or 0  # type: ignore[assignment]
        version_str: str = row.version or "v1"  # type: ignore[assignment]
        deprecated: bool = row.deprecated or False  # type: ignore[assignment]
        successor_id: str | None = row.successor_id  # type: ignore[assignment]
        parent_ids_str: str = row.parent_ids or "[]"  # type: ignore[assignment]
        derivation_type: str = row.derivation_type or "induction"  # type: ignore[assignment]
        created_at: datetime = row.created_at  # type: ignore[assignment]
        updated_at: datetime = row.updated_at  # type: ignore[assignment]

        # Convert version string to int (e.g., "v1" -> 1, "v2" -> 2)
        try:
            version = int(version_str.lstrip("v"))
        except ValueError:
            version = 1

        # Build IndexProfile from Q-value fields
        index_profile = IndexProfile(
            q_value=q_value,
            q_update_count=q_update_count,
            created_at=created_at,
            last_used_at=updated_at,
        )

        return Skill(
            id=skill_id,
            name=name,
            trigger_pattern=trigger_pattern,
            code_template=json.loads(code_template_str),
            description=description,
            tags=[],
            created_at=created_at,
            updated_at=updated_at,
            metadata={
                "q_value": q_value,
            },
            parent_ids=json.loads(parent_ids_str) if parent_ids_str else [],
            derivation_type=derivation_type,  # type: ignore[arg-type]
            index_profile=index_profile,
            version=version,
            is_deprecated=deprecated,
            successor_id=successor_id,
        )

    def add_skill(
        self,
        name: str,
        trigger_pattern: str,
        code_template: dict[str, Any],
        description: str | None = None,
        parent_ids: list[str] | None = None,
        derivation_type: str = "extraction",
    ) -> str:
        """Add new skill template.

        Args:
            name: Unique skill identifier
            trigger_pattern: Activation condition (supports | for alternatives)
            code_template: Parameterized template (dict with steps, params, etc.)
            description: Human-readable description
            parent_ids: Source memory IDs for provenance
            derivation_type: How skill was derived (extraction/induction)

        Returns:
            skill_id: Unique identifier for the skill

        Raises:
            IntegrityError: If skill name already exists
        """
        skill_id = f"skill_{uuid.uuid4().hex[:12]}"

        with self.SessionLocal() as session:
            new_skill = SkillRow(
                skill_id=skill_id,
                name=name,
                trigger_pattern=trigger_pattern,
                code_template=json.dumps(code_template),
                description=description,
                parent_ids=json.dumps(parent_ids or []),
                derivation_type=derivation_type,
            )

            try:
                session.add(new_skill)
                session.commit()
            except IntegrityError:
                session.rollback()
                # Update existing skill instead
                existing = session.query(SkillRow).filter(SkillRow.name == name).first()
                if existing:
                    existing.trigger_pattern = trigger_pattern  # type: ignore[assignment]
                    existing.code_template = json.dumps(code_template)  # type: ignore[assignment]
                    existing.description = description  # type: ignore[assignment]
                    existing.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]
                    session.commit()
                    skill_id = str(existing.skill_id)  # type: ignore[arg-type]

            logger.debug(
                "skill_added",
                skill_id=skill_id,
                name=name,
                trigger_pattern=trigger_pattern[:50],
            )

            return skill_id

    def get_skill(self, name: str) -> Skill | None:
        """Retrieve skill by name.

        Args:
            name: Skill identifier

        Returns:
            Skill Pydantic model or None if not found
        """
        with self.SessionLocal() as session:
            row = session.query(SkillRow).filter(SkillRow.name == name).first()

            if not row:
                return None

            return self._row_to_skill(row)

    def get_skill_by_id(self, skill_id: str) -> Skill | None:
        """Retrieve skill by ID.

        Args:
            skill_id: Unique skill identifier

        Returns:
            Skill Pydantic model or None if not found
        """
        with self.SessionLocal() as session:
            row = session.query(SkillRow).filter(SkillRow.skill_id == skill_id).first()

            if not row:
                return None

            return self._row_to_skill(row)

    def _evaluate_pattern_match(
        self, pattern: str, query_lower: str, query_words: set[str]
    ) -> tuple[bool, float]:
        """Evaluate a single pattern against the query and return match status and score."""
        # Exact match
        if pattern == query_lower:
            return True, 1.0

        # Substring match
        if pattern in query_lower or query_lower in pattern:
            return True, 0.8

        # Word overlap
        pattern_words = set(pattern.split())
        if pattern_words & query_words:
            score = self._calculate_match_score(pattern, query_lower)
            return True, score

        return False, 0.0

    def search_by_trigger(self, query: str, limit: int = 5) -> list[Skill]:
        """Search skills by matching trigger patterns.

        Args:
            query: User query to match against trigger patterns
            limit: Maximum results

        Returns:
            List of matching Skill models sorted by Q-value
        """
        with self.SessionLocal() as session:
            # Get all skills and match against query
            all_skills = session.query(SkillRow).all()

            matches: list[tuple[Skill, float]] = []
            query_lower = query.lower()
            query_words = set(query_lower.split())

            for row in all_skills:
                # Convert to Skill model
                skill = self._row_to_skill(row)
                trigger_pattern = skill.trigger_pattern

                # Split trigger pattern by | and check each alternative
                patterns = trigger_pattern.lower().split("|")
                best_match_score = 0.0
                matched = False

                for pattern in patterns:
                    pattern = pattern.strip()
                    is_match, score = self._evaluate_pattern_match(
                        pattern, query_lower, query_words
                    )
                    if is_match:
                        matched = True
                        best_match_score = max(best_match_score, score)
                        if score == 1.0:  # Perfect match, no need to check others
                            break

                if matched:
                    matches.append((skill, best_match_score))

            # Sort by match score and Q-value
            def q_value_func(s: Skill) -> float:
                profile = s.index_profile
                if profile is None:
                    return 0.5
                return profile.q_value

            matches.sort(key=lambda x: (x[1], q_value_func(x[0])), reverse=True)

            return [skill for skill, _ in matches[:limit]]

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Search skills and return as Memory objects.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of Memory objects representing skills
        """
        skills = self.search_by_trigger(query, limit)

        memories = []
        for skill in skills:
            content = f"Skill: {skill.name}\nTrigger: {skill.trigger_pattern}"
            if skill.description:
                content += f"\nDescription: {skill.description}"

            # Access Q-value via index_profile
            profile = skill.index_profile
            q_value = profile.q_value if profile else 0.5

            memories.append(
                Memory(
                    id=skill.id,
                    content=content,
                    score=0.8,  # Base score for skill matches
                    source="skill",
                    timestamp=skill.created_at,
                    metadata={
                        "name": skill.name,
                        "trigger_pattern": skill.trigger_pattern,
                        "code_template": skill.code_template,
                        "q_value": q_value,
                    },
                    index_profile=profile,
                )
            )

        return memories

    def record_success(self, skill_id: str) -> bool:
        """Record successful skill execution by updating Q-value.

        Args:
            skill_id: Skill identifier

        Returns:
            True if updated, False if not found
        """
        return self._update_q_value(skill_id, reward=1.0)

    def record_failure(self, skill_id: str) -> bool:
        """Record failed skill execution by updating Q-value.

        Args:
            skill_id: Skill identifier

        Returns:
            True if updated, False if not found
        """
        return self._update_q_value(skill_id, reward=0.0)

    def _update_q_value(self, skill_id: str, reward: float, alpha: float = 0.1) -> bool:
        """Update Q-value using Monte Carlo update rule.

        Args:
            skill_id: Skill identifier
            reward: Reward signal (1.0 = success, 0.0 = failure)
            alpha: Learning rate

        Returns:
            True if updated, False if not found
        """
        with self.SessionLocal() as session:
            row = (
                session.query(SkillRow)
                .filter(SkillRow.skill_id == skill_id)
                .first()
            )
            if not row:
                return False

            current_q: float = getattr(row, "q_value", None) or 0.5
            current_count: int = getattr(row, "q_update_count", None) or 0

            # Monte Carlo update: Q_new = Q_old + α(r - Q_old)
            new_q = current_q + alpha * (reward - current_q)
            new_count = current_count + 1

            session.query(SkillRow).filter(SkillRow.skill_id == skill_id).update(
                {
                    "q_value": new_q,
                    "q_update_count": new_count,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            session.commit()

            logger.debug(
                "skill_q_value_updated",
                skill_id=skill_id,
                old_q=current_q,
                new_q=new_q,
                reward=reward,
            )

            return True

    def update_index_profile(self, skill_id: str, profile: IndexProfile) -> bool:
        """Update the IndexProfile for a skill.

        Args:
            skill_id: Skill identifier
            profile: Updated IndexProfile

        Returns:
            True if updated, False if not found
        """
        with self.SessionLocal() as session:
            rows = (
                session.query(SkillRow)
                .filter(SkillRow.skill_id == skill_id)
                .update(
                    {
                        "q_value": profile.q_value,
                        "q_update_count": profile.q_update_count,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
            )
            session.commit()

            if rows > 0:
                logger.debug(
                    "skill_index_profile_updated",
                    skill_id=skill_id,
                    q_value=profile.q_value,
                    q_update_count=profile.q_update_count,
                )

            return rows > 0

    def deprecate_skill(self, skill_id: str, successor_id: str | None = None) -> bool:
        """Mark a skill as deprecated.

        Args:
            skill_id: Skill identifier
            successor_id: Optional ID of the replacement skill

        Returns:
            True if updated, False if not found
        """
        with self.SessionLocal() as session:
            update_data: dict[str, bool | str | datetime] = {
                "deprecated": True,
                "updated_at": datetime.now(timezone.utc),
            }
            if successor_id:
                update_data["successor_id"] = successor_id

            rows = (
                session.query(SkillRow)
                .filter(SkillRow.skill_id == skill_id)
                .update(update_data)  # type: ignore[arg-type]
            )
            session.commit()

            if rows > 0:
                logger.info(
                    "skill_deprecated",
                    skill_id=skill_id,
                    successor_id=successor_id,
                )

            return rows > 0

    def delete_skill(self, name: str) -> bool:
        """Delete a skill by name.

        Args:
            name: Skill name

        Returns:
            True if deleted, False if not found
        """
        with self.SessionLocal() as session:
            deleted = session.query(SkillRow).filter(SkillRow.name == name).delete()
            session.commit()
            return deleted > 0

    def list_all(self) -> list[Skill]:
        """List all skills.

        Returns:
            List of all Skill models
        """
        with self.SessionLocal() as session:
            rows = session.query(SkillRow).order_by(SkillRow.name).all()

            return [self._row_to_skill(row) for row in rows]

    def _calculate_match_score(self, pattern: str, query: str) -> float:
        """Calculate how well a pattern matches a query.

        Args:
            pattern: Trigger pattern
            query: User query

        Returns:
            Match score between 0 and 1
        """
        # Simple overlap ratio
        pattern_words = set(pattern.split())
        query_words = set(query.split())

        if not pattern_words or not query_words:
            return 0.0

        intersection = pattern_words & query_words
        union = pattern_words | query_words

        return len(intersection) / len(union) if union else 0.0

    def health_check(self) -> dict[str, str | int]:
        """Check skill store health.

        Returns:
            Health metrics
        """
        stats = self.get_stats()
        return {"status": "healthy", **stats}

    def get_stats(self) -> dict[str, int]:
        """Get skill statistics.

        Returns:
            Statistics dictionary
        """
        with self.SessionLocal() as session:
            total = session.query(SkillRow).count()

            # Calculate average Q-value
            all_skills = session.query(SkillRow).all()
            if all_skills:
                q_values = []
                for row in all_skills:
                    q_value: float = getattr(row, "q_value", None) or 0.5
                    q_values.append(q_value)
                avg_q = sum(q_values) / len(q_values)
            else:
                avg_q = 0.5

            return {
                "total_skills": total,
                "avg_q_value": int(avg_q * 100),  # Percentage
            }

    def clear(self) -> int:
        """Clear all skills (for testing).

        Returns:
            Number of skills deleted
        """
        with self.SessionLocal() as session:
            deleted = session.query(SkillRow).delete()
            session.commit()
            return deleted
