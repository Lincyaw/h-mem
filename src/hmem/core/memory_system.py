"""Main MemorySystem class - the unified interface for cognitive memory.

This is the primary entry point following Unix philosophy: "Do One Thing Well"
Provides only 2 core methods: remember() and recall()
"""

from collections.abc import Iterator

from hmem.config import MemoryConfig
from hmem.models import Memory


class MemorySystem:
    """Cognitive Agent Memory System (CAMS) - Core Interface.

    This class orchestrates all three layers:
    - Layer 1: Perception & Working Memory (Context Manager)
    - Layer 2: Hippocampus Processing (Encoder, Consolidator, Reflector)
    - Layer 3: Long-Term Storage (Episodic, Semantic, Skill)

    Design Philosophy:
    - Unix Rule of Silence: All complexity hidden in config
    - Unix Rule of Modularity: Internal components replaceable via protocols
    - Event Sourcing: Single source of truth (append-only event log)

    Example:
        >>> memory = MemorySystem()  # Zero config for beginners
        >>> memory.remember("Alice likes dark mode", session_id="sess_001")
        >>> results = list(memory.recall("user preferences"))
    """

    def __init__(self, config: MemoryConfig | None = None) -> None:
        """Initialize memory system with optional config.

        Args:
            config: Configuration object. If None, loads from default path.
        """
        self.config = config or MemoryConfig.from_file()
        self._initialized = False

    @classmethod
    def from_config(cls, config_path: str) -> "MemorySystem":
        """Create instance from config file.

        Args:
            config_path: Path to YAML config file

        Returns:
            Configured MemorySystem instance
        """
        config = MemoryConfig.from_file(config_path)
        return cls(config)

    def remember(
        self,
        content: str,
        session_id: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Store new memory (single write interface).

        This triggers:
        1. Append to Event Log (single source of truth)
        2. Async projection to vector/graph stores

        Args:
            content: Raw content to remember
            session_id: Session identifier for grouping
            metadata: Optional metadata (e.g., user_id, tags)

        Raises:
            MemoryError: If event log write fails
        """
        raise NotImplementedError("Phase 1 implementation pending")

    def recall(
        self,
        query: str,
        limit: int = 10,
        filters: dict[str, str] | None = None,
    ) -> Iterator[Memory]:
        """Retrieve relevant memories (single read interface).

        Two-phase retrieval:
        - Phase 1 (sync): Cache + Bloom Filter (P95 < 50ms)
        - Phase 2 (async): Vector + Graph search (P95 < 500ms)

        Args:
            query: Search query
            limit: Maximum results to return
            filters: Optional filters (e.g., session_id, date_range)

        Yields:
            Memory objects ranked by relevance

        Raises:
            RetrievalError: If retrieval fails
        """
        raise NotImplementedError("Phase 1 implementation pending")

    def consolidate(self, session_id: str) -> dict[str, int]:
        """Trigger memory consolidation (cold path).

        This is called:
        - Synchronously at session end (Phase 1)
        - Asynchronously by scheduler (Phase 3)

        Args:
            session_id: Session to consolidate

        Returns:
            Statistics: {"events_processed": N, "facts_extracted": M, ...}

        Raises:
            ConsolidationError: If consolidation fails
        """
        raise NotImplementedError("Phase 1 implementation pending")

    def health(self) -> dict[str, str | int]:
        """Get system health status.

        Returns:
            Health metrics: status, memory_count, latency_p95, etc.
        """
        return {
            "status": "healthy",
            "version": "0.1.0",
            "episodic_count": 0,
            "semantic_count": 0,
        }

    def explain_recall(self, query: str) -> dict[str, str | float]:
        """Explain how a query would be processed (observability).

        Args:
            query: Query to explain

        Returns:
            Explanation with threshold, cache status, estimated latency
        """
        raise NotImplementedError("Phase 3 implementation")
