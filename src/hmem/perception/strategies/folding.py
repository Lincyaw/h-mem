"""Abstract base class for memory folding strategies."""

from abc import ABC, abstractmethod


class FoldingStrategy(ABC):
    """Strategy for compressing context when approaching token limit.

    Different strategies trade off between:
    - Preservation of recent vs. important messages
    - Compression ratio vs. information loss
    - Processing latency vs. quality
    """

    @abstractmethod
    def fold(
        self, messages: list[dict[str, str]], target_tokens: int
    ) -> list[dict[str, str]]:
        """Compress messages to fit target token count.

        Args:
            messages: Full message history
            target_tokens: Target token count after folding

        Returns:
            Compressed message list
        """
        pass

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        pass
