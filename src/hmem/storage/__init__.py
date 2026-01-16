"""Layer 3: Long-Term Memory Storage.

Hybrid database architecture with lightweight embedded solutions.
Supports multiple backends via factory pattern.

Architecture:
    Event Log (source of truth)
        │
        ├─→ ChromaDB (episodic, vectors)
        ├─→ Neo4j (semantic, graph)
        └─→ SQLite (skills, k-v)
"""

from typing import Literal

from hmem.storage.chroma_episodic import ChromaEpisodicStore
from hmem.storage.semantic import BaseSemanticStore, SemanticStoreProtocol
from hmem.storage.skill import SkillStore


def create_semantic_store(
    backend: Literal["neo4j"] = "neo4j",
    **kwargs,
) -> SemanticStoreProtocol:
    """Factory function to create semantic store instances.

    Args:
        backend: Backend type (only "neo4j" supported)
        **kwargs: Backend-specific configuration

    Returns:
        SemanticStoreProtocol implementation
    """
    if backend == "neo4j":
        from hmem.storage.neo4j_semantic import Neo4jSemanticStore

        return Neo4jSemanticStore(
            uri=kwargs.get("uri", "bolt://localhost:7687"),
            username=kwargs.get("username", "neo4j"),
            password=kwargs.get("password", "password"),
            database=kwargs.get("database", "neo4j"),
        )
    raise ValueError(f"Unsupported semantic backend: {backend}")


__all__ = [
    "ChromaEpisodicStore",
    "SkillStore",
    "BaseSemanticStore",
    "SemanticStoreProtocol",
    "create_semantic_store",
]
