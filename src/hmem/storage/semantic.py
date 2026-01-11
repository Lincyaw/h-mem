"""Semantic Store Protocol - Abstract interface for knowledge graph backends.

Defines the contract for semantic storage implementations (Neo4j, etc.).
Follows the Strategy pattern to allow runtime backend selection.
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from hmem.models import Memory, SemanticTriple


@runtime_checkable
class SemanticStoreProtocol(Protocol):
    """Protocol defining the semantic store interface.

    All semantic store implementations must implement this protocol.
    This enables the factory pattern and coordinated retrieval.

    Graph Model:
        - Nodes: Entities (subject, object)
        - Edges: Relationships (predicate) with properties (weight, version)
        - Provenance: parent_ids linking to source memories

    Key Operations:
        - add_or_update: Insert/update triples with optimistic locking
        - search: Text-based search (LIKE or full-text index)
        - check_conflict/resolve_conflict: Handle semantic conflicts
        - update_weight: Reconsolidation mechanism
        - prune_low_weight/apply_decay: Active forgetting
    """

    def add_or_update(
        self,
        triple: SemanticTriple,
        parent_ids: list[str] | None = None,
    ) -> tuple[bool, int]:
        """Add a new triple or update existing one with optimistic locking."""
        ...

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Search semantic facts by text matching or full-text index."""
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

    def get_weight(self, fact_id: str) -> float | None:
        """Get current weight of a fact."""
        ...

    def prune_low_weight(self, threshold: float = 0.3) -> int:
        """Remove low-weight facts (active forgetting)."""
        ...

    def apply_decay(self, decay_factor: float = 0.99, min_weight: float = 0.1) -> int:
        """Apply time-based decay to all weights."""
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
    Concrete implementations: Neo4jSemanticStore.
    """

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
    def get_weight(self, fact_id: str) -> float | None:
        """Get current weight of a fact."""
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
    def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        pass

    @abstractmethod
    def clear(self) -> int:
        """Clear all facts."""
        pass
