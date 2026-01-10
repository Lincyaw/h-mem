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
    Index,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker  # type: ignore
from sqlalchemy.exc import IntegrityError  # type: ignore

from hmem.storage.base import BaseStore
from hmem.models import Memory

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
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    parent_ids = Column(Text, default="[]")  # JSON array of source memory IDs
    derivation_type = Column(String, default="extraction")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_skill_name", "name"),
        Index("idx_trigger_pattern", "trigger_pattern"),
    )


class SkillStore(BaseStore):
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

    def _row_to_dict(
        self, row: SkillRow, include_template: bool = True
    ) -> dict[str, Any]:
        """Convert SkillRow to dictionary.

        Args:
            row: SQLAlchemy row object
            include_template: Whether to include code_template

        Returns:
            Dictionary representation of the skill
        """
        # Access row attributes (SQLAlchemy returns Python types at runtime)
        skill_id: str = row.skill_id  # type: ignore[assignment]
        name: str = row.name  # type: ignore[assignment]
        trigger_pattern: str = row.trigger_pattern  # type: ignore[assignment]
        code_template_str: str = row.code_template  # type: ignore[assignment]
        description: str | None = row.description  # type: ignore[assignment]
        success_count: int = row.success_count or 0  # type: ignore[assignment]
        failure_count: int = row.failure_count or 0  # type: ignore[assignment]
        parent_ids_str: str = row.parent_ids or "[]"  # type: ignore[assignment]
        derivation_type: str = row.derivation_type or "extraction"  # type: ignore[assignment]
        created_at: datetime = row.created_at  # type: ignore[assignment]
        updated_at: datetime = row.updated_at  # type: ignore[assignment]

        result: dict[str, Any] = {
            "skill_id": skill_id,
            "name": name,
            "trigger_pattern": trigger_pattern,
            "description": description,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": self._calculate_success_rate(success_count, failure_count),
            "parent_ids": json.loads(parent_ids_str) if parent_ids_str else [],
            "derivation_type": derivation_type,
            "created_at": created_at,
            "updated_at": updated_at,
        }

        if include_template:
            result["code_template"] = json.loads(code_template_str)

        return result

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

    def get_skill(self, name: str) -> dict[str, Any] | None:
        """Retrieve skill by name.

        Args:
            name: Skill identifier

        Returns:
            Skill template dict or None if not found
        """
        with self.SessionLocal() as session:
            row = session.query(SkillRow).filter(SkillRow.name == name).first()

            if not row:
                return None

            return self._row_to_dict(row)

    def get_skill_by_id(self, skill_id: str) -> dict[str, Any] | None:
        """Retrieve skill by ID.

        Args:
            skill_id: Unique skill identifier

        Returns:
            Skill template dict or None if not found
        """
        with self.SessionLocal() as session:
            row = session.query(SkillRow).filter(SkillRow.skill_id == skill_id).first()

            if not row:
                return None

            return self._row_to_dict(row)

    def search_by_trigger(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search skills by matching trigger patterns.

        Args:
            query: User query to match against trigger patterns
            limit: Maximum results

        Returns:
            List of matching skills sorted by success rate
        """
        with self.SessionLocal() as session:
            # Get all skills and match against query
            all_skills = session.query(SkillRow).all()

            matches = []
            query_lower = query.lower()
            query_words = set(query_lower.split())

            for row in all_skills:
                # Extract row data with proper typing
                skill_data = self._row_to_dict(row, include_template=True)
                trigger_pattern: str = skill_data["trigger_pattern"]

                # Split trigger pattern by | and check each alternative
                patterns = trigger_pattern.lower().split("|")
                best_match_score = 0.0
                matched = False

                for pattern in patterns:
                    pattern = pattern.strip()
                    pattern_words = set(pattern.split())

                    # Check for exact substring match
                    if pattern in query_lower or query_lower in pattern:
                        matched = True
                        best_match_score = max(
                            best_match_score,
                            self._calculate_match_score(pattern, query_lower),
                        )
                    # Check for word overlap (any common words)
                    elif pattern_words & query_words:
                        matched = True
                        best_match_score = max(
                            best_match_score,
                            self._calculate_match_score(pattern, query_lower),
                        )

                if matched:
                    skill_data["match_score"] = best_match_score
                    matches.append(skill_data)

            # Sort by match score and success rate
            matches.sort(
                key=lambda x: (x["match_score"], x["success_rate"]), reverse=True
            )

            return matches[:limit]

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
            content = f"Skill: {skill['name']}\nTrigger: {skill['trigger_pattern']}"
            if skill.get("description"):
                content += f"\nDescription: {skill['description']}"

            memories.append(
                Memory(
                    id=skill["skill_id"],
                    content=content,
                    score=skill.get("match_score", 0.5),
                    source="skill",
                    timestamp=datetime.now(timezone.utc),
                    metadata={
                        "name": skill["name"],
                        "trigger_pattern": skill["trigger_pattern"],
                        "code_template": skill["code_template"],
                        "success_rate": skill.get("success_rate", 0.0),
                    },
                )
            )

        return memories

    def record_success(self, skill_id: str) -> bool:
        """Record successful skill execution.

        Args:
            skill_id: Skill identifier

        Returns:
            True if updated, False if not found
        """
        with self.SessionLocal() as session:
            rows = (
                session.query(SkillRow)
                .filter(SkillRow.skill_id == skill_id)
                .update(
                    {
                        "success_count": SkillRow.success_count + 1,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
            )
            session.commit()

            if rows > 0:
                logger.debug("skill_success_recorded", skill_id=skill_id)

            return rows > 0

    def record_failure(self, skill_id: str) -> bool:
        """Record failed skill execution.

        Args:
            skill_id: Skill identifier

        Returns:
            True if updated, False if not found
        """
        with self.SessionLocal() as session:
            rows = (
                session.query(SkillRow)
                .filter(SkillRow.skill_id == skill_id)
                .update(
                    {
                        "failure_count": SkillRow.failure_count + 1,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
            )
            session.commit()

            if rows > 0:
                logger.debug("skill_failure_recorded", skill_id=skill_id)

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

    def list_all(self) -> list[dict[str, Any]]:
        """List all skills.

        Returns:
            List of all skill templates
        """
        with self.SessionLocal() as session:
            rows = session.query(SkillRow).order_by(SkillRow.name).all()

            return [self._row_to_dict(row, include_template=False) for row in rows]

    def _calculate_success_rate(self, success: int, failure: int) -> float:
        """Calculate success rate from counts.

        Args:
            success: Success count
            failure: Failure count

        Returns:
            Success rate between 0 and 1
        """
        total = success + failure
        if total == 0:
            return 0.5  # Default for new skills
        return success / total

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

            # Calculate average success rate
            all_skills = session.query(SkillRow).all()
            if all_skills:
                rates = []
                for row in all_skills:
                    # Extract row data with proper typing
                    success_count: int = row.success_count or 0  # type: ignore[assignment]
                    failure_count: int = row.failure_count or 0  # type: ignore[assignment]
                    rates.append(
                        self._calculate_success_rate(success_count, failure_count)
                    )
                avg_rate = sum(rates) / len(rates)
            else:
                avg_rate = 0.0

            return {
                "total_skills": total,
                "avg_success_rate": int(avg_rate * 100),  # Percentage
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
