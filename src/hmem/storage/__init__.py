"""Layer 3: Long-Term Memory Storage.

Unified Neo4j architecture with complete provenance chain.

Architecture:
    (:Conversation) -[:GENERATES]-> (:Fact)
    (:Conversation) -[:GENERATES]-> (:Process)
    (:Entity) -[:HAS_ATTRIBUTE]-> (:Fact)
    (:Process) -[:INSTANCE_OF]-> (:Skill)
    (:Process) -[:INVOLVES]-> (:Fact)
    (:Fact) -[:SUPPORTS]-> (:Principle)
    (:Skill) -[:GUIDED_BY]-> (:Principle)

    + Vector Index (Neo4j 5.11+) for semantic search
    + Full provenance chain from any memory to source conversation
    + Unified evolution via Q-value on all node types
"""

from hmem.storage.neo4j_unified import Neo4jUnifiedStore

__all__ = [
    "Neo4jUnifiedStore",
]
