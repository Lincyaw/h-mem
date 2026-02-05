"""Layer 3: Long-Term Memory Storage.

Unified Neo4j architecture with complete provenance chain.

Architecture:
    (:Conversation) -[:HAS_EVENT]-> (:Event)
    (:Event) -[:GENERATES]-> (:Fact)
    (:Event) -[:INDUCES]-> (:Principle)
    (:Event) -[:INDUCES]-> (:Skill)

    + Vector Index (Neo4j 5.11+) for semantic search
    + Full provenance chain from any memory to source conversation
    + Unified evolution via Q-value on all node types
"""

from hmem.storage.neo4j_unified import Neo4jUnifiedStore

__all__ = [
    "Neo4jUnifiedStore",
]
