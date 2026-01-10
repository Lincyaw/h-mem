"""Retrieval Engine - Two-phase memory retrieval with hybrid ranking.

XML Markup for Actionable Memories:
    When skill or principle memories are retrieved, they are wrapped in XML tags
    to enable feedback tracking. The agent can use these memories and the system
    will automatically detect usage in subsequent conversations.

    Format:
        <skill id="skill_xxx" outcome="pending">content</skill>
        <principle id="fact_xxx" outcome="pending">content</principle>

    The 'outcome' attribute should be updated by the agent to 'success' or 'failure'
    before calling remember() to close the feedback loop.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, Protocol

import structlog

from hmem.models import Memory
from hmem.storage.episodic import EpisodicStore
from hmem.strategies.ranking import HybridRanker, RetrievalRanker

logger = structlog.get_logger()


@dataclass
class FeedbackSignal:
    """Extracted feedback signal from conversation."""

    memory_id: str
    memory_type: Literal["episodic", "semantic", "skill", "principle"]
    outcome: Literal["success", "failure"]


# Regex patterns for extracting feedback from conversation
# All memory types are supported: episodic, semantic, skill, principle
MEMORY_PATTERN = re.compile(
    r'<(episodic|semantic|skill|principle)\s+id="([^"]+)"\s+outcome="(success|failure)"[^>]*>',
    re.IGNORECASE,
)

# Legacy patterns for backward compatibility
SKILL_PATTERN = re.compile(
    r'<skill\s+id="([^"]+)"\s+outcome="(success|failure)"[^>]*>',
    re.IGNORECASE,
)
PRINCIPLE_PATTERN = re.compile(
    r'<principle\s+id="([^"]+)"\s+outcome="(success|failure)"[^>]*>',
    re.IGNORECASE,
)


def extract_feedback_signals(text: str) -> list[FeedbackSignal]:
    """Extract feedback signals from text containing XML-marked memories.

    Looks for patterns like:
        <episodic id="evt_xxx" outcome="success">...</episodic>
        <semantic id="fact_xxx" outcome="failure">...</semantic>
        <skill id="skill_xxx" outcome="success">...</skill>
        <principle id="fact_xxx" outcome="failure">...</principle>

    Args:
        text: Text potentially containing XML-marked memory usage

    Returns:
        List of extracted feedback signals
    """
    signals: list[FeedbackSignal] = []
    seen_ids: set[str] = set()  # Deduplicate

    # Extract all memory type feedback using unified pattern
    for match in MEMORY_PATTERN.finditer(text):
        mem_type = match.group(1).lower()
        mem_id = match.group(2)
        outcome = match.group(3).lower()

        if mem_id not in seen_ids:
            seen_ids.add(mem_id)
            signals.append(
                FeedbackSignal(
                    memory_id=mem_id,
                    memory_type=mem_type,  # type: ignore
                    outcome=outcome,  # type: ignore
                )
            )

    return signals


class SemanticStoreProtocol(Protocol):
    """Protocol for semantic store implementations."""

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Search semantic facts."""
        ...


