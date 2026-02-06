"""
h-mem: Cognitive Agent Memory System (CAMS)

A memory system for AI agents inspired by cognitive neuroscience.

Architecture (Unified Neo4j):
    (:Conversation) -[:GENERATES]-> (:Fact)
    (:Conversation) -[:GENERATES]-> (:Process)
    (:Entity) -[:HAS_ATTRIBUTE]-> (:Fact)
    (:Process) -[:INSTANCE_OF]-> (:Skill)
    (:Process) -[:INVOLVES]-> (:Fact)
    (:Fact) -[:SUPPORTS]-> (:Principle)
    (:Skill) -[:GUIDED_BY]-> (:Principle)

    + Vector Index (Neo4j 5.11+) for semantic search
    + Complete provenance chain from any memory to source conversation
    + Unified evolution via Q-value on all node types

Design Philosophy:
    - Unix Rule of Silence: Complexity hidden in config
    - Complete Provenance: All derived knowledge traceable to source conversations
    - Unified Storage: Single Neo4j backend for all memory types
"""

from hmem.core import MemorySystem
from hmem.exceptions import (
    ConsolidationError,
    MemoryError,
    ReflectionError,
    RetrievalError,
)
from hmem.models import (
    Conversation,
    ConsolidationResult,
    Memory,
    Principle,
    Skill,
    Entity,
    Process,
)

__version__ = "0.2.0"

__all__ = [
    # Core Interface
    "MemorySystem",
    # Data Models
    "Memory",
    "Conversation",
    "ConsolidationResult",
    "Principle",
    "Skill",
    "Entity",
    "Process",
    # Exceptions
    "MemoryError",
    "RetrievalError",
    "ConsolidationError",
    "ReflectionError",
]
