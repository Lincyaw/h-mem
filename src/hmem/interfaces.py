from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Iterator

from .models import (
    Conversation,
    ConsolidationResult,
    Memory,
    Message,
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

    Updated API Design:
    - Inputs are conversation records (Message/Conversation objects)
    - remember() internalizes conversation into memory system
    - recall() searches and returns Memory objects
    """

    @abstractmethod
    def remember(
        self,
        conversation: Conversation | list[Message],
    ) -> str:
        """
        Store conversation into memory system (single write interface).

        This method accepts a conversation record and internalizes it into the memory system.
        The conversation is processed through:
        1. Sensory buffer (immediate storage)
        2. Event encoding (extracting events and facts)
        3. Async consolidation (non-blocking, runs in background)
        4. Async feedback extraction (LLM-based, if used_memory_ids present)

        Args:
            conversation: Either a Conversation object or list of Message objects.
                         If list provided, a session_id will be auto-generated.

        Returns:
            session_id: Unique identifier for this conversation session

        Raises:
            MemoryError: Raised when storage fails

        Example:
            >>> from hmem.models import Message, Conversation
            >>> memory = MemorySystem()
            >>>
            >>> # Option 1: Using Conversation object
            >>> conv = Conversation(
            ...     session_id="session_123",
            ...     messages=[
            ...         Message(role="user", content="My name is Alice"),
            ...         Message(role="assistant", content="Nice to meet you, Alice!"),
            ...     ]
            ... )
            >>> session_id = memory.remember(conv)
            >>>
            >>> # Option 2: Using list of messages
            >>> messages = [
            ...     Message(role="user", content="I want to learn Python"),
            ...     Message(role="assistant", content="Great choice!"),
            ... ]
            >>> session_id = memory.remember(messages)

        Note:
            - All consolidation runs asynchronously (non-blocking)
            - Feedback signals are extracted via LLM from conversation.metadata["used_memory_ids"]
            - Automatically triggers conflict detection and memory reconsolidation
        """
        pass

    @abstractmethod
    def recall(
        self,
        query: str | Message | Conversation,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> Iterator[Memory]:
        """
        Retrieve relevant memories (single read interface).

        Searches existing memories and returns relevant content.
        Accepts string, Message, or Conversation for flexible querying.

        Args:
            query: Search query with multiple formats:
                  - str: Simple text query for single search
                  - Message: Single message with role/metadata for context
                  - Conversation: Full conversation for proactive prompting
                    (uses conversation context to find relevant memories)
            limit: Maximum number of results to return (1-100)
            filters: Optional filter conditions:
                    - session_id: Filter by specific session
                    - source: Filter by memory type (episodic/semantic/skill)
                    - time_range: Filter by time period
                    - tags: Filter by tags
                    - min_score: Minimum relevance threshold

        Yields:
            Memory: Memories sorted by relevance score

        Raises:
            RetrievalError: Raised when retrieval fails

        Example:
            >>> # Simple string query (single search)
            >>> for memory in memory.recall("user preferences", limit=5):
            ...     print(f"{memory.content} (score: {memory.score})")
            >>>
            >>> # Context-aware query with Message
            >>> query_msg = Message(role="user", content="What do I like?")
            >>> results = list(memory.recall(query_msg, limit=10))
            >>>
            >>> # Proactive prompting with Conversation
            >>> conversation = Conversation(
            ...     session_id="s1",
            ...     messages=[
            ...         Message(role="user", content="I'm working on web scraping"),
            ...         Message(role="assistant", content="Great! What site?"),
            ...     ]
            ... )
            >>> results = list(memory.recall(conversation, limit=10))
            >>>
            >>> # Filtered query
            >>> results = list(memory.recall(
            ...     "web scraping",
            ...     filters={"source": "episodic", "session_id": "s1"}
            ... ))

        Note:
            - Returns iterator for progressive processing
            - Phase 1: Fast cache query
            - Phase 2: Deep vector + graph query
            - Automatically triggers memory reconsolidation (weight update)
            - When Conversation is provided, uses full context for retrieval
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

    def reflect(self) -> list[Principle]:
        """
        Manually trigger deep reflection (advanced users).

        Args:
            topic: Optional reflection topic (e.g., "debugging", "data_analysis").
                   If None, reflects on all topics using semantic clustering.

        Returns:
            list[Principle]: List of extracted principles
        """
        raise NotImplementedError("Reflection is automatic by default")

    def explain_recall(self, query: str) -> dict[str, Any]:
        """
        Explain retrieval process (diagnostic tool).

        Args:
            query: Query to analyze

        Returns:
            dict: Contains retrieval path, scores, cache hits, etc.
        """
        raise NotImplementedError("Diagnostic feature - Phase 3")

    def health_check(self) -> dict[str, Any]:
        """
        System health check.

        Returns:
            dict: Contains database status, index health, memory usage, etc.
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

# Note: FoldingStrategy is defined in hmem.perception.strategies.folding
# Import from there for consistency:
#   from hmem.perception.strategies.folding import FoldingStrategy


class RetrievalRanker(ABC):
    """Retrieval result ranking strategy [Stable - Pluggable]."""

    @abstractmethod
    def rank(self, candidates: list[Memory], query: str) -> list[Memory]:
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
        relation: str | None = None,
        max_depth: int = 2,
    ) -> list[SemanticTriple]:
        """
        Query related entities.

        Args:
            entity: Starting entity
            relation: Relation type (None means all relations)
            max_depth: Maximum query depth

        Returns:
            list[SemanticTriple]: List of related triples
        """
        pass

    @abstractmethod
    def detect_conflict(self, triple: SemanticTriple) -> SemanticTriple | None:
        """
        Detect conflicting triple.

        Args:
            triple: Triple to check

        Returns:
            SemanticTriple | None: Conflicting triple if exists
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
        metadata: dict[str, Any] | None = None,
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
    def match_skill(self, query: str) -> dict[str, Any] | None:
        """
        Match skill template.

        Args:
            query: Query text

        Returns:
            dict | None: Matched skill information
        """
        pass
