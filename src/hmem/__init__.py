"""
h-mem: Cognitive Agent Memory System (CAMS)

A memory system for AI agents inspired by cognitive neuroscience.

Architecture:
    Layer 1 (Perception): Context Manager, Sensory Buffer
    Layer 2 (Hippocampus): Encoder, Consolidator, Reflector, Retrieval Engine
    Layer 3 (Storage): Episodic, Semantic, Skill stores

Design Philosophy:
    - Unix Rule of Silence: Complexity hidden in config
    - Event Sourcing: Single source of truth
    - Pluggable Strategies: Easy migration paths
"""

from hmem.core import MemorySystem
from hmem.exceptions import (
    ConsolidationError,
    MemoryError,
    ReflectionError,
    RetrievalError,
)
from hmem.models import ConsolidationResult, Event, Memory, Principle, Skill

__version__ = "0.1.0"

__all__ = [
    # Core Interface (Unix philosophy: minimal public API)
    "MemorySystem",
    # Data Models
    "Memory",
    "Event",
    "ConsolidationResult",
    "Principle",
    "Skill",
    # Exceptions
    "MemoryError",
    "RetrievalError",
    "ConsolidationError",
    "ReflectionError",
]
