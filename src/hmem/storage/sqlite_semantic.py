"""SQLite-based semantic memory store implementation (Phase 2).

Implements the Semantic Store from design.md with:
- Triple storage (subject-predicate-object)
- Weight-based importance tracking
- Optimistic locking for conflict detection
- Provenance tracking (parent_ids)
- Multi-hop relationship traversal via closure table
"""

from datetime import datetime, timezone
from typing import Any
import json
import uuid
import structlog

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    Boolean,
    UniqueConstraint,
    Index,
    create_engine,
    and_,
    or_,
)
from sqlalchemy.orm import declarative_base, sessionmaker  # type: ignore
from sqlalchemy.exc import IntegrityError  # type: ignore

from hmem.models import SemanticTriple, Memory
from hmem.exceptions import ConsolidationError

logger = structlog.get_logger()

Base = declarative_base()  # type: ignore


class SemanticFactRow(Base):  # type: ignore
    """SQLite table for semantic triples with provenance."""

    __tablename__ = "semantic_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fact_id = Column(String, unique=True, nullable=False, index=True)
    subject = Column(String, nullable=False, index=True)
    predicate = Column(String, nullable=False)
    object = Column(Text, nullable=False)
    weight = Column(Float, default=1.0)
    version = Column(Integer, default=1)
    access_count = Column(Integer, default=0)
    is_superseded = Column(Boolean, default=False)
    superseded_by = Column(String, nullable=True)
    parent_ids = Column(Text, default="[]")  # JSON array of parent memory IDs
    derivation_type = Column(String, default="extraction")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("subject", "predicate", "object", name="_spo_uc"),
        Index("idx_subject", "subject"),
        Index("idx_spo", "subject", "predicate", "object"),
        Index("idx_predicate", "predicate"),
    )


class SemanticClosureRow(Base):  # type: ignore
    """Pre-computed transitive closure for multi-hop queries."""

    __tablename__ = "semantic_closure"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ancestor = Column(String, nullable=False, index=True)
    descendant = Column(String, nullable=False, index=True)
    path_length = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("ancestor", "descendant", name="_ad_uc"),
        Index("idx_ancestor", "ancestor"),
        Index("idx_descendant", "descendant"),
    )


