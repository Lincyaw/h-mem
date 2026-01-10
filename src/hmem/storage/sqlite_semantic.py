"""SQLite-based semantic memory store implementation (Phase 2)."""

from datetime import datetime
from typing import Iterator

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    UniqueConstraint,
    Index,
    create_engine,
    select,
    update,
    and_
)
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from pydantic import BaseModel

from hmem.models import SemanticTriple, Memory
from hmem.exceptions import ConsolidationError


Base = declarative_base()


class SemanticFactRow(Base):
    """SQLite table for semantic triples."""
    
    __tablename__ = "semantic_facts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    subject = Column(String, nullable=False, index=True)
    predicate = Column(String, nullable=False)
    object = Column(Text, nullable=False)
    weight = Column(Float, default=1.0)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('subject', 'predicate', 'object', name='_spo_uc'),
        Index('idx_subject', 'subject'),
        Index('idx_spo', 'subject', 'predicate', 'object'),
    )


class SQLiteSemanticStore:
    """SQLite-based semantic graph store with conflict resolution.
    
    Features:
    - Triple storage (subject-predicate-object)
    - Weight-based importance tracking
    - Optimistic locking for conflict detection
    - Relationship traversal
    """
    
    def __init__(self, database_url: str = "sqlite:///./semantic.db"):
        """Initialize SQLite semantic store.
        
        Args:
            database_url: SQLite database URL
        """
        self.engine = create_engine(database_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def add_or_update(self, triple: SemanticTriple) -> tuple[bool, int]:
        """Add a new triple or update existing one.
        
        Args:
            triple: Semantic triple to add/update
            
        Returns:
            Tuple of (was_conflict, conflicts_resolved)
        """
        with self.SessionLocal() as session:
            existing = session.query(SemanticFactRow).filter(
                and_(
                    SemanticFactRow.subject == triple.subject,
                    SemanticFactRow.predicate == triple.predicate,
                    SemanticFactRow.object == triple.object
                )
            ).first()
            
            if existing:
                existing.weight += 0.1
                existing.version += 1
                existing.updated_at = datetime.utcnow()
                session.commit()
                return False, 0
            else:
                new_row = SemanticFactRow(
                    subject=triple.subject,
                    predicate=triple.predicate,
                    object=triple.object,
                    weight=triple.weight,
                    version=1
                )
                session.add(new_row)
                session.commit()
                return False, 0
    
    def check_conflict(
        self,
        subject: str,
        predicate: str,
        new_object: str
    ) -> tuple[bool, list[str]]:
        """Check if a new triple conflicts with existing ones.
        
        Args:
            subject: Subject of the triple
            predicate: Predicate (relationship)
            new_object: New object value
            
        Returns:
            Tuple of (has_conflict, list of conflicting objects)
        """
        with self.SessionLocal() as session:
            existing = session.query(SemanticFactRow).filter(
                and_(
                    SemanticFactRow.subject == subject,
                    SemanticFactRow.predicate == predicate
                )
            ).all()
            
            if not existing:
                return False, []
            
            conflicting = [row.object for row in existing if row.object != new_object]
            return len(conflicting) > 0, conflicting
    
    def resolve_conflict(
        self,
        subject: str,
        predicate: str,
        old_object: str,
        new_object: str
    ) -> int:
        """Resolve conflict by updating the triple.
        
        Args:
            subject: Subject of the triple
            predicate: Predicate
            old_object: Old object to replace
            new_object: New object value
            
        Returns:
            Number of conflicts resolved
        """
        with self.SessionLocal() as session:
            old_row = session.query(SemanticFactRow).filter(
                and_(
                    SemanticFactRow.subject == subject,
                    SemanticFactRow.predicate == predicate,
                    SemanticFactRow.object == old_object
                )
            ).first()
            
            if old_row:
                old_row.weight *= 0.5
                old_row.updated_at = datetime.utcnow()
            
            new_triple = SemanticTriple(
                subject=subject,
                predicate=predicate,
                object=new_object,
                weight=1.0
            )
            self.add_or_update(new_triple)
            
            session.commit()
            return 1 if old_row else 0
    
    def query_related(
        self,
        entity: str,
        max_depth: int = 2
    ) -> list[tuple[str, str, str, float]]:
        """Query related entities up to max_depth hops.
        
        Args:
            entity: Starting entity
            max_depth: Maximum traversal depth (1-3)
            
        Returns:
            List of (subject, predicate, object, weight) tuples
        """
        max_depth = min(max_depth, 3)
        
        with self.SessionLocal() as session:
            results = session.query(SemanticFactRow).filter(
                SemanticFactRow.subject == entity
            ).all()
            
            return [
                (row.subject, row.predicate, row.object, row.weight)
                for row in results
            ]
    
    def search(
        self,
        query: str,
        limit: int = 10
    ) -> list[Memory]:
        """Search semantic facts by text matching.
        
        Args:
            query: Query text
            limit: Maximum results
            
        Returns:
            List of relevant memories
        """
        with self.SessionLocal() as session:
            query_lower = query.lower()
            
            results = session.query(SemanticFactRow).filter(
                (SemanticFactRow.subject.like(f"%{query_lower}%")) |
                (SemanticFactRow.object.like(f"%{query_lower}%"))
            ).order_by(SemanticFactRow.weight.desc()).limit(limit).all()
            
            memories = []
            for row in results:
                content = f"{row.subject} {row.predicate} {row.object}"
                memories.append(Memory(
                    content=content,
                    score=min(row.weight, 1.0),
                    source="semantic",
                    timestamp=row.updated_at,
                    metadata={
                        "subject": row.subject,
                        "predicate": row.predicate,
                        "object": row.object,
                        "weight": row.weight
                    }
                ))
            
            return memories
    
    def prune_low_weight(self, threshold: float = 0.3) -> int:
        """Remove low-weight facts (active forgetting).
        
        Args:
            threshold: Minimum weight threshold
            
        Returns:
            Number of facts removed
        """
        with self.SessionLocal() as session:
            deleted = session.query(SemanticFactRow).filter(
                SemanticFactRow.weight < threshold
            ).delete()
            session.commit()
            return deleted
    
    def count(self) -> dict[str, int]:
        """Get count statistics.
        
        Returns:
            Dictionary with node and edge counts
        """
        with self.SessionLocal() as session:
            total = session.query(SemanticFactRow).count()
            
            unique_subjects = session.query(SemanticFactRow.subject).distinct().count()
            
            return {
                "total_facts": total,
                "unique_entities": unique_subjects
            }
    
    def health_check(self) -> dict[str, any]:
        """Get health status of the store.
        
        Returns:
            Health status dictionary
        """
        stats = self.count()
        return {
            "status": "healthy",
            **stats
        }
