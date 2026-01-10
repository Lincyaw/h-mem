"""Token-based folding strategy - default implementation."""

from typing import Any

from hmem.perception.strategies.folding import FoldingStrategy


class TokenBasedFolder(FoldingStrategy):
    """Fold based on token threshold.

    Strategy:
    1. Trigger folding when token count exceeds threshold ratio
    2. Keep most recent N messages intact
    3. Summarize older messages into single context block
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
    ) -> None:
        """Initialize token-based folder.

        Args:
            trigger_ratio: Trigger folding at this ratio of max_tokens (0.5-0.95)
            preserve_recent: Number of recent messages to keep intact
        """
        if not (0.5 <= trigger_ratio <= 0.95):
            raise ValueError("trigger_ratio should be between 0.5 and 0.95")

        self.trigger_ratio = trigger_ratio
        self.preserve_recent = preserve_recent

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
        """Compress messages by summarizing old ones.

        Args:
            messages: Messages to compress

        Returns:
            Summary text describing compressed content
        """
        if len(messages) == 0:
            return ""

        # Phase 1: Simple summarization
        # Phase 2+: Use LLM for intelligent summarization
        content_preview = " | ".join(
            msg.get("content", "")[:50] for msg in messages[:3]
        )
        return f"[Summarized {len(messages)} messages: {content_preview}...]"
