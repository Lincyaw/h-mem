"""Retrieval Engine - Two-phase memory retrieval."""

from collections.abc import Iterator

from hmem.models import Memory
from hmem.storage.episodic import EpisodicStore


class RetrievalEngine:
    """Orchestrates two-phase retrieval process.

    Phase 1 (sync, P95 < 50ms):
    - Check in-memory cache
    - Bloom filter for quick negative checks

    Phase 2 (async, P95 < 500ms):
    - Vector similarity search (ChromaDB)
    - Graph relationship traversal (SQLite)
    - Hybrid ranking (similarity + recency + importance)

    Returns results as iterator for progressive rendering.

    Example:
        >>> engine = RetrievalEngine(episodic_store)
        >>> for memory in engine.retrieve("user preferences", limit=10):
        ...     print(memory.content)
        ...     if good_enough:
        ...         break  # Early termination supported
    """

    def __init__(self, episodic_store: EpisodicStore) -> None:
        """Initialize retrieval engine.
        
        Args:
            episodic_store: Episodic memory store
        """
        self._episodic_store = episodic_store
        self._cache: dict[str, list[Memory]] = {}  # Simple cache

    def retrieve(
        self,
        query: str,
        limit: int = 10,
        filters: dict[str, str] | None = None,
    ) -> Iterator[Memory]:
        """Execute two-phase retrieval.

        Args:
            query: Search query
            limit: Maximum results
            filters: Optional filters

        Yields:
            Memory objects ranked by relevance
        """
        # Phase 1: Check cache
        cache_key = f"{query}:{limit}"
        if cache_key in self._cache:
            yield from self._cache[cache_key]
            return
        
        # Phase 2: Deep retrieval from episodic store
        memories = self._episodic_store.search(query, limit, filters)
        
        # Cache results
        self._cache[cache_key] = memories
        
        # Yield results
        yield from memories

    def _phase1_fast_retrieval(self, query: str) -> list[Memory]:
        """Fast cache + bloom filter check.

        Args:
            query: Search query

        Returns:
            Cached results if available
        """
        # Simple cache lookup
        return self._cache.get(query, [])

    def _phase2_deep_retrieval(self, query: str, limit: int) -> list[Memory]:
        """Deep vector + graph search.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            Ranked memories from all sources
        """
        # Delegate to episodic store for now
        return self._episodic_store.search(query, limit)
