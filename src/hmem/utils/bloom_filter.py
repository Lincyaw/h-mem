"""Bloom Filter implementation for fast memory existence checks in Phase 1 retrieval."""

import math
import hashlib
from typing import Iterator


class BloomFilter:
    """Space-efficient probabilistic data structure for set membership testing.

    Used in Phase 1 retrieval to quickly check if a memory might exist,
    avoiding expensive database lookups for non-existent items.

    Properties:
    - No false negatives (if item was added, it will be found)
    - Possible false positives (might say item exists when it doesn't)
    - Space efficient compared to storing all items

    Example:
        >>> bf = BloomFilter(expected_items=10000, false_positive_rate=0.01)
        >>> bf.add("memory_123")
        >>> assert "memory_123" in bf
        >>> assert "memory_999" not in bf  # Probably
    """

    def __init__(self, expected_items: int = 10000, false_positive_rate: float = 0.01):
        """Initialize Bloom Filter.

        Args:
            expected_items: Expected number of items to store
            false_positive_rate: Desired false positive rate (0.0-1.0)
        """
        self.expected_items = expected_items
        self.false_positive_rate = false_positive_rate

        # Calculate optimal parameters
        self.size = self._optimal_size(expected_items, false_positive_rate)
        self.hash_count = self._optimal_hash_count(self.size, expected_items)

        # Initialize bit array
        self.bit_array = [False] * self.size
        self.item_count = 0

    def _optimal_size(self, n: int, p: float) -> int:
        """Calculate optimal bit array size.

        Formula: m = -(n * ln(p)) / (ln(2)^2)
        """
        return int(-(n * math.log(p)) / (math.log(2) ** 2))

    def _optimal_hash_count(self, m: int, n: int) -> int:
        """Calculate optimal number of hash functions.

        Formula: k = (m/n) * ln(2)
        """
        return int((m / n) * math.log(2))

    def _hashes(self, item: str) -> Iterator[int]:
        """Generate hash values for an item.

        Uses double hashing technique for better distribution.
        """
        # Primary hash
        h1 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        # Secondary hash
        h2 = int(hashlib.sha256(item.encode()).hexdigest(), 16)

        # Generate k hash values using double hashing
        for i in range(self.hash_count):
            yield (h1 + i * h2) % self.size

    def add(self, item: str) -> None:
        """Add an item to the Bloom Filter.

        Args:
            item: Item to add (converted to string)
        """
        item_str = str(item)
        for hash_value in self._hashes(item_str):
            self.bit_array[hash_value] = True
        self.item_count += 1

    def __contains__(self, item: str) -> bool:
        """Check if item might be in the Bloom Filter.

        Args:
            item: Item to check

        Returns:
            True if item might be in set, False if definitely not
        """
        item_str = str(item)
        for hash_value in self._hashes(item_str):
            if not self.bit_array[hash_value]:
                return False
        return True

    def might_contain(self, item: str) -> bool:
        """Alias for __contains__ for clarity."""
        return item in self

    def clear(self) -> None:
        """Clear all items from the Bloom Filter."""
        self.bit_array = [False] * self.size
        self.item_count = 0

    def estimate_false_positive_rate(self) -> float:
        """Estimate current false positive rate.

        Formula: (1 - e^(-kn/m))^k
        """
        if self.item_count == 0:
            return 0.0

        ratio = self.bit_array.count(True) / self.size
        return ratio**self.hash_count

    def __len__(self) -> int:
        """Return number of items added."""
        return self.item_count

    def __repr__(self) -> str:
        """String representation of Bloom Filter."""
        return (
            f"BloomFilter(size={self.size}, hash_count={self.hash_count}, "
            f"items={self.item_count}, fp_rate={self.estimate_false_positive_rate():.4f})"
        )


class ScalableBloomFilter:
    """Bloom Filter that can grow as more items are added.

    Automatically adds new Bloom Filters when capacity is reached,
    maintaining the desired false positive rate.

    Example:
        >>> sbf = ScalableBloomFilter(initial_capacity=1000, fp_rate=0.01)
        >>> for i in range(10000):
        ...     sbf.add(f"item_{i}")
        >>> assert "item_5000" in sbf
    """

    def __init__(
        self, initial_capacity: int = 1000, fp_rate: float = 0.01, scale_factor: int = 2
    ):
        """Initialize Scalable Bloom Filter.

        Args:
            initial_capacity: Initial capacity of first filter
            fp_rate: Desired false positive rate
            scale_factor: Factor by which to increase capacity
        """
        self.fp_rate = fp_rate
        self.scale_factor = scale_factor
        self.filters: list[BloomFilter] = []
        self.current_capacity = initial_capacity
        self._add_filter()

    def _add_filter(self) -> None:
        """Add a new Bloom Filter."""
        new_filter = BloomFilter(
            expected_items=self.current_capacity, false_positive_rate=self.fp_rate
        )
        self.filters.append(new_filter)

    def add(self, item: str) -> None:
        """Add an item to the Scalable Bloom Filter."""
        # Add to the last filter
        self.filters[-1].add(item)

        # If last filter is at capacity, add a new one
        if len(self.filters[-1]) >= self.filters[-1].expected_items:
            self.current_capacity *= self.scale_factor
            self._add_filter()

    def __contains__(self, item: str) -> bool:
        """Check if item is in any of the filters."""
        return any(item in bf for bf in self.filters)

    def clear(self) -> None:
        """Clear all filters."""
        self.filters.clear()
        self.current_capacity = self.filters[0].expected_items if self.filters else 1000
        self._add_filter()

    def __len__(self) -> int:
        """Return total number of items across all filters."""
        return sum(len(bf) for bf in self.filters)

    def estimate_false_positive_rate(self) -> float:
        """Estimate overall false positive rate."""
        if not self.filters:
            return 0.0

        # Weighted average of all filters
        total_items = len(self)
        if total_items == 0:
            return 0.0

        weighted_fp = sum(
            bf.estimate_false_positive_rate() * len(bf) for bf in self.filters
        )
        return weighted_fp / total_items
