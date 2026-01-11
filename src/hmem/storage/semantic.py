"""Semantic Store Protocol - Abstract interface for knowledge graph backends.

Defines the contract for semantic storage implementations (SQLite, Neo4j, etc.).
Follows the Strategy pattern to allow runtime backend selection.
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from hmem.models import Memory, SemanticTriple


@runtime_checkable
class SemanticStoreProtocol(Protocol):
    """Protocol defining the semantic store interface.

    All semantic store implementations (SQLite, Neo4j, etc.) must implement
    this protocol. This enables the factory pattern and coordinated retrieval
    across different backends.

    Graph Model:
        - Nodes: Entities (subject, object)
        - Edges: Relationships (predicate) with properties (weight, version)
        - Provenance: parent_ids linking to source memories

    Key Operations:
        - add_or_update: Insert/update triples with optimistic locking
        - search: Text-based search (LIKE or full-text index)
        - query_related: Multi-hop graph traversal
        - expand_neighbors: Get neighbors for graph expansion
    """

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
        """
        ...

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Search semantic facts by text matching or full-text index.

        Args:
            query: Query text
            limit: Maximum results

        Returns:
            List of relevant memories with provenance
        """
        ...

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
        ...

    def expand_neighbors(
        self,
        entities: list[str],
        max_depth: int = 1,
        limit_per_entity: int = 5,
    ) -> list[SemanticTriple]:
        """Expand neighborhood around given entities (for graph-based retrieval).

        Args:
            entities: List of seed entities to expand from
            max_depth: How many hops to expand
            limit_per_entity: Max neighbors per entity

        Returns:
            List of neighboring triples
        """
        ...

    def get_by_id(self, fact_id: str) -> SemanticTriple | None:
        """Get a triple by its ID."""
        ...

    def check_conflict(
        self, subject: str, predicate: str, new_object: str
    ) -> tuple[bool, list[SemanticTriple]]:
        """Check if a new triple conflicts with existing ones."""
        ...

    def resolve_conflict(
        self,
        subject: str,
        predicate: str,
        old_object: str,
        new_object: str,
        new_parent_ids: list[str] | None = None,
    ) -> int:
        """Resolve conflict by superseding old triple."""
        ...

    def update_weight(self, fact_id: str, delta: float = 0.1) -> bool:
        """Update weight of a fact (reconsolidation)."""
        ...

    def increment_access(self, fact_id: str) -> bool:
        """Increment access count."""
        ...

    def prune_low_weight(self, threshold: float = 0.3) -> int:
        """Remove low-weight facts (active forgetting)."""
        ...

    def apply_decay(self, decay_factor: float = 0.99, min_weight: float = 0.1) -> int:
        """Apply time-based decay to all weights."""
        ...

    def get_all_for_entity(self, entity: str) -> list[SemanticTriple]:
        """Get all facts for an entity."""
        ...

    def count(self) -> dict[str, int]:
        """Get count statistics."""
        ...

    def health_check(self) -> dict[str, Any]:
        """Get health status of the store."""
        ...

    def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        ...

    def clear(self) -> int:
        """Clear all facts (for testing)."""
        ...


class BaseSemanticStore(ABC):
    """Abstract base class for semantic stores.

    Provides common functionality and enforces the SemanticStoreProtocol.
    Concrete implementations: SQLiteSemanticStore, Neo4jSemanticStore.
    """

    MAX_QUERY_DEPTH: int = 3  # Hard limit for traversal depth

    @abstractmethod
    def add_or_update(
        self,
        triple: SemanticTriple,
        parent_ids: list[str] | None = None,
    ) -> tuple[bool, int]:
        """Add a new triple or update existing one with optimistic locking."""
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Search semantic facts by text matching."""
        pass

    @abstractmethod
    def query_related(
        self, entity: str, max_depth: int = 2
    ) -> list[tuple[str, str, str, float]]:
        """Query related entities up to max_depth hops."""
        pass

    @abstractmethod
    def expand_neighbors(
        self,
        entities: list[str],
        max_depth: int = 1,
        limit_per_entity: int = 5,
    ) -> list[SemanticTriple]:
        """Expand neighborhood around given entities."""
        pass

    @abstractmethod
    def get_by_id(self, fact_id: str) -> SemanticTriple | None:
        """Get a triple by its ID."""
        pass

    @abstractmethod
    def check_conflict(
        self, subject: str, predicate: str, new_object: str
    ) -> tuple[bool, list[SemanticTriple]]:
        """Check if a new triple conflicts with existing ones."""
        pass

    @abstractmethod
    def resolve_conflict(
        self,
        subject: str,
        predicate: str,
        old_object: str,
        new_object: str,
        new_parent_ids: list[str] | None = None,
    ) -> int:
        """Resolve conflict by superseding old triple."""
        pass

    @abstractmethod
    def update_weight(self, fact_id: str, delta: float = 0.1) -> bool:
        """Update weight of a fact."""
        pass

    @abstractmethod
    def increment_access(self, fact_id: str) -> bool:
        """Increment access count."""
        pass

    @abstractmethod
    def prune_low_weight(self, threshold: float = 0.3) -> int:
        """Remove low-weight facts."""
        pass

    @abstractmethod
    def apply_decay(self, decay_factor: float = 0.99, min_weight: float = 0.1) -> int:
        """Apply time-based decay."""
        pass

    @abstractmethod
    def get_all_for_entity(self, entity: str) -> list[SemanticTriple]:
        """Get all facts for an entity."""
        pass

    @abstractmethod
    def count(self) -> dict[str, int]:
        """Get count statistics."""
        pass

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Get health status."""
        pass

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        pass

    @abstractmethod
    def clear(self) -> int:
        """Clear all facts."""
        pass
