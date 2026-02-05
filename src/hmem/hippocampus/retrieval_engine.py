"""Retrieval Engine - Unified Neo4j retrieval with hybrid ranking.

XML Markup for Memory Tracking:
    When memories are retrieved, they are wrapped in XML tags to track which
    memories were used in the conversation. The LLM analyzes conversation semantics
    to determine if these memories were helpful or not.

    Format:
        <episodic id="evt_xxx">content</episodic>
        <semantic id="fact_xxx" role="user|assistant">content</semantic>
        <skill id="skill_xxx">content</skill>
        <principle id="prin_xxx">content</principle>
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import structlog

from hmem.models import Memory
from hmem.strategies.ranking import QValueRanker, RetrievalRanker

logger = structlog.get_logger()


class LLMClientProtocol(Protocol):
    """Protocol for LLM client used in relevance filtering."""

    def filter_relevant_memories(
        self, query: str, memories: list[dict[str, str]], min_relevance: float = 0.5
    ) -> list[dict[str, Any]]:
        """Filter memories by relevance to query."""
        ...


class Neo4jStoreProtocol(Protocol):
    """Protocol for Neo4j unified store."""

    def vector_search(
        self, query_embedding: list[float], node_type: str, limit: int = 10
    ) -> list[Memory]:
        """Vector similarity search."""
        ...

    def fulltext_search(
        self, query: str, node_types: list[str] | None = None, limit: int = 10
    ) -> list[Memory]:
        """Fulltext search."""
        ...

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Combined search."""
        ...


@dataclass
class FeedbackSignal:
    """Extracted feedback signal from conversation."""

    memory_id: str
    memory_type: Literal["episodic", "semantic", "skill", "principle"]
    outcome: Literal["success", "failure"]


# Regex patterns for extracting memory IDs from XML tags
MEMORY_ID_PATTERN = re.compile(
    r'<(episodic|semantic|skill|principle)\s+id="([^"]+)"[^>]*>',
    re.IGNORECASE,
)


def extract_memory_ids(text: str) -> set[str]:
    """Extract memory IDs from conversation text containing XML-tagged memories.

    Args:
        text: Conversation text potentially containing XML-tagged memories

    Returns:
        Set of memory IDs that were referenced in the text
    """
    memory_ids: set[str] = set()

    for match in MEMORY_ID_PATTERN.finditer(text):
        mem_id = match.group(2)
        memory_ids.add(mem_id)

    return memory_ids