class SQLiteSemanticStore:
    """SQLite-based semantic graph store with conflict resolution.

    Features:
    - Triple storage (subject-predicate-object)
    - Weight-based importance tracking
    - Optimistic locking for conflict detection
    - Provenance tracking (parent_ids, derivation_type)
    - Multi-hop relationship traversal
    - Active forgetting (prune low-weight facts)
    - Reconsolidation (update weights on access)
    """

    MAX_QUERY_DEPTH = 3  # Hard limit for traversal depth

    def __init__(self, database_url: str = "sqlite:///./semantic.db"):
        """Initialize SQLite semantic store.

        Args:
            database_url: SQLite database URL
        """
        self.engine = create_engine(database_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def add_or_update(
        self,
        triple: SemanticTriple,
        parent_ids: list[str] | None = None,
    ) -> tuple[bool, int]:
        """Add a new triple or update existing one with optimistic locking.

        Args:
            triple: Semantic triple to add/update
            parent_ids: Source memory IDs for provenance

        Returns:
            Tuple of (was_conflict, conflicts_resolved)

        Raises:
            ConsolidationError: If optimistic lock conflict after retries
        """
        parent_ids = parent_ids or triple.parent_ids
        fact_id = f"fact_{uuid.uuid4().hex[:12]}"

        with self.SessionLocal() as session:
            # Check for existing triple
            existing = (
                session.query(SemanticFactRow)
                .filter(
                    and_(
                        SemanticFactRow.subject == triple.subject,
                        SemanticFactRow.predicate == triple.predicate,
                        SemanticFactRow.object == triple.object,
                        SemanticFactRow.is_superseded == False,  # noqa: E712
                    )
                )
                .first()
            )

            if existing:
                # Update with optimistic locking
                old_version = existing.version
                rows_affected = (
                    session.query(SemanticFactRow)
                    .filter(
                        and_(
                            SemanticFactRow.id == existing.id,
                            SemanticFactRow.version == old_version,
                        )
                    )
                    .update(
                        {
                            "weight": SemanticFactRow.weight + 0.1,
                            "version": SemanticFactRow.version + 1,
                            "access_count": SemanticFactRow.access_count + 1,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    )
                )
                session.commit()

                if rows_affected == 0:
                    raise ConsolidationError(
                        f"Optimistic lock conflict for triple: {triple.subject}-{triple.predicate}-{triple.object}"
                    )

                logger.debug(
                    "semantic_triple_updated",
                    subject=triple.subject,
                    predicate=triple.predicate,
                    new_version=old_version + 1,
                )
                return False, 0
            else:
                # Add new triple
                new_row = SemanticFactRow(
                    fact_id=fact_id,
                    subject=triple.subject,
                    predicate=triple.predicate,
                    object=triple.object,
                    weight=triple.weight,
                    version=1,
                    parent_ids=json.dumps(parent_ids),
                    derivation_type=triple.derivation_type or "extraction",
                )
                session.add(new_row)
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    # Race condition: another process added the same triple
                    return self.add_or_update(triple, parent_ids)

                logger.debug(
                    "semantic_triple_added",
                    fact_id=fact_id,
                    subject=triple.subject,
                    predicate=triple.predicate,
                )
                return False, 0

    def update_weight(self, fact_id: str, delta: float = 0.1) -> bool:
        """Update weight of a fact (reconsolidation mechanism).

        Args:
            fact_id: Unique fact identifier
            delta: Weight change (positive = strengthen, negative = weaken)

        Returns:
            True if updated, False if not found
        """
        with self.SessionLocal() as session:
            rows = (
                session.query(SemanticFactRow)
                .filter(SemanticFactRow.fact_id == fact_id)
                .update(
                    {
                        "weight": SemanticFactRow.weight + delta,
                        "access_count": SemanticFactRow.access_count + 1,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
            )
            session.commit()
            return rows > 0

    def increment_access(self, fact_id: str) -> bool:
        """Increment access count (for reconsolidation on recall).

        Args:
            fact_id: Unique fact identifier

        Returns:
            True if updated, False if not found
        """
        return self.update_weight(fact_id, delta=0.05)

    def check_conflict(
        self, subject: str, predicate: str, new_object: str
    ) -> tuple[bool, list[SemanticTriple]]:
        """Check if a new triple conflicts with existing ones.

        A conflict exists when same (subject, predicate) has different object.
        Example: User EATS Vegetarian conflicts with User EATS Pescatarian

        Args:
            subject: Subject of the triple
            predicate: Predicate (relationship)
            new_object: New object value

        Returns:
            Tuple of (has_conflict, list of conflicting triples)
        """
        with self.SessionLocal() as session:
            existing = (
                session.query(SemanticFactRow)
                .filter(
                    and_(
                        SemanticFactRow.subject == subject,
                        SemanticFactRow.predicate == predicate,
                        SemanticFactRow.object != new_object,
                        SemanticFactRow.is_superseded == False,  # noqa: E712
                    )
                )
                .all()
            )

            if not existing:
                return False, []

            conflicting_triples = [
                SemanticTriple(
                    id=row.fact_id,
                    subject=row.subject,
                    predicate=row.predicate,
                    object=row.object,
                    weight=row.weight,
                    version=row.version,
                    parent_ids=json.loads(row.parent_ids) if row.parent_ids else [],
                )
                for row in existing
            ]

            return True, conflicting_triples

    def resolve_conflict(
        self,
        subject: str,
        predicate: str,
        old_object: str,
        new_object: str,
        new_parent_ids: list[str] | None = None,
    ) -> int:
        """Resolve conflict by superseding old triple and adding new one.

        The old triple is marked as superseded (soft delete) rather than
        removed, maintaining full history for auditing.

        Args:
            subject: Subject of the triple
            predicate: Predicate
            old_object: Old object to supersede
            new_object: New object value
            new_parent_ids: Parent IDs for the new triple

        Returns:
            Number of conflicts resolved
        """
        new_fact_id = f"fact_{uuid.uuid4().hex[:12]}"

        with self.SessionLocal() as session:
            # Mark old triple as superseded
            old_row = (
                session.query(SemanticFactRow)
                .filter(
                    and_(
                        SemanticFactRow.subject == subject,
                        SemanticFactRow.predicate == predicate,
                        SemanticFactRow.object == old_object,
                        SemanticFactRow.is_superseded == False,  # noqa: E712
                    )
                )
                .first()
            )

            conflicts_resolved = 0
            if old_row:
                old_row.is_superseded = True
                old_row.superseded_by = new_fact_id
                old_row.weight *= 0.5  # Decay weight
                old_row.updated_at = datetime.now(timezone.utc)
                conflicts_resolved = 1

            # Add new triple with supersession derivation type
            new_row = SemanticFactRow(
                fact_id=new_fact_id,
                subject=subject,
                predicate=predicate,
                object=new_object,
                weight=1.0,
                version=1,
                parent_ids=json.dumps(new_parent_ids or []),
                derivation_type="supersession",
            )
            session.add(new_row)

            session.commit()

            logger.info(
                "semantic_conflict_resolved",
                subject=subject,
                predicate=predicate,
                old_object=old_object,
                new_object=new_object,
            )

            return conflicts_resolved

    def query_related(
        self, entity: str, max_depth: int = 2
    ) -> list[tuple[str, str, str, float]]:
        """Query related entities up to max_depth hops.

        Args:
            entity: Starting entity
            max_depth: Maximum traversal depth (1-3)

        Returns:
            List of (subject, predicate, object, weight) tuples
        """
        max_depth = min(max_depth, self.MAX_QUERY_DEPTH)

        with self.SessionLocal() as session:
            # Direct relations (depth=1)
            results = (
                session.query(SemanticFactRow)
                .filter(
                    and_(
                        or_(
                            SemanticFactRow.subject == entity,
                            SemanticFactRow.object == entity,
                        ),
                        SemanticFactRow.is_superseded == False,  # noqa: E712
                    )
                )
                .all()
            )

            relations = [
                (row.subject, row.predicate, row.object, row.weight) for row in results
            ]

            if max_depth <= 1:
                return relations

            # Multi-hop (depth > 1): BFS traversal
            visited = {entity}
            frontier = set()

            for row in results:
                frontier.add(row.subject if row.subject != entity else row.object)
                frontier.add(row.object if row.object != entity else row.subject)

            for depth in range(2, max_depth + 1):
                next_frontier = set()
                for node in frontier:
                    if node in visited:
                        continue
                    visited.add(node)

                    node_results = (
                        session.query(SemanticFactRow)
                        .filter(
                            and_(
                                or_(
                                    SemanticFactRow.subject == node,
                                    SemanticFactRow.object == node,
                                ),
                                SemanticFactRow.is_superseded == False,  # noqa: E712
                            )
                        )
                        .all()
                    )

                    for row in node_results:
                        relations.append(
                            (row.subject, row.predicate, row.object, row.weight)
                        )
                        next_frontier.add(row.subject)
                        next_frontier.add(row.object)

                frontier = next_frontier - visited

            return relations

    def get_by_id(self, fact_id: str) -> SemanticTriple | None:
        """Get a triple by its ID.

        Args:
            fact_id: Unique fact identifier

        Returns:
            SemanticTriple if found, None otherwise
        """
        with self.SessionLocal() as session:
            row = (
                session.query(SemanticFactRow)
                .filter(SemanticFactRow.fact_id == fact_id)
                .first()
            )

            if not row:
                return None

            return SemanticTriple(
                id=row.fact_id,
                subject=row.subject,
                predicate=row.predicate,
                object=row.object,
                weight=row.weight,
                version=row.version,
                created_at=row.created_at,
                updated_at=row.updated_at,
                parent_ids=json.loads(row.parent_ids) if row.parent_ids else [],
                derivation_type=row.derivation_type,
            )

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Search semantic facts by text matching.

        Args:
            query: Query text
            limit: Maximum results

        Returns:
            List of relevant memories with provenance
        """
        with self.SessionLocal() as session:
            query_lower = query.lower()

            results = (
                session.query(SemanticFactRow)
                .filter(
                    and_(
                        or_(
                            SemanticFactRow.subject.ilike(f"%{query_lower}%"),
                            SemanticFactRow.object.ilike(f"%{query_lower}%"),
                            SemanticFactRow.predicate.ilike(f"%{query_lower}%"),
                        ),
                        SemanticFactRow.is_superseded == False,  # noqa: E712
                    )
                )
                .order_by(SemanticFactRow.weight.desc())
                .limit(limit)
                .all()
            )

            memories = []
            for row in results:
                # Increment access count (reconsolidation)
                row.access_count += 1

                content = f"{row.subject} {row.predicate} {row.object}"
                memories.append(
                    Memory(
                        id=row.fact_id,
                        content=content,
                        score=min(row.weight, 1.0),
                        source="semantic",
                        timestamp=row.updated_at,
                        metadata={
                            "subject": row.subject,
                            "predicate": row.predicate,
                            "object": row.object,
                            "weight": row.weight,
                            "access_count": row.access_count,
                        },
                        parent_ids=json.loads(row.parent_ids) if row.parent_ids else [],
                        derivation_type=row.derivation_type,
                    )
                )

            session.commit()  # Save access count updates
            return memories

    def prune_low_weight(self, threshold: float = 0.3) -> int:
        """Remove low-weight facts (active forgetting).

        Facts below threshold are soft-deleted (marked as superseded)
        to maintain history while freeing up query performance.

        Args:
            threshold: Minimum weight threshold

        Returns:
            Number of facts pruned
        """
        with self.SessionLocal() as session:
            pruned = (
                session.query(SemanticFactRow)
                .filter(
                    and_(
                        SemanticFactRow.weight < threshold,
                        SemanticFactRow.is_superseded == False,  # noqa: E712
                    )
                )
                .update(
                    {
                        "is_superseded": True,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
            )
            session.commit()

            logger.info("semantic_facts_pruned", count=pruned, threshold=threshold)
            return pruned

    def apply_decay(self, decay_factor: float = 0.99, min_weight: float = 0.1) -> int:
        """Apply time-based decay to all weights.

        This simulates forgetting over time - facts that aren't accessed
        gradually lose weight.

        Args:
            decay_factor: Multiplier for weight decay (0-1)
            min_weight: Minimum weight floor

        Returns:
            Number of facts decayed
        """
        with self.SessionLocal() as session:
            decayed = (
                session.query(SemanticFactRow)
                .filter(
                    and_(
                        SemanticFactRow.weight > min_weight,
                        SemanticFactRow.is_superseded == False,  # noqa: E712
                    )
                )
                .update(
                    {
                        "weight": SemanticFactRow.weight * decay_factor,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
            )
            session.commit()
            return decayed

    def count(self) -> dict[str, int]:
        """Get count statistics.

        Returns:
            Dictionary with node and edge counts
        """
        with self.SessionLocal() as session:
            total = (
                session.query(SemanticFactRow)
                .filter(SemanticFactRow.is_superseded == False)  # noqa: E712
                .count()
            )

            unique_subjects = (
                session.query(SemanticFactRow.subject)
                .filter(SemanticFactRow.is_superseded == False)  # noqa: E712
                .distinct()
                .count()
            )

            superseded = (
                session.query(SemanticFactRow)
                .filter(SemanticFactRow.is_superseded == True)  # noqa: E712
                .count()
            )

            return {
                "total_facts": total,
                "unique_entities": unique_subjects,
                "superseded_facts": superseded,
            }

    def health_check(self) -> dict[str, Any]:
        """Get health status of the store.

        Returns:
            Health status dictionary
        """
        stats = self.count()
        return {"status": "healthy", **stats}

    def get_all_for_entity(self, entity: str) -> list[SemanticTriple]:
        """Get all facts for an entity.

        Args:
            entity: Entity to query

        Returns:
            List of semantic triples
        """
        with self.SessionLocal() as session:
            results = (
                session.query(SemanticFactRow)
                .filter(
                    and_(
                        SemanticFactRow.subject == entity,
                        SemanticFactRow.is_superseded == False,  # noqa: E712
                    )
                )
                .all()
            )

            return [
                SemanticTriple(
                    id=row.fact_id,
                    subject=row.subject,
                    predicate=row.predicate,
                    object=row.object,
                    weight=row.weight,
                    version=row.version,
                    parent_ids=json.loads(row.parent_ids) if row.parent_ids else [],
                    derivation_type=row.derivation_type,
                )
                for row in results
            ]

    def clear(self) -> int:
        """Clear all facts (for testing).

        Returns:
            Number of facts deleted
        """
        with self.SessionLocal() as session:
            deleted = session.query(SemanticFactRow).delete()
            session.commit()
            return deleted

    def get_stats(self) -> dict[str, Any]:
        """Get store statistics.

        Returns:
            Statistics dictionary
        """
        with self.SessionLocal() as session:
            total = session.query(SemanticFactRow).count()
            active = (
                session.query(SemanticFactRow)
                .filter(SemanticFactRow.is_superseded == False)  # noqa: E712
                .count()
            )
            superseded = total - active

            return {
                "total_triples": active,
                "superseded_triples": superseded,
                "total_stored": total,
            }
