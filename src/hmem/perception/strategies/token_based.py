"""Token-based folding strategy - default implementation."""

from __future__ import annotations

from typing import Any

import structlog
import tiktoken

from hmem.perception.strategies.folding import FoldingStrategy

from hmem.agents.llm import LLMClient

logger = structlog.get_logger()


class TokenBasedFolder(FoldingStrategy):
    """Fold based on token threshold.

    Strategy:
    1. Trigger folding when token count exceeds threshold ratio
    2. Keep most recent N messages intact
    3. Summarize older messages using LLM (or fallback)
    4. Always preserve system prompts

    Configuration:
        trigger_ratio: 0.8 (trigger at 80% of max_tokens)
        preserve_recent: 5 (keep last 5 messages intact)

    Example:
        >>> folder = TokenBasedFolder(trigger_ratio=0.8)
        >>> if folder.should_fold(messages, token_count=3500, limit=4000):
        ...     summary = folder.compress(messages[:10])
    """

    def __init__(
        self,
        trigger_ratio: float = 0.8,
        preserve_recent: int = 5,
        encoding_name: str = "cl100k_base",
        llm_client: LLMClient | None = None,
    ) -> None:
        """Initialize token-based folder.

        Args:
            trigger_ratio: Trigger folding at this ratio of max_tokens (0.5-0.95)
            preserve_recent: Number of recent messages to keep intact
            encoding_name: Tiktoken encoding name (cl100k_base for GPT-4/3.5)
            llm_client: Optional LLM client for intelligent summarization
        """
        if not (0.5 <= trigger_ratio <= 0.95):
            raise ValueError("trigger_ratio should be between 0.5 and 0.95")

        self.trigger_ratio = trigger_ratio
        self.preserve_recent = preserve_recent
        self._encoding = tiktoken.get_encoding(encoding_name)
        self._llm = llm_client

    def estimate_tokens(self, text: str) -> int:
        """Accurately count tokens using tiktoken.

        Args:
            text: Text to count tokens for

        Returns:
            Actual token count
        """
        return len(self._encoding.encode(text))

    def should_fold(
        self, messages: list[dict[str, Any]], token_count: int, limit: int
    ) -> bool:
        """Check if token count exceeds threshold.

        Args:
            messages: Current message history
            token_count: Current estimated token count
            limit: Maximum token limit

        Returns:
            True if token_count > limit * trigger_ratio
        """
        return token_count > limit * self.trigger_ratio

    def compress(self, messages: list[dict[str, Any]]) -> str:
        """Compress messages using LLM summarization with fallback.

        Uses LLM to generate an intelligent summary that preserves
        key information, decisions, and outcomes from the messages.

        Args:
            messages: Messages to compress

        Returns:
            Summary text describing compressed content
        """
        if len(messages) == 0:
            return ""

        # Try LLM-based summarization
        if self._llm is not None:
            try:
                summary = self._llm.summarize(messages)
                if summary and summary.strip():
                    logger.debug(
                        "llm_compression_success",
                        message_count=len(messages),
                        summary_length=len(summary),
                    )
                    return summary
            except Exception as e:
                logger.warning("llm_compression_failed", error=str(e))

        # Fallback: Simple summarization
        return self._fallback_compress(messages)

    def _fallback_compress(self, messages: list[dict[str, Any]]) -> str:
        """Fallback compression without LLM.

        Creates a simple preview-based summary when LLM is unavailable.

        Args:
            messages: Messages to compress

        Returns:
            Preview-based summary
        """
        content_preview = " | ".join(
            msg.get("content", "")[:50] for msg in messages[:3]
        )
        return f"[Summarized {len(messages)} messages: {content_preview}...]"