class RetrievalEngine:
    """Orchestrates retrieval from unified Neo4j store.

    Features:
    - Vector similarity search (using Neo4j vector indexes)
    - Fulltext search (using Neo4j fulltext indexes)
    - Hybrid ranking (similarity + Q-value + recency)
    - LLM-based relevance filtering
    - XML markup for feedback tracking

    Example:
        >>> from hmem.storage.neo4j_unified import Neo4jUnifiedStore
        >>> store = Neo4jUnifiedStore(...)
        >>> engine = RetrievalEngine(store=store)
        >>> for memory in engine.retrieve("user preferences", limit=10):
        ...     print(memory.content, memory.source)
    """

    def __init__(
        self,
        store: Neo4jStoreProtocol,
        ranker: RetrievalRanker | None = None,
        cache_size: int = 100,
        llm_client: LLMClientProtocol | None = None,
        enable_relevance_filter: bool = True,
        min_relevance_score: float = 0.5,
    ):
        """Initialize retrieval engine.

        Args:
            store: Neo4j unified store
            ranker: Ranking strategy (default: QValueRanker)
            cache_size: Maximum cache entries (LRU eviction)
            llm_client: LLM client for relevance filtering
            enable_relevance_filter: Whether to use LLM relevance filtering
            min_relevance_score: Minimum relevance score for LLM filter
        """
        self._store = store
        self._ranker = ranker or QValueRanker()
        self._cache: dict[str, list[Memory]] = {}
        self._cache_size = cache_size
        self._cache_access_order: list[str] = []
        self._llm_client = llm_client
        self._enable_relevance_filter = enable_relevance_filter
        self._min_relevance_score = min_relevance_score

    def _markup_memory(self, memory: Memory) -> Memory:
        """Apply XML markup to memory for feedback tracking.

        Args:
            memory: Original memory object

        Returns:
            Memory with XML-wrapped content
        """
        mem_id = memory.id or f"mem_{id(memory)}"
        tag = memory.source

        if tag == "semantic" and memory.metadata.get("source_role"):
            role = memory.metadata["source_role"]
            marked_content = (
                f'<{tag} id="{mem_id}" role="{role}">{memory.content}</{tag}>'
            )
        else:
            marked_content = f'<{tag} id="{mem_id}">{memory.content}</{tag}>'

        return Memory(
            id=memory.id,
            content=marked_content,
            score=memory.score,
            source=memory.source,
            timestamp=memory.timestamp,
            metadata=memory.metadata,
            parent_ids=memory.parent_ids,
            derivation_type=memory.derivation_type,
        )

    def retrieve(
        self,
        query: str,
        limit: int = 10,
        filters: dict[str, str] | None = None,
    ) -> Iterator[Memory]:
        """Execute retrieval with hybrid ranking.

        Args:
            query: Search query
            limit: Maximum results
            filters: Optional filters

        Yields:
            Memory objects ranked by relevance (wrapped with XML tags)
        """
        # Phase 1: Fast cache lookup
        cache_key = self._make_cache_key(query, limit, filters)
        cached_results = self._get_from_cache(cache_key)

        if cached_results is not None:
            logger.debug(
                "retrieval_cache_hit", query=query, results=len(cached_results)
            )
            yield from cached_results
            return

        # Phase 2: Deep retrieval from Neo4j
        logger.debug("retrieval_cache_miss", query=query)
        memories = self._deep_retrieval(query, limit, filters)

        # Apply hybrid ranking
        ranked_memories = self._ranker.rank(memories, query)

        # Apply LLM-based relevance filtering
        if self._enable_relevance_filter and self._llm_client and ranked_memories:
            ranked_memories = self._filter_by_relevance(ranked_memories, query)

        # Apply XML markup
        marked_memories = [self._markup_memory(m) for m in ranked_memories]

        # Cache results
        self._put_in_cache(cache_key, marked_memories)

        yield from marked_memories

    def _filter_by_relevance(self, memories: list[Memory], query: str) -> list[Memory]:
        """Filter memories by LLM-judged relevance.

        Args:
            memories: Candidate memories to filter
            query: The user's query

        Returns:
            List of memories that are truly relevant
        """
        if not self._llm_client or not memories:
            return memories

        memory_dicts = [
            {"id": m.id or f"mem_{i}", "content": m.content}
            for i, m in enumerate(memories)
        ]

        try:
            relevant_results = self._llm_client.filter_relevant_memories(
                query=query,
                memories=memory_dicts,
                min_relevance=self._min_relevance_score,
            )

            if not relevant_results:
                logger.info(
                    "relevance_filter_empty",
                    query=query[:50],
                    candidates=len(memories),
                )
                return []

            relevant_ids = {r["id"] for r in relevant_results}
            id_to_relevance = {r["id"]: r["relevance"] for r in relevant_results}

            filtered = []
            for mem in memories:
                mem_id = mem.id or f"mem_{memories.index(mem)}"
                if mem_id in relevant_ids:
                    filtered.append(
                        Memory(
                            id=mem.id,
                            content=mem.content,
                            score=id_to_relevance.get(mem_id, mem.score),
                            source=mem.source,
                            timestamp=mem.timestamp,
                            metadata=mem.metadata,
                            parent_ids=mem.parent_ids,
                            derivation_type=mem.derivation_type,
                        )
                    )

            filtered.sort(key=lambda m: m.score, reverse=True)

            logger.debug(
                "relevance_filter_applied",
                query=query[:50],
                before_count=len(memories),
                after_count=len(filtered),
            )

            return filtered

        except Exception as e:
            logger.warning(
                "relevance_filter_failed",
                query=query[:50],
                error=str(e),
            )
            return memories

    def _make_cache_key(
        self,
        query: str,
        limit: int,
        filters: dict[str, str] | None,
    ) -> str:
        """Create cache key from query parameters."""
        filter_str = ""
        if filters:
            filter_items = sorted(filters.items())
            filter_str = "&".join(f"{k}={v}" for k, v in filter_items)

        return f"{query}|{limit}|{filter_str}"

    def _get_from_cache(self, cache_key: str) -> list[Memory] | None:
        """Retrieve results from cache with LRU tracking."""
        if cache_key not in self._cache:
            return None

        if cache_key in self._cache_access_order:
            self._cache_access_order.remove(cache_key)
        self._cache_access_order.append(cache_key)

        return self._cache[cache_key]

    def _put_in_cache(self, cache_key: str, memories: list[Memory]) -> None:
        """Store results in cache with LRU eviction."""
        if len(self._cache) >= self._cache_size:
            if self._cache_access_order:
                oldest_key = self._cache_access_order.pop(0)
                del self._cache[oldest_key]

        self._cache[cache_key] = memories
        self._cache_access_order.append(cache_key)

    def _deep_retrieval(
        self,
        query: str,
        limit: int,
        filters: dict[str, str] | None,
    ) -> list[Memory]:
        """Deep search from unified Neo4j store.

        Uses fulltext search (vector search requires embeddings).

        Args:
            query: Search query
            limit: Maximum results
            filters: Optional filters

        Returns:
            Raw memories from Neo4j
        """
        all_memories: list[Memory] = []

        # Fulltext search across all node types
        try:
            search_limit = limit * 2  # Oversample for ranking
            results = self._store.search(query, search_limit)
            all_memories.extend(results)

            logger.debug(
                "retrieval_fulltext",
                query=query[:50],
                results=len(results),
            )
        except Exception as e:
            logger.warning(
                "retrieval_fulltext_failed",
                query=query[:50],
                error=str(e),
            )

        # Deduplicate by content
        seen_contents: dict[str, Memory] = {}
        for mem in all_memories:
            content_key = mem.content[:100]
            if (
                content_key not in seen_contents
                or mem.score > seen_contents[content_key].score
            ):
                seen_contents[content_key] = mem

        deduplicated = list(seen_contents.values())

        logger.debug(
            "retrieval_combined",
            query=query[:50],
            total_raw=len(all_memories),
            after_dedup=len(deduplicated),
        )

        return deduplicated[:limit]

    def record_feedback(
        self,
        query: str,
        accepted: bool,
        result_count: int = 0,
    ) -> None:
        """Record user feedback (placeholder for adaptive threshold).

        Args:
            query: Original query
            accepted: Whether user accepted results
            result_count: Number of results shown
        """
        logger.info(
            "retrieval_feedback_recorded",
            query=query[:50],
            accepted=accepted,
            result_count=result_count,
        )

    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._cache.clear()
        self._cache_access_order.clear()
        logger.info("retrieval_cache_cleared")
