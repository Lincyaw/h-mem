"""Sensory Buffer - Temporary storage for raw inputs.

Mimics human sensory memory that briefly holds unprocessed stimuli
before hippocampus processing.
"""

from collections import deque


class SensoryBuffer:
    """FIFO buffer for raw interaction logs.

    Holds unprocessed multi-modal inputs before consolidation.
    Simple implementation using deque for Phase 1.
    Can be upgraded to Redis list for distributed setup.

    Example:
        >>> buffer = SensoryBuffer(max_size=100)
        >>> buffer.push({"user": "query", "response": "answer"})
        >>> batch = buffer.pop_batch(10)
    """

    def __init__(self, max_size: int = 1000) -> None:
        """Initialize sensory buffer.

        Args:
            max_size: Maximum buffer size (oldest dropped when full)
        """
        self.max_size = max_size
        self._buffer: deque[dict[str, str]] = deque(maxlen=max_size)

    def push(self, raw_log: dict[str, str]) -> None:
        """Add raw log to buffer.

        Args:
            raw_log: Unprocessed interaction log
        """
        self._buffer.append(raw_log)

    def pop_batch(self, size: int) -> list[dict[str, str]]:
        """Pop batch for processing.

        Args:
            size: Batch size

        Returns:
            List of raw logs (oldest first)
        """
        batch = []
        for _ in range(min(size, len(self._buffer))):
            if self._buffer:
                batch.append(self._buffer.popleft())
        return batch

    def size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)
