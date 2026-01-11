"""Layer 3: Long-Term Memory Storage.

Hybrid database architecture with lightweight embedded solutions.
Supports multiple backends via factory pattern.

Architecture:
    Event Log (source of truth)
        │
        ├─→ ChromaDB (episodic, vectors)
        ├─→ Neo4j/SQLite (semantic, graph)
        └─→ SQLite (skills, k-v)
"""

from typing import Literal

from hmem.storage.base import BaseStore
from hmem.storage.episodic import EpisodicStore
from hmem.storage.semantic import BaseSemanticStore, SemanticStoreProtocol
from hmem.storage.skill import SkillStore


def create_semantic_store(
    backend: Literal["neo4j"] = "neo4j",
    **kwargs,
) -> SemanticStoreProtocol:
    """Factory function to create semantic store instances.

    Enables runtime backend selection based on configuration.

    Args:
        backend: Backend type (only "neo4j" supported)
        **kwargs: Backend-specific configuration:
            Neo4j:
                - uri: Neo4j bolt URI
                - username: Neo4j username
                - password: Neo4j password
                - database: Database name

    Returns:
        SemanticStoreProtocol implementation

    Raises:
        ValueError: If backend is not supported

    Example:
        >>> # Neo4j backend
        >>> store = create_semantic_store(
        ...     "neo4j",
        ...     uri="bolt://localhost:7687",
        ...     username="neo4j",
        ...     password="password",
        ... )
    """
    if backend == "neo4j":
        from hmem.storage.neo4j_semantic import Neo4jSemanticStore

        return Neo4jSemanticStore(
            uri=kwargs.get("uri", "bolt://localhost:7687"),
            username=kwargs.get("username", "neo4j"),
            password=kwargs.get("password", "password"),
            database=kwargs.get("database", "neo4j"),
        )

    else:
        raise ValueError(f"Unsupported semantic backend: {backend}")


__all__ = [
    "BaseStore",
    "EpisodicStore",
    "SkillStore",
    "BaseSemanticStore",
    "SemanticStoreProtocol",
    "create_semantic_store",
]