class SkillStoreProtocol(Protocol):
    """Protocol for skill store implementations."""

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Search skill templates."""
        ...


class RetrievalEngine:
    """Orchestrates two-phase retrieval process with hybrid sources.

    Phase 1 (sync, P95 < 50ms):
    - Check in-memory cache
    - Bloom filter for quick negative checks (future)

    Phase 2 (async, P95 < 500ms):
    - Vector similarity search (ChromaDB) - Episodic memories
    - Graph relationship traversal (SQLite) - Semantic facts
    - Skill pattern matching - Procedural memories
    - Hybrid ranking (similarity + recency + importance)

    Returns results as iterator for progressive rendering.

    Example:
        >>> engine = RetrievalEngine(episodic_store, semantic_store, skill_store)
        >>> for memory in engine.retrieve("user preferences", limit=10):
        ...     print(memory.content, memory.source)
        ...     if good_enough:
        ...         break  # Early termination supported
    """

    def __init__(
        self,
        episodic_store: EpisodicStore,
        semantic_store: SemanticStoreProtocol | None = None,
        skill_store: SkillStoreProtocol | None = None,
        ranker: RetrievalRanker | None = None,
        cache_size: int = 100,
    ):
        """Initialize retrieval engine.

        Args:
            episodic_store: Episodic memory store (required)
            semantic_store: Semantic memory store (optional, Phase 2+)
            skill_store: Skill/procedural memory store (optional, Phase 3)
            ranker: Ranking strategy (default: HybridRanker)
            cache_size: Maximum cache entries (LRU eviction)
        """
        self._episodic_store = episodic_store
        self._semantic_store = semantic_store
        self._skill_store = skill_store
        self._ranker = ranker or HybridRanker()
        self._cache: dict[str, list[Memory]] = {}
        self._cache_size = cache_size
        self._cache_access_order: list[str] = []  # For LRU

    def _markup_memory(self, memory: Memory) -> Memory:
        """Apply XML markup to all memories for feedback tracking.

        All memory types are wrapped with XML tags to enable the feedback loop:
        - <episodic id="xxx" outcome="pending">content</episodic>
        - <semantic id="xxx" outcome="pending">content</semantic>
        - <skill id="xxx" outcome="pending">content</skill>
        - <principle id="xxx" outcome="pending">content</principle>

        The agent can update the outcome attribute to 'success' or 'failure',
        and remember() will automatically detect and process the feedback.

        Args:
            memory: Original memory object

        Returns:
            Memory with XML-wrapped content
        """
        mem_id = memory.id or f"mem_{id(memory)}"
        tag = memory.source  # "episodic", "semantic", "skill", or "principle"

        # Wrap content in XML with outcome="pending"
        marked_content = (
            f'<{tag} id="{mem_id}" outcome="pending">{memory.content}</{tag}>'
        )

        # Return new Memory with marked content
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
        """Execute two-phase retrieval with hybrid ranking.

        All memories are automatically wrapped in XML tags to enable feedback tracking:
            <episodic id="xxx" outcome="pending">content</episodic>
            <semantic id="xxx" outcome="pending">content</semantic>
            <skill id="xxx" outcome="pending">content</skill>
            <principle id="xxx" outcome="pending">content</principle>

        Args:
            query: Search query
            limit: Maximum results
            filters: Optional filters (session_id, date_range, etc.)

        Yields:
            Memory objects ranked by relevance (skill/principle marked with XML)

        Performance:
            - Phase 1 (cache hit): P95 < 10ms
            - Phase 2 (deep search): P95 < 200ms (Phase 1), < 500ms (Phase 2+)
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

        # Phase 2: Deep retrieval from episodic store
        logger.debug("retrieval_cache_miss", query=query)
        memories = self._deep_retrieval(query, limit, filters)

        # Apply hybrid ranking
        ranked_memories = self._ranker.rank(memories, query)

        # Apply XML markup to skill/principle memories
        marked_memories = [self._markup_memory(m) for m in ranked_memories]

        # Cache results (with markup)
        self._put_in_cache(cache_key, marked_memories)

        # Yield results with markup
        yield from marked_memories

    def _make_cache_key(
        self,
        query: str,
        limit: int,
        filters: dict[str, str] | None,
    ) -> str:
        """Create cache key from query parameters.

        Args:
            query: Search query
            limit: Result limit
            filters: Optional filters

        Returns:
            Cache key string
        """
        filter_str = ""
        if filters:
            filter_items = sorted(filters.items())
            filter_str = "&".join(f"{k}={v}" for k, v in filter_items)

        return f"{query}|{limit}|{filter_str}"

    def _get_from_cache(self, cache_key: str) -> list[Memory] | None:
        """Retrieve results from cache with LRU tracking.

        Args:
            cache_key: Cache key

        Returns:
            Cached memories or None if not found
        """
        if cache_key not in self._cache:
            return None

        # Update LRU access order
        if cache_key in self._cache_access_order:
            self._cache_access_order.remove(cache_key)
        self._cache_access_order.append(cache_key)

        return self._cache[cache_key]

    def _put_in_cache(self, cache_key: str, memories: list[Memory]) -> None:
        """Store results in cache with LRU eviction.

        Args:
            cache_key: Cache key
            memories: Memories to cache
        """
        # Evict oldest if cache full
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
        """Deep vector + graph + skill search.

        Combines results from all three memory stores:
        - Episodic: Vector similarity search for past experiences
        - Semantic: Graph traversal for facts and relationships
        - Skill: Pattern matching for procedural templates

        Args:
            query: Search query
            limit: Maximum results
            filters: Optional filters

        Returns:
            Raw memories from all sources (before ranking)
        """
        all_memories: list[Memory] = []

        # Episodic search (always available)
        episodic_limit = (
            limit * 2 if self._semantic_store or self._skill_store else limit
        )
        episodic_results = self._episodic_store.search(query, episodic_limit, filters)
        all_memories.extend(episodic_results)

        logger.debug(
            "retrieval_episodic",
            query=query[:50],
            results=len(episodic_results),
        )

        # Semantic search (Phase 2+)
        if self._semantic_store:
            try:
                semantic_limit = max(limit // 2, 5)
                semantic_results = self._semantic_store.search(query, semantic_limit)
                all_memories.extend(semantic_results)

                logger.debug(
                    "retrieval_semantic",
                    query=query[:50],
                    results=len(semantic_results),
                )
            except Exception as e:
                logger.warning(
                    "retrieval_semantic_failed",
                    query=query[:50],
                    error=str(e),
                )

        # Skill search (Phase 3)
        if self._skill_store:
            try:
                skill_limit = max(limit // 3, 3)
                skill_results = self._skill_store.search(query, skill_limit)

                # Wrap skills with XML markup for feedback tracking
                for skill in skill_results:
                    skill_id = skill.metadata.get("skill_id", skill.id or "unknown")
                    skill.content = f'<skill id="{skill_id}" outcome="pending">{skill.content}</skill>'

                all_memories.extend(skill_results)

                logger.debug(
                    "retrieval_skill",
                    query=query[:50],
                    results=len(skill_results),
                )
            except Exception as e:
                logger.warning(
                    "retrieval_skill_failed",
                    query=query[:50],
                    error=str(e),
                )

        # Deduplicate by content (keep highest score)
        seen_contents: dict[str, Memory] = {}
        for mem in all_memories:
            content_key = mem.content[:100]  # Use first 100 chars as key
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

        return deduplicated

    def clear_cache(self) -> None:
        """Clear all cached results.

        Useful for testing or when memory contents change significantly.
        """
        self._cache.clear()
        self._cache_access_order.clear()
        logger.info("retrieval_cache_cleared")
