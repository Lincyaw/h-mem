"""Time-window based folding strategy.

Folds messages based on time elapsed since oldest message,
rather than token count alone.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from hmem.perception.strategies.folding import FoldingStrategy

from hmem.agents.llm import LLMClient

logger = structlog.get_logger()


class TimeWindowFolder(FoldingStrategy):
    """Fold based on time window from oldest message.

    Strategy:
    1. Trigger folding when oldest message exceeds time threshold
    2. Compress messages older than the window
    3. Keep recent messages within window intact

    Use case:
    - Long-running conversations that span multiple hours/days
    - When temporal context matters more than token count

    Example:
        >>> folder = TimeWindowFolder(window_hours=24)
        >>> # Folds messages older than 24 hours
    """

    def __init__(
        self,
        window_hours: float = 24.0,
        min_messages_to_compress: int = 3,
        llm_client: LLMClient | None = None,
    ) -> None:
        """Initialize time-window folder.

        Args:
            window_hours: Time window in hours before triggering fold
            min_messages_to_compress: Minimum messages to justify compression
            llm_client: Optional LLM client for intelligent topic extraction
        """
        self.window_hours = window_hours
        self.min_messages_to_compress = min_messages_to_compress
        self._llm = llm_client

    def should_fold(
        self, messages: list[dict[str, Any]], token_count: int, limit: int
    ) -> bool:
        """Check if oldest message exceeds time window.

        Args:
            messages: Current message history (must have 'timestamp' field)
            token_count: Current estimated token count (not used directly)
            limit: Maximum token limit (not used directly)

        Returns:
            True if oldest message is older than window_hours
        """
        if len(messages) < self.min_messages_to_compress:
            return False

        # Get oldest message timestamp
        oldest_timestamp = self._get_oldest_timestamp(messages)
        if oldest_timestamp is None:
            return False

        time_diff = datetime.now() - oldest_timestamp
        return time_diff > timedelta(hours=self.window_hours)

    def compress(self, messages: list[dict[str, Any]]) -> str:
        """Compress messages with time-based summary.

        Args:
            messages: Messages to compress

        Returns:
            Summary text with time context
        """
        if len(messages) == 0:
            return ""

        oldest_timestamp = self._get_oldest_timestamp(messages)
        newest_timestamp = self._get_newest_timestamp(messages)

        time_range = ""
        if oldest_timestamp and newest_timestamp:
            time_range = f" from {oldest_timestamp.strftime('%Y-%m-%d %H:%M')} to {newest_timestamp.strftime('%H:%M')}"

        # Extract key topics mentioned
        topics = self._extract_topics(messages)
        topics_str = f" Topics: {', '.join(topics)}" if topics else ""

        return f"[Summarized {len(messages)} messages{time_range}.{topics_str}]"

    def _get_oldest_timestamp(self, messages: list[dict[str, Any]]) -> datetime | None:
        """Get timestamp of oldest message."""
        for msg in messages:
            ts = msg.get("timestamp")
            if ts:
                if isinstance(ts, datetime):
                    return ts
                elif isinstance(ts, str):
                    try:
                        return datetime.fromisoformat(ts)
                    except ValueError:
                        continue
        return None

    def _get_newest_timestamp(self, messages: list[dict[str, Any]]) -> datetime | None:
        """Get timestamp of newest message."""
        for msg in reversed(messages):
            ts = msg.get("timestamp")
            if ts:
                if isinstance(ts, datetime):
                    return ts
                elif isinstance(ts, str):
                    try:
                        return datetime.fromisoformat(ts)
                    except ValueError:
                        continue
        return None

    def _extract_topics(
        self, messages: list[dict[str, Any]], max_topics: int = 3
    ) -> list[str]:
        """Extract key topics from messages using LLM with fallback.

        Args:
            messages: Messages to analyze
            max_topics: Maximum topics to return

        Returns:
            List of topic keywords
        """
        # Combine message content for analysis
        all_content = " ".join(msg.get("content", "")[:200] for msg in messages)

        # Try LLM-based extraction
        if self._llm is not None:
            try:
                topics = self._llm.extract_conversation_topics(all_content, max_topics)
                if topics:
                    logger.debug(
                        "llm_topic_extraction_success",
                        message_count=len(messages),
                        topics=topics,
                    )
                    return topics
            except Exception as e:
                logger.warning("llm_topic_extraction_failed", error=str(e))

        # Fallback: Simple keyword extraction
        return self._extract_topics_keywords(messages, max_topics)

    def _extract_topics_keywords(
        self, messages: list[dict[str, Any]], max_topics: int = 3
    ) -> list[str]:
        """Fallback keyword-based topic extraction.

        Args:
            messages: Messages to analyze
            max_topics: Maximum topics to return

        Returns:
            List of topic keywords
        """
        all_content = " ".join(msg.get("content", "")[:100] for msg in messages)
        words = all_content.split()

        # Filter out common words and short words
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "i",
            "you",
            "we",
            "they",
            "it",
            "he",
            "she",
            "my",
            "your",
            "this",
            "that",
            "what",
            "how",
            "can",
            "will",
            "would",
            "should",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "and",
            "or",
            "but",
        }
        significant = [
            w.lower().strip(".,!?:;\"'")
            for w in words
            if len(w) > 3 and w.lower() not in stop_words
        ]

        # Return unique topics
        seen: set[str] = set()
        topics = []
        for word in significant:
            if word and word not in seen:
                seen.add(word)
                topics.append(word)
                if len(topics) >= max_topics:
                    break

        return topics
