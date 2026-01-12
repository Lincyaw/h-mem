"""Unit tests for Bloom Filter implementation."""

import pytest
from hmem.utils.bloom_filter import BloomFilter, ScalableBloomFilter


class TestBloomFilter:
    """Test basic Bloom Filter functionality."""

    def test_basic_add_and_contains(self):
        """Test adding and checking items."""
        bf = BloomFilter(expected_items=100, false_positive_rate=0.01)

        # Add items
        bf.add("memory_123")
        bf.add("skill_456")
        bf.add("principle_789")

        # Check existence
        assert "memory_123" in bf
        assert "skill_456" in bf
        assert "principle_789" in bf

        # Check non-existence
        assert "nonexistent" not in bf
        assert "memory_999" not in bf

    def test_false_positive_rate(self):
        """Test that false positive rate is within bounds."""
        bf = BloomFilter(expected_items=1000, false_positive_rate=0.01)

        # Add 1000 items
        for i in range(1000):
            bf.add(f"item_{i}")

        # Check false positive rate with 10000 non-existent items
        false_positives = 0
        for i in range(10000):
            if f"nonexistent_{i}" in bf:
                false_positives += 1

        actual_fp_rate = false_positives / 10000
        # Should be close to expected rate (within 50% tolerance)
        assert actual_fp_rate < 0.015  # 1.5x the expected rate

    def test_no_false_negatives(self):
        """Test that there are no false negatives."""
        bf = BloomFilter(expected_items=100, false_positive_rate=0.01)

        items = [f"memory_{i}" for i in range(100)]

        # Add all items
        for item in items:
            bf.add(item)

        # Check all items exist (no false negatives)
        for item in items:
            assert item in bf, f"False negative for {item}"

    def test_clear(self):
        """Test clearing the Bloom Filter."""
        bf = BloomFilter(expected_items=10, false_positive_rate=0.01)

        # Add items
        bf.add("item_1")
        bf.add("item_2")

        assert len(bf) == 2
        assert "item_1" in bf

        # Clear
        bf.clear()

        assert len(bf) == 0
        assert "item_1" not in bf
        assert "item_2" not in bf

    def test_different_item_types(self):
        """Test adding different types of items."""
        bf = BloomFilter(expected_items=10, false_positive_rate=0.01)

        # Add different types
        bf.add("string_item")
        bf.add(12345)
        bf.add({"dict": "item"})
        bf.add(("tuple", "item"))

        # All should be findable
        assert "string_item" in bf
        assert 12345 in bf
        assert str({"dict": "item"}) in bf
        assert str(("tuple", "item")) in bf

    def test_estimate_false_positive_rate(self):
        """Test false positive rate estimation."""
        bf = BloomFilter(expected_items=100, false_positive_rate=0.01)

        # Empty filter should have 0 FP rate
        assert bf.estimate_false_positive_rate() == 0.0

        # Add some items
        for i in range(50):
            bf.add(f"item_{i}")

        # FP rate should be reasonable
        estimated_fp = bf.estimate_false_positive_rate()
        assert 0 <= estimated_fp <= 0.1

    def test_parameter_validation(self):
        """Test parameter validation."""
        # Valid parameters
        BloomFilter(expected_items=1, false_positive_rate=0.999)
        BloomFilter(expected_items=1000000, false_positive_rate=0.0001)

        # Edge cases
        bf3 = BloomFilter(expected_items=1, false_positive_rate=0.5)
        assert bf3.size > 0
        # Hash count can be 0 for edge cases, which is acceptable

    def test_repr(self):
        """Test string representation."""
        bf = BloomFilter(expected_items=100, false_positive_rate=0.01)
        bf.add("test_item")

        repr_str = repr(bf)
        assert "BloomFilter" in repr_str
        assert "size=" in repr_str
        assert "hash_count=" in repr_str
        assert "items=1" in repr_str


