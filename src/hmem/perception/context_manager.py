"""Context Manager - Maintains LLM's limited context window.

Prevents context overflow while maintaining conversation coherence
through dynamic memory folding strategies.
"""

from hmem.models import Message
from hmem.utils.llm import LLMClient
import structlog

logger = structlog.get_logger()


class FoldingStrategy:
    """Base class for memory folding strategies."""

    def should_fold(
        self, messages: list[Message], token_count: int, limit: int
    ) -> bool:
        """Determine if folding is needed."""
        raise NotImplementedError

    def compress(self, messages: list[Message]) -> str:
        """Compress messages into a summary."""
        raise NotImplementedError


class TokenBasedFoldingStrategy(FoldingStrategy):
    """Token-based folding strategy using configurable trigger ratio."""

    def __init__(self, trigger_ratio: float = 0.8):
        """Initialize token-based folding strategy.

        Args:
            trigger_ratio: Ratio of limit to trigger folding (0.5-0.95)
        """
        if not (0.5 <= trigger_ratio <= 0.95):
            raise ValueError("trigger_ratio should be between 0.5 and 0.95")

        self.trigger_ratio = trigger_ratio
        self.llm_client = LLMClient(use_mock=True)

    def should_fold(
        self, messages: list[Message], token_count: int, limit: int
    ) -> bool:
        """Check if token count exceeds threshold."""
        return token_count > limit * self.trigger_ratio

    def compress(self, messages: list[Message]) -> str:
        """Compress messages using LLM summarization."""
        messages_dict = [{"role": msg.role, "content": msg.content} for msg in messages]

        return self.llm_client.summarize(messages_dict)


class ContextManager:
    """Manages LLM context window with dynamic folding (Phase 3).

    Responsibilities:
    - Track current conversation tokens
    - Trigger folding when approaching limit
    - Construct final system prompt with retrieved memories

    Design:
    - Strategy pattern for pluggable folding algorithms
    - Configuration-driven (no hardcoded thresholds)

    Example:
        >>> manager = ContextManager(token_limit=4000)
        >>> manager.add_message(Message(role="user", content="Hello"))
        >>> if manager.should_fold():
        ...     manager.fold()
    """

    def __init__(
        self,
        token_limit: int = 4000,
        folding_strategy: FoldingStrategy | None = None,
    ) -> None:
        """Initialize context manager.

        Args:
            token_limit: Maximum tokens before folding
            folding_strategy: Strategy for folding (default: TokenBasedFoldingStrategy)
        """
        self.token_limit = token_limit
        self.folding_strategy = folding_strategy or TokenBasedFoldingStrategy()

        self.messages: list[Message] = []
        self.summary: str | None = None
        self.was_folded = False
        self.fold_count = 0

    def add_message(
        self, role: str = None, content: str = None, message: Message = None
    ) -> None:
        """Add message to context.

        Args:
            role: 'user' | 'assistant' | 'system' (if not using message)
            content: Message content (if not using message)
            message: Message object (preferred)
        """
        if message:
            self.messages.append(message)
        elif role and content:
            self.messages.append(Message(role=role, content=content))
        else:
            raise ValueError("Must provide either message or (role, content)")

        self._check_and_fold()

    def should_fold(self) -> bool:
        """Check if folding should be triggered.

        Returns:
            True if current token count exceeds threshold
        """
        token_count = self._estimate_tokens()
        return self.folding_strategy.should_fold(
            self.messages, token_count, self.token_limit
        )

    def fold(self) -> None:
        """Execute folding strategy to compress context."""
        self._execute_fold()

    def build_prompt(self, retrieved_memories: list[str]) -> str:
        """Build final prompt with memories.

        Args:
            retrieved_memories: Memories from long-term storage

        Returns:
            Complete system prompt
        """
        memory_section = "\n".join([f"- {mem}" for mem in retrieved_memories])

        context_msgs = "\n".join(
            [f"{msg.role}: {msg.content}" for msg in self.get_context()]
        )

        return f"""Relevant Memories:
{memory_section}

Current Conversation:
{context_msgs}
"""

    def get_context(self) -> list[Message]:
        """Get current context messages.

        Returns:
            List of active messages (may include summary)
        """
        if self.summary:
            summary_msg = Message(
                role="system",
                content=f"[Summary of earlier conversation]: {self.summary}",
            )
            return [summary_msg] + self.messages

        return self.messages

    def _check_and_fold(self):
        """Check if folding is needed and execute if necessary."""
        if self.should_fold():
            self._execute_fold()

    def _estimate_tokens(self) -> int:
        """Estimate token count (rough approximation).

        Returns:
            Estimated token count
        """
        total_chars = sum(len(msg.content) for msg in self.messages)
        return int(total_chars / 4)

    def _execute_fold(self):
        """Execute memory folding by compressing older messages."""
        if len(self.messages) < 4:
            return

        split_point = len(self.messages) // 2

        to_compress = self.messages[:split_point]
        to_keep = self.messages[split_point:]

        compressed = self.folding_strategy.compress(to_compress)

        if self.summary:
            self.summary = f"{self.summary} | {compressed}"
        else:
            self.summary = compressed

        self.messages = to_keep
        self.was_folded = True
        self.fold_count += 1

        logger.info(
            "memory_folded",
            compressed_messages=len(to_compress),
            remaining_messages=len(to_keep),
            fold_count=self.fold_count,
        )

    def clear(self):
        """Clear all context."""
        self.messages = []
        self.summary = None
        self.was_folded = False
        self.fold_count = 0

    def get_stats(self) -> dict[str, any]:
        """Get context statistics.

        Returns:
            Dictionary with context stats
        """
        return {
            "message_count": len(self.messages),
            "estimated_tokens": self._estimate_tokens(),
            "token_limit": self.token_limit,
            "has_summary": self.summary is not None,
            "fold_count": self.fold_count,
            "was_folded": self.was_folded,
        }
