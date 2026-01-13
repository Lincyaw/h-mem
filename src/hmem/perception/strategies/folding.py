"""Abstract base class for memory folding strategies.

This is the single source of truth for FoldingStrategy interface.
All folding implementations should inherit from this class.
"""

from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger()


class FoldingStrategy(ABC):
    """Strategy for compressing context when approaching token limit.

    Different strategies trade off between:
    - Preservation of recent vs. important messages
    - Compression ratio vs. information loss
    - Processing latency vs. quality

    All concrete implementations must provide:
    - should_fold(): Determine if folding is needed
    - compress(): Execute compression and return summary
    - estimate_tokens(): Estimate token count for text
    """

    @abstractmethod
    def should_fold(
        self, messages: list[dict[str, Any]], token_count: int, limit: int
    ) -> bool:
        """Determine if folding is needed.

        Args:
            messages: Current message history
            token_count: Current estimated token count
            limit: Maximum token limit

        Returns:
            True if folding should be triggered
        """
        pass

    @abstractmethod
    def compress(self, messages: list[dict[str, Any]]) -> str:
        """Compress messages into a summary string.

        Args:
            messages: Messages to compress

        Returns:
            Compressed summary text
        """
        pass

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text using tiktoken.

        Uses tiktoken for accurate counting when available,
        falls back to character-based estimation.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        try:
            import tiktoken

            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except ImportError:
            logger.debug("tiktoken_not_available_using_fallback")
            # Fallback: ~4 chars per token approximation
            return len(text) // 4
        except Exception as e:
            logger.warning("token_estimation_failed", error=str(e))
            return len(text) // 4
