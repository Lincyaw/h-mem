from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from .models import (
    ConsolidationResult,
    Event,
    Memory,
    Principle,
    ReflectionContext,
    SemanticTriple,
)

# ============ Core System Interfaces ============


class MemorySystem(ABC):
    """Core interface for cognitive memory system [Core - Stable Interface].

    Follows Unix philosophy: simple interface, sophisticated implementation.
    Users only need to understand two core operations: remember and recall.
    All intelligent decisions (consolidation, reflection, fallback) are internal strategies.
    """

    @abstractmethod
    def remember(
        self,
        content: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Store new memory (single write interface).

        Args:
            content: Memory content (conversation, event, observation)
            context: Optional context information (time, location, mood, etc.)
            session_id: Session identifier for associating related memories

        Returns:
            memory_id: Unique identifier for the memory

        Raises:
            MemoryError: Raised when storage fails

        Example:
            >>> memory = MemorySystem()
            >>> memory_id = memory.remember(
            ...     "User prefers dark mode",
            ...     context={"importance": "high"},
            ...     session_id="session_123"
            ... )

        Note:
            - Default async mode: returns immediately, consolidation runs async
            - Can be configured for sync consolidation (Phase 1)
            - Automatically triggers conflict detection and memory reconsolidation
        """
        pass

    @abstractmethod
    def recall(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Memory]:
        """
        Retrieve relevant memories (single read interface).

        Args:
            query: Query content (natural language)
            limit: Maximum number of results to return
            filters: Optional filter conditions (time range, source, tags, etc.)

        Yields:
            Memory: Memories sorted by relevance

        Raises:
            RetrievalError: Raised when retrieval fails

        Example:
            >>> for memory in memory.recall("user preferences", limit=5):
            ...     print(f"{memory.content} (score: {memory.score})")

        Note:
            - Returns iterator for progressive processing
            - Phase 1: Fast cache query
            - Phase 2: Deep vector + graph query
            - Automatically triggers memory reconsolidation (weight update)
        """
        pass

    # ============ Auxiliary Interfaces (Optional) ============

    def consolidate(self, session_id: str) -> ConsolidationResult:
        """
        Manually trigger memory consolidation (advanced users).

        Args:
            session_id: Session ID to consolidate

        Returns:
            ConsolidationResult: Consolidation statistics
        """
        raise NotImplementedError("Consolidation is automatic by default")

    def reflect(self, topic: str) -> List[Principle]:
        """
        Manually trigger deep reflection (advanced users).

        Args:
            topic: Reflection topic (e.g., "debugging", "data_analysis")

        Returns:
            List[Principle]: List of extracted principles
        """
        raise NotImplementedError("Reflection is automatic by default")

    def explain_recall(self, query: str) -> Dict[str, Any]:
        """
        Explain retrieval process (diagnostic tool).

        Args:
            query: Query to analyze

        Returns:
            Dict: Contains retrieval path, scores, cache hits, etc.
        """
        raise NotImplementedError("Diagnostic feature - Phase 3")

    def health_check(self) -> Dict[str, Any]:
        """
        System health check.

        Returns:
            Dict: Contains database status, index health, memory usage, etc.
        """
        raise NotImplementedError("Diagnostic feature - Phase 3")

    @classmethod
    def from_config(cls, config_path: str) -> "MemorySystem":
        """
        Create system instance from configuration file.

        Args:
            config_path: Path to configuration file (YAML/JSON)

        Returns:
            MemorySystem: Configured system instance
        """
        raise NotImplementedError("To be implemented in concrete class")


# ============ Strategy Interfaces ============


class FoldingStrategy(ABC):
    """Abstract base class for memory folding strategy."""

    @abstractmethod
    def should_fold(
        self, messages: List[Dict[str, Any]], token_count: int, limit: int
    ) -> bool:
        """Determine if folding is needed."""
        pass

    @abstractmethod
    def compress(self, messages: List[Dict[str, Any]]) -> str:
        """Execute compression and return summary text."""
        pass


class RetrievalRanker(ABC):
    """Retrieval result ranking strategy [Stable - Pluggable]."""

    @abstractmethod
    def rank(self, candidates: List[Memory], query: str) -> List[Memory]:
        """Rank candidate memories."""
        pass


class ReflectionPolicy(ABC):
    """Reflection trigger policy - Multi-timescale adaptive."""

    @abstractmethod
    def should_trigger(self, topic: str, context: ReflectionContext) -> bool:
        """Determine if reflection should be triggered."""
        pass


class LockProvider(ABC):
    """Lock abstraction layer - Supports smooth migration from single-node to distributed."""

    @abstractmethod
    @contextmanager
    def acquire(self, key: str, timeout: float) -> Iterator[None]:
        """
        Acquire lock, raises LockTimeoutError on timeout.

        Args:
            key: Unique identifier for the lock
            timeout: Timeout in seconds

        Yields:
            None: While lock is held

        Raises:
            LockTimeoutError: Lock acquisition timeout
        """
        pass


# ============ Storage Layer Interfaces ============


class EpisodicStore(ABC):
    """Episodic memory storage interface."""

    @abstractmethod
    def add(
        self,
        events: List[Event],
        embeddings: Optional[List[List[float]]] = None,
    ) -> List[str]:
        """
        Add events to episodic memory.

        Args:
            events: List of events
            embeddings: Optional pre-computed vectors (auto-generated if None)

        Returns:
            List[str]: List of event IDs
        """
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Memory]:
        """
        Vector similarity search.

        Args:
            query: Query text
            limit: Number of results to return
            filters: Metadata filter conditions

        Returns:
            List[Memory]: List of matching memories
        """
        pass


class SemanticStore(ABC):
    """Semantic memory storage interface (knowledge graph)."""

    @abstractmethod
    def add_triple(self, triple: SemanticTriple) -> str:
        """
        Add or update triple.

        Args:
            triple: Semantic triple

        Returns:
            str: Triple ID
        """
        pass

    @abstractmethod
    def query_related(
        self,
        entity: str,
        relation: Optional[str] = None,
        max_depth: int = 2,
    ) -> List[SemanticTriple]:
        """
        Query related entities.

        Args:
            entity: Starting entity
            relation: Relation type (None means all relations)
            max_depth: Maximum query depth

        Returns:
            List[SemanticTriple]: List of related triples
        """
        pass

    @abstractmethod
    def detect_conflict(self, triple: SemanticTriple) -> Optional[SemanticTriple]:
        """
        Detect conflicting triple.

        Args:
            triple: Triple to check

        Returns:
            Optional[SemanticTriple]: Conflicting triple if exists
        """
        pass


class SkillStore(ABC):
    """Procedural memory storage interface (skill templates)."""

    @abstractmethod
    def add_skill(
        self,
        name: str,
        trigger_pattern: str,
        code_template: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add skill template.

        Args:
            name: Skill name
            trigger_pattern: Trigger pattern (regex)
            code_template: Code template
            metadata: Metadata

        Returns:
            str: Skill ID
        """
        pass

    @abstractmethod
    def match_skill(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Match skill template.

        Args:
            query: Query text

        Returns:
            Optional[Dict]: Matched skill information
        """
        pass
