"""Shared outcome detection utility with LLM support and caching.

Provides a unified outcome detection mechanism used by both MemoryEncoder
and HybridRanker, with LRU caching to avoid redundant LLM calls.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Literal

import structlog

from hmem.agents.llm import LLMClient

logger = structlog.get_logger()


class OutcomeDetector:
    """Shared outcome detection with LLM and keyword fallback.

    Provides a unified mechanism for detecting task outcomes from content,
    used by both MemoryEncoder and HybridRanker. Features:
    - LLM-based semantic understanding when available
    - Keyword-based fallback for reliability
    - LRU cache to avoid redundant analysis

    Example:
        >>> detector = OutcomeDetector(llm_client=llm)
        >>> outcome = detector.detect("The build succeeded!")
        >>> print(outcome)  # "success"
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        cache_size: int = 100,
        use_llm: bool = True,
    ) -> None:
        """Initialize outcome detector.

        Args:
            llm_client: LLM client for semantic analysis (optional)
            cache_size: Maximum number of cached results
            use_llm: Whether to use LLM for detection (can be disabled)
        """
        self._llm = llm_client
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._cache_size = cache_size
        self._use_llm = use_llm
        self._logger = logger.bind(component="outcome_detector")

    def detect(
        self,
        content: str,
        current_outcome: str = "unknown",
    ) -> Literal["success", "failure", "unknown"]:
        """Detect outcome from content.

        If current_outcome is already known (not "unknown"), returns it directly.
        Otherwise, attempts LLM detection with keyword fallback.

        Args:
            content: Text content to analyze
            current_outcome: Pre-existing outcome if known

        Returns:
            Detected outcome: "success", "failure", or "unknown"
        """
        # Return existing outcome if already known
        if current_outcome in ("success", "failure"):
            return current_outcome  # type: ignore[return-value]

        # Check cache
        content_hash = self._hash_content(content)
        if content_hash in self._cache:
            self._cache.move_to_end(content_hash)  # LRU update
            return self._cache[content_hash]  # type: ignore[return-value]

        # Try LLM detection
        outcome: Literal["success", "failure", "unknown"] = "unknown"
        if self._use_llm and self._llm is not None:
            try:
                outcome = self._llm.infer_outcome(content)
                if outcome != "unknown":
                    self._cache_result(content_hash, outcome)
                    return outcome
            except Exception as e:
                self._logger.warning("llm_detection_failed", error=str(e))

        self._cache_result(content_hash, outcome)
        return outcome

    def _hash_content(self, content: str) -> str:
        """Generate hash for content caching.

        Args:
            content: Text content to hash

        Returns:
            Short hash string
        """
        # Use first 500 chars for hash to handle long content
        hash_input = content[:500].encode("utf-8")
        return hashlib.md5(hash_input).hexdigest()[:16]

    def _cache_result(self, content_hash: str, outcome: str) -> None:
        """Cache detection result with LRU eviction.

        Args:
            content_hash: Content hash as cache key
            outcome: Detection result to cache
        """
        self._cache[content_hash] = outcome
        self._cache.move_to_end(content_hash)

        # Evict oldest if over capacity
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def clear_cache(self) -> None:
        """Clear the detection cache."""
        self._cache.clear()

    @property
    def cache_size(self) -> int:
        """Current number of cached results."""
        return len(self._cache)
