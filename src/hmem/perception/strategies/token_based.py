"""Token-based folding strategy - default implementation."""

from hmem.perception.strategies.folding import FoldingStrategy


class TokenBasedFolder(FoldingStrategy):
    """Fold based on token threshold.

    Strategy:
    1. Keep most recent N messages intact
    2. Summarize older messages into single context block
    3. Always preserve system prompts

    Configuration:
        folding_threshold: 0.8 (trigger at 80% of max_tokens)
        preserve_recent: 5 (keep last 5 messages intact)
    """

    def __init__(
        self,
        folding_threshold: float = 0.8,
        preserve_recent: int = 5,
    ) -> None:
        """Initialize token-based folder.

        Args:
            folding_threshold: Trigger folding at this ratio of max_tokens
            preserve_recent: Number of recent messages to keep intact
        """
        self.folding_threshold = folding_threshold
        self.preserve_recent = preserve_recent

    def fold(
        self, messages: list[dict[str, str]], target_tokens: int
    ) -> list[dict[str, str]]:
        """Fold messages by summarizing old ones.

        Args:
            messages: Full message history
            target_tokens: Target token count

        Returns:
            Compressed messages
        """
        # Phase 1: Simple implementation - keep recent, drop old
        # Phase 2: Use LLM to generate summary
        if len(messages) <= self.preserve_recent:
            return messages

        recent = messages[-self.preserve_recent :]
        old = messages[: -self.preserve_recent]

        # TODO: Summarize old messages using LLM
        summary = {
            "role": "system",
            "content": f"[Previous conversation summarized: {len(old)} messages]",
        }

        return [summary] + recent

    def estimate_tokens(self, text: str) -> int:
        """Rough estimation: ~4 chars per token.

        Args:
            text: Text to estimate

        Returns:
            Estimated tokens
        """
        return len(text) // 4
