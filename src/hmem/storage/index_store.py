"""Index Store - SQLite-based storage for usage statistics and associations.

Implements the IndexStore from interfaces.md with:
- Index profiles for memory usage statistics
- Usage records for tracking individual memory usage
- Associations for discovered relationships between memories
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import uuid
import structlog

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Float,
    Index,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker  # type: ignore

from hmem.models import IndexProfile, UsageRecord, Association

logger = structlog.get_logger()

Base = declarative_base()  # type: ignore


class IndexProfileRow(Base):  # type: ignore
    """SQLite table for index profiles (memory usage statistics)."""

    __tablename__ = "index_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(String, unique=True, nullable=False, index=True)
    usage_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    weight = Column(Float, default=1.0)
    first_used_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (Index("idx_memory_id", "memory_id"),)


class UsageRecordRow(Base):  # type: ignore
    """SQLite table for usage records."""

    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(String, unique=True, nullable=False, index=True)
    memory_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    subtask_id = Column(String, nullable=True)
    sequence_position = Column(Integer, default=0)
    query = Column(Text, nullable=False)
    rank_position = Column(Integer, nullable=False)
    outcome = Column(String, default="unknown")
    used_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_usage_memory_id", "memory_id"),
        Index("idx_usage_session_id", "session_id"),
    )


class AssociationRow(Base):  # type: ignore
    """SQLite table for discovered associations."""

    __tablename__ = "associations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String, nullable=False, index=True)
    target_id = Column(String, nullable=False, index=True)
    relation_type = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    support = Column(Integer, nullable=False)
    discovered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_assoc_source", "source_id"),
        Index("idx_assoc_target", "target_id"),
        Index("idx_assoc_type", "relation_type"),
    )


class IndexStore:
    """SQLite-based storage for index profiles, usage records, and associations.

    This store handles high-frequency read/write operations for:
    - Memory usage statistics (IndexProfile)
    - Individual usage records (UsageRecord)
    - Discovered memory relationships (Association)

    Example:
        >>> store = IndexStore(db_path=Path("./.hmem/index.db"))
        >>> store.record_usage(usage_record)
        >>> profile = store.get_profile("mem_123")
    """

    def __init__(self, db_path: Path | str) -> None:
        """Initialize index store.

        Args:
            db_path: SQLite database path (can be Path or str)
        """
        if isinstance(db_path, str):
            if db_path.startswith("sqlite://"):
                database_url = db_path
            else:
                database_url = f"sqlite:///{db_path}"
        else:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            database_url = f"sqlite:///{db_path}"

        self.engine = create_engine(database_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        logger.info("index_store_initialized", db_url=database_url)

    # ========== Index Profile Methods ==========

    def get_profile(self, memory_id: str) -> IndexProfile | None:
        """Get index profile for a memory.

        Args:
            memory_id: Memory identifier

        Returns:
            IndexProfile if found, None otherwise
        """
        with self.SessionLocal() as session:
            row = (
                session.query(IndexProfileRow)
                .filter(IndexProfileRow.memory_id == memory_id)
                .first()
            )

            if not row:
                return None

            # Extract row data with proper typing
            usage_count: int = row.usage_count or 0  # type: ignore[assignment]
            success_count: int = row.success_count or 0  # type: ignore[assignment]
            failure_count: int = row.failure_count or 0  # type: ignore[assignment]
            weight: float = row.weight or 1.0  # type: ignore[assignment]
            created_at: datetime = row.created_at or datetime.now(timezone.utc)  # type: ignore[assignment]
            last_used_at: datetime | None = row.last_used_at  # type: ignore[assignment]

            return IndexProfile(
                usage_count=usage_count,
                success_count=success_count,
                failure_count=failure_count,
                weight=weight,
                created_at=created_at,
                last_used_at=last_used_at,
            )

    def get_or_create_profile(self, memory_id: str) -> IndexProfile:
        """Get or create index profile for a memory.

        Args:
            memory_id: Memory identifier

        Returns:
            IndexProfile (existing or newly created)
        """
        profile = self.get_profile(memory_id)
        if profile:
            return profile

        # Create new profile
        with self.SessionLocal() as session:
            row = IndexProfileRow(memory_id=memory_id)
            session.add(row)
            session.commit()

        return IndexProfile()

    def update_profile(
        self,
        memory_id: str,
        outcome: Literal["success", "failure", "not_used", "unknown"],
    ) -> IndexProfile:
        """Update index profile after memory usage.

        Args:
            memory_id: Memory identifier
            outcome: Usage outcome

        Returns:
            Updated IndexProfile
        """
        now = datetime.now(timezone.utc)

        with self.SessionLocal() as session:
            row = (
                session.query(IndexProfileRow)
                .filter(IndexProfileRow.memory_id == memory_id)
                .first()
            )

            if not row:
                # Create new profile
                new_row = IndexProfileRow(
                    memory_id=memory_id,
                    usage_count=1,
                    success_count=1 if outcome == "success" else 0,
                    failure_count=1 if outcome == "failure" else 0,
                    weight=1.1
                    if outcome == "success"
                    else (0.8 if outcome == "failure" else 1.0),
                    first_used_at=now,
                    last_used_at=now,
                    last_success_at=now if outcome == "success" else None,
                )
                session.add(new_row)
                session.commit()

                return IndexProfile(
                    usage_count=1,
                    success_count=1 if outcome == "success" else 0,
                    failure_count=1 if outcome == "failure" else 0,
                    weight=1.1
                    if outcome == "success"
                    else (0.8 if outcome == "failure" else 1.0),
                    created_at=now,
                    last_used_at=now,
                )
            else:
                # Extract current values with proper typing
                current_usage: int = row.usage_count or 0  # type: ignore[assignment]
                current_success: int = row.success_count or 0  # type: ignore[assignment]
                current_failure: int = row.failure_count or 0  # type: ignore[assignment]
                current_weight: float = row.weight or 1.0  # type: ignore[assignment]
                current_first: datetime | None = row.first_used_at  # type: ignore[assignment]

                # Calculate new values
                new_usage = current_usage + 1
                new_success = current_success + (1 if outcome == "success" else 0)
                new_failure = current_failure + (1 if outcome == "failure" else 0)

                if outcome == "success":
                    new_weight = min(10.0, current_weight + 0.1)
                elif outcome == "failure":
                    new_weight = max(0.0, current_weight - 0.2)
                else:
                    new_weight = current_weight

                # Update row using update() to avoid type issues
                update_data: dict[str, int | float | datetime | None] = {
                    "usage_count": new_usage,
                    "last_used_at": now,
                    "weight": new_weight,
                }

                if current_first is None:
                    update_data["first_used_at"] = now

                if outcome == "success":
                    update_data["success_count"] = new_success
                    update_data["last_success_at"] = now
                elif outcome == "failure":
                    update_data["failure_count"] = new_failure

                session.query(IndexProfileRow).filter(
                    IndexProfileRow.memory_id == memory_id
                ).update(update_data)  # type: ignore[arg-type]
                session.commit()

                # Use created_at from row or fallback to now
                profile_created_at: datetime = row.created_at or now  # type: ignore[assignment]

                return IndexProfile(
                    usage_count=new_usage,
                    success_count=new_success,
                    failure_count=new_failure,
                    weight=new_weight,
                    created_at=profile_created_at,
                    last_used_at=now,
                )

    # ========== Usage Record Methods ==========

    def record_usage(self, usage: UsageRecord) -> str:
        """Record a memory usage.

        Args:
            usage: UsageRecord to store

        Returns:
            Record ID
        """
        record_id = usage.id if usage.id else f"usage_{uuid.uuid4().hex[:12]}"

        with self.SessionLocal() as session:
            row = UsageRecordRow(
                record_id=record_id,
                memory_id=usage.memory_id,
                session_id=usage.session_id,
                subtask_id=usage.subtask_id,
                sequence_position=usage.sequence_position,
                query=usage.query,
                rank_position=usage.rank_position,
                outcome=usage.outcome,
                used_at=usage.used_at,
            )
            session.add(row)
            session.commit()

            logger.debug(
                "usage_recorded",
                record_id=record_id,
                memory_id=usage.memory_id,
                session_id=usage.session_id,
            )

        # Also update the index profile
        self.update_profile(usage.memory_id, usage.outcome)

        return record_id

    def _row_to_usage_record(self, row: UsageRecordRow) -> UsageRecord:
        """Convert UsageRecordRow to UsageRecord Pydantic model.

        Args:
            row: SQLAlchemy row object

        Returns:
            UsageRecord Pydantic model instance
        """
        # Extract row data with proper typing
        record_id: str = row.record_id  # type: ignore[assignment]
        memory_id: str = row.memory_id  # type: ignore[assignment]
        session_id: str = row.session_id  # type: ignore[assignment]
        subtask_id: str | None = row.subtask_id  # type: ignore[assignment]
        sequence_position: int = row.sequence_position or 0  # type: ignore[assignment]
        query: str = row.query  # type: ignore[assignment]
        rank_position: int = row.rank_position  # type: ignore[assignment]
        outcome_raw: str = row.outcome or "unknown"  # type: ignore[assignment]
        used_at: datetime = row.used_at  # type: ignore[assignment]

        # Validate outcome
        valid_outcomes = {"success", "failure", "not_used", "unknown"}
        outcome = outcome_raw if outcome_raw in valid_outcomes else "unknown"

        return UsageRecord(
            id=record_id,
            memory_id=memory_id,
            session_id=session_id,
            subtask_id=subtask_id,
            sequence_position=sequence_position,
            query=query,
            rank_position=rank_position,
            outcome=outcome,  # type: ignore[arg-type]
            used_at=used_at,
        )

    def _row_to_association(self, row: AssociationRow) -> Association:
        """Convert AssociationRow to Association Pydantic model.

        Args:
            row: SQLAlchemy row object

        Returns:
            Association Pydantic model instance
        """
        # Extract row data with proper typing
        source_id: str = row.source_id  # type: ignore[assignment]
        target_id: str = row.target_id  # type: ignore[assignment]
        relation_type: str = row.relation_type  # type: ignore[assignment]
        confidence: float = row.confidence  # type: ignore[assignment]
        support: int = row.support  # type: ignore[assignment]
        discovered_at: datetime = row.discovered_at  # type: ignore[assignment]

        return Association(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,  # type: ignore[arg-type]
            confidence=confidence,
            support=support,
            discovered_at=discovered_at,
        )

    def get_usage_history(self, memory_id: str, limit: int = 100) -> list[UsageRecord]:
        """Get usage history for a memory.

        Args:
            memory_id: Memory identifier
            limit: Maximum records to return

        Returns:
            List of UsageRecord objects
        """
        with self.SessionLocal() as session:
            rows = (
                session.query(UsageRecordRow)
                .filter(UsageRecordRow.memory_id == memory_id)
                .order_by(UsageRecordRow.used_at.desc())
                .limit(limit)
                .all()
            )

            return [self._row_to_usage_record(row) for row in rows]

    def get_session_usage(self, session_id: str) -> list[UsageRecord]:
        """Get all usage records for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of UsageRecord objects ordered by sequence
        """
        with self.SessionLocal() as session:
            rows = (
                session.query(UsageRecordRow)
                .filter(UsageRecordRow.session_id == session_id)
                .order_by(UsageRecordRow.sequence_position)
                .all()
            )

            return [self._row_to_usage_record(row) for row in rows]

    # ========== Association Methods ==========

    def add_association(self, association: Association) -> None:
        """Add or update a discovered association.

        Args:
            association: Association to store
        """
        with self.SessionLocal() as session:
            # Check for existing association
            existing = (
                session.query(AssociationRow)
                .filter(
                    AssociationRow.source_id == association.source_id,
                    AssociationRow.target_id == association.target_id,
                    AssociationRow.relation_type == association.relation_type,
                )
                .first()
            )

            if existing:
                # Update existing association using update()
                session.query(AssociationRow).filter(
                    AssociationRow.source_id == association.source_id,
                    AssociationRow.target_id == association.target_id,
                    AssociationRow.relation_type == association.relation_type,
                ).update(
                    {
                        "confidence": association.confidence,
                        "support": association.support,
                        "discovered_at": association.discovered_at,
                    }
                )
            else:
                # Add new association
                row = AssociationRow(
                    source_id=association.source_id,
                    target_id=association.target_id,
                    relation_type=association.relation_type,
                    confidence=association.confidence,
                    support=association.support,
                    discovered_at=association.discovered_at,
                )
                session.add(row)

            session.commit()

            logger.debug(
                "association_stored",
                source_id=association.source_id,
                target_id=association.target_id,
                relation_type=association.relation_type,
            )

    def get_associations(
        self,
        memory_id: str,
        relation_type: str | None = None,
    ) -> list[Association]:
        """Get associations for a memory.

        Args:
            memory_id: Memory identifier
            relation_type: Optional filter by relation type

        Returns:
            List of Association objects
        """
        with self.SessionLocal() as session:
            query = session.query(AssociationRow).filter(
                AssociationRow.source_id == memory_id
            )

            if relation_type:
                query = query.filter(AssociationRow.relation_type == relation_type)

            rows = query.order_by(AssociationRow.confidence.desc()).all()

            return [self._row_to_association(row) for row in rows]

    def get_complements(self, memory_id: str) -> list[str]:
        """Get complementary memory IDs.

        Args:
            memory_id: Memory identifier

        Returns:
            List of complementary memory IDs
        """
        associations = self.get_associations(memory_id, relation_type="COMPLEMENTS")
        return [a.target_id for a in associations]

    def get_causal_chain(self, memory_id: str, max_depth: int = 3) -> list[str]:
        """Get causal chain from a memory.

        Args:
            memory_id: Starting memory identifier
            max_depth: Maximum chain depth

        Returns:
            List of memory IDs in causal chain
        """
        chain = []
        current_id = memory_id

        for _ in range(max_depth):
            associations = self.get_associations(current_id, relation_type="CAUSES")
            if not associations:
                break

            # Follow the highest confidence causal link
            next_id = associations[0].target_id
            if next_id in chain:
                break  # Prevent cycles

            chain.append(next_id)
            current_id = next_id

        return chain

    # ========== Statistics Methods ==========

    def get_stats(self) -> dict[str, int]:
        """Get index store statistics.

        Returns:
            Statistics dictionary
        """
        with self.SessionLocal() as session:
            total_profiles = session.query(IndexProfileRow).count()
            total_usage = session.query(UsageRecordRow).count()
            total_associations = session.query(AssociationRow).count()

            return {
                "total_profiles": total_profiles,
                "total_usage_records": total_usage,
                "total_associations": total_associations,
            }

    def clear(self) -> dict[str, int]:
        """Clear all data (for testing).

        Returns:
            Counts of deleted records
        """
        with self.SessionLocal() as session:
            profiles = session.query(IndexProfileRow).delete()
            usage = session.query(UsageRecordRow).delete()
            associations = session.query(AssociationRow).delete()
            session.commit()

            return {
                "profiles_deleted": profiles,
                "usage_records_deleted": usage,
                "associations_deleted": associations,
            }
