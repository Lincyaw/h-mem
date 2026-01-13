"""Sensory Buffer - Temporary storage for raw inputs.

Mimics human sensory memory that briefly holds unprocessed stimuli
before hippocampus processing.
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BufferItem:
    """Item in sensory buffer with metadata."""

    raw_log: dict[str, Any]
    priority: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    content_hash: str = ""

    def __post_init__(self) -> None:
        """Generate content hash for deduplication."""
        if not self.content_hash:
            content = str(sorted(self.raw_log.items()))
            self.content_hash = hashlib.md5(content.encode()).hexdigest()[:16]


class SensoryBuffer:
    """Enhanced FIFO buffer with priority and deduplication.

    Holds unprocessed multi-modal inputs before consolidation.
    Features:
    - Priority-based processing (higher priority processed first)
    - Content-based deduplication (optional)
    - Timestamp tracking for age-based processing

    Example:
        >>> buffer = SensoryBuffer(max_size=100)
        >>> buffer.push({"user": "query", "response": "answer"})
        >>> batch = buffer.pop_batch(10)
        >>> # Or with priority-aware batching
        >>> batch = buffer.pop_batch(10, priority_aware=True)
    """

    def __init__(
        self,
        max_size: int = 1000,
        deduplicate: bool = True,
    ) -> None:
        """Initialize sensory buffer.

        Args:
            max_size: Maximum buffer size (oldest dropped when full)
            deduplicate: Whether to skip duplicate content
        """
        self.max_size = max_size
        self.deduplicate = deduplicate
        self._buffer: deque[BufferItem] = deque(maxlen=max_size)
        self._seen_hashes: set[str] = set()

    def push(
        self,
        raw_log: dict[str, Any],
        priority: int = 0,
    ) -> bool:
        """Add raw log to buffer with optional priority.

        Args:
            raw_log: Unprocessed interaction log
            priority: Processing priority (higher = processed sooner)

        Returns:
            True if added, False if duplicate (when deduplicate=True)
        """
        item = BufferItem(raw_log=raw_log, priority=priority)

        # Check for duplicates
        if self.deduplicate and item.content_hash in self._seen_hashes:
            return False

        self._buffer.append(item)

        if self.deduplicate:
            self._seen_hashes.add(item.content_hash)
            # Limit seen hashes to prevent unbounded growth
            if len(self._seen_hashes) > self.max_size * 2:
                # Rebuild set from current buffer
                self._seen_hashes = {i.content_hash for i in self._buffer}

        return True

    def pop_batch(
        self,
        size: int,
        priority_aware: bool = False,
    ) -> list[dict[str, Any]]:
        """Pop batch for processing.

        Args:
            size: Batch size
            priority_aware: If True, return highest priority items first

        Returns:
            List of raw logs
        """
        if not priority_aware:
            # Original FIFO behavior for backward compatibility
            batch = []
            for _ in range(min(size, len(self._buffer))):
                if self._buffer:
                    item = self._buffer.popleft()
                    if self.deduplicate:
                        self._seen_hashes.discard(item.content_hash)
                    batch.append(item.raw_log)
            return batch

        # Priority-aware: sort and pop highest priority first
        if not self._buffer:
            return []

        # Convert to list for sorting
        items = list(self._buffer)
        items.sort(key=lambda x: (-x.priority, x.timestamp))

        # Take top N items
        selected = items[:size]
        batch = []

        for item in selected:
            self._buffer.remove(item)
            if self.deduplicate:
                self._seen_hashes.discard(item.content_hash)
            batch.append(item.raw_log)

        return batch

    def size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)

    def peek(self, count: int = 1) -> list[dict[str, Any]]:
        """Peek at items without removing them.

        Args:
            count: Number of items to peek

        Returns:
            List of raw logs (oldest first)
        """
        items = list(self._buffer)[:count]
        return [item.raw_log for item in items]

    def clear(self) -> None:
        """Clear all items from buffer."""
        self._buffer.clear()
        self._seen_hashes.clear()