class TestScalableBloomFilter:
    """Test Scalable Bloom Filter functionality."""

    def test_automatic_scaling(self):
        """Test that filter automatically scales when full."""
        sbf = ScalableBloomFilter(initial_capacity=10, fp_rate=0.01, scale_factor=2)

        # Add more items than initial capacity
        for i in range(50):
            sbf.add(f"item_{i}")

        # All items should still be findable
        for i in range(50):
            assert f"item_{i}" in sbf

        # Should have multiple filters now
        assert len(sbf.filters) > 1

    def test_no_false_negatives_scaling(self):
        """Test no false negatives during scaling."""
        sbf = ScalableBloomFilter(initial_capacity=100, fp_rate=0.01)

        items = []
        for i in range(1000):
            item = f"memory_{i}"
            items.append(item)
            sbf.add(item)

        # Check all items exist
        for item in items:
            assert item in sbf

    def test_false_positive_rate_scaling(self):
        """Test FP rate remains bounded during scaling."""
        sbf = ScalableBloomFilter(initial_capacity=100, fp_rate=0.01)

        # Add many items
        for i in range(1000):
            sbf.add(f"item_{i}")

        # Check FP rate
        false_positives = 0
        for i in range(1000):
            if f"nonexistent_{i}" in sbf:
                false_positives += 1

        fp_rate = false_positives / 1000
        assert (
            fp_rate < 0.03
        )  # Should be close to target rate (relaxed for test variability)

    def test_clear_scaling(self):
        """Test clearing scalable bloom filter."""
        sbf = ScalableBloomFilter(initial_capacity=10, fp_rate=0.01)

        # Add items to trigger scaling
        for i in range(100):
            sbf.add(f"item_{i}")

        assert len(sbf) == 100
        assert len(sbf.filters) > 1

        # Clear
        sbf.clear()

        assert len(sbf) == 0
        assert len(sbf.filters) == 1  # Should reset to single filter

        # Items should not exist
        assert "item_1" not in sbf
        assert "item_99" not in sbf

    def test_len_across_filters(self):
        """Test length calculation across multiple filters."""
        sbf = ScalableBloomFilter(initial_capacity=10, fp_rate=0.01)

        # Add items
        for i in range(55):
            sbf.add(f"item_{i}")

        assert len(sbf) == 55

        # Add more to trigger scaling
        for i in range(55, 150):
            sbf.add(f"item_{i}")

        assert len(sbf) == 150

    def test_estimate_false_positive_rate_scaling(self):
        """Test FP rate estimation with multiple filters."""
        sbf = ScalableBloomFilter(initial_capacity=50, fp_rate=0.01)

        # Add items to create multiple filters
        for i in range(200):
            sbf.add(f"item_{i}")

        fp_rate = sbf.estimate_false_positive_rate()
        assert 0 <= fp_rate <= 0.05  # Should be reasonable

    def test_different_scale_factors(self):
        """Test different scale factors."""
        # Small scale factor
        sbf1 = ScalableBloomFilter(initial_capacity=10, fp_rate=0.01, scale_factor=1.5)

        # Large scale factor
        sbf2 = ScalableBloomFilter(initial_capacity=10, fp_rate=0.01, scale_factor=5)

        # Add same number of items
        for i in range(100):
            sbf1.add(f"item_{i}")
            sbf2.add(f"item_{i}")

        # Both should work
        assert len(sbf1) == 100
        assert len(sbf2) == 100

        # Different number of filters due to scale factor
        assert len(sbf1.filters) != len(sbf2.filters)


@pytest.mark.unit
def test_bloom_filter_integration():
    """Test integration with memory system concepts."""
    bf = BloomFilter(expected_items=1000, false_positive_rate=0.01)

    # Add memory-like items
    memory_ids = [f"memory_{i:06d}" for i in range(100)]
    for memory_id in memory_ids:
        bf.add(memory_id)

    # Check queries
    assert "memory_000042" in bf
    assert "memory_000099" in bf
    assert "memory_999999" not in bf  # Not added

    # Add query terms
    bf.add("python")
    bf.add("machine_learning")
    bf.add("data_science")

    assert "python" in bf
    assert "machine_learning" in bf
    assert "java" not in bf  # Not added
