"""Association discovery strategies for memory system.

Implements pluggable strategies to discover associations between memories
based on their usage patterns.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone

from hmem.models import UsageRecord, Association


class AssociationDiscoveryStrategy(ABC):
    """Abstract base class for association discovery strategies."""

    @abstractmethod
    def discover(
        self, usage_records: list[UsageRecord], min_support: int = 3
    ) -> list[Association]:
        """Discover associations from usage records.

        Args:
            usage_records: List of usage records to analyze
            min_support: Minimum occurrence count for an association

        Returns:
            List of discovered associations
        """
        pass


class DefaultAssociationDiscovery(AssociationDiscoveryStrategy):
    """Default association discovery using co-occurrence analysis.

    Discovers three types of associations:
    - COMPLEMENTS: Memories used together successfully in the same session
    - CAUSES: Memory A failed, then memory B succeeded (A causes trying B)
    - FOLLOWED_BY: Memory A used in subtask_i, B used in subtask_i+1
    """

    def discover(
        self, usage_records: list[UsageRecord], min_support: int = 3
    ) -> list[Association]:
        """Discover associations from usage records.

        Args:
            usage_records: List of usage records to analyze
            min_support: Minimum occurrence count for an association

        Returns:
            List of discovered associations
        """
        associations: list[Association] = []

        # Group records by session
        session_records: dict[str, list[UsageRecord]] = defaultdict(list)
        for record in usage_records:
            session_records[record.session_id].append(record)

        # Discover COMPLEMENTS (co-occurrence with success)
        complement_pairs = self._discover_complements(session_records, min_support)
        associations.extend(complement_pairs)

        # Discover CAUSES (failure -> success pattern)
        causal_pairs = self._discover_causal(session_records, min_support)
        associations.extend(causal_pairs)

        # Discover FOLLOWED_BY (sequence pattern)
        sequence_pairs = self._discover_sequences(session_records, min_support)
        associations.extend(sequence_pairs)

        return associations

    def _discover_complements(
        self,
        session_records: dict[str, list[UsageRecord]],
        min_support: int,
    ) -> list[Association]:
        """Discover complement associations (successful co-occurrence).

        Args:
            session_records: Records grouped by session
            min_support: Minimum occurrence count

        Returns:
            List of COMPLEMENTS associations
        """
        # Count co-occurrences of successful memory pairs
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        pair_successes: dict[tuple[str, str], int] = defaultdict(int)

        for records in session_records.values():
            # Get successful memories in this session
            successful_memories = [
                r.memory_id for r in records if r.outcome == "success"
            ]

            # Count pairs (order doesn't matter for complements)
            for i, mem_a in enumerate(successful_memories):
                for mem_b in successful_memories[i + 1 :]:
                    pair = (min(mem_a, mem_b), max(mem_a, mem_b))
                    pair_counts[pair] += 1
                    pair_successes[pair] += 1

        # Convert to associations
        associations = []
        now = datetime.now(timezone.utc)

        for pair, count in pair_counts.items():
            if count >= min_support:
                success_count = pair_successes[pair]
                confidence = success_count / count if count > 0 else 0.0

                associations.append(
                    Association(
                        source_id=pair[0],
                        target_id=pair[1],
                        relation_type="COMPLEMENTS",
                        confidence=confidence,
                        support=count,
                        discovered_at=now,
                    )
                )

        return associations

    def _discover_causal(
        self,
        session_records: dict[str, list[UsageRecord]],
        min_support: int,
    ) -> list[Association]:
        """Discover causal associations (failure followed by success).

        Args:
            session_records: Records grouped by session
            min_support: Minimum occurrence count

        Returns:
            List of CAUSES associations
        """
        # Count failure -> success patterns
        causal_counts: dict[tuple[str, str], int] = defaultdict(int)

        for records in session_records.values():
            # Sort by sequence position
            sorted_records = sorted(records, key=lambda r: r.sequence_position)

            # Look for failure -> success patterns
            for i, rec_a in enumerate(sorted_records[:-1]):
                if rec_a.outcome == "failure":
                    for rec_b in sorted_records[i + 1 :]:
                        if rec_b.outcome == "success":
                            pair = (rec_a.memory_id, rec_b.memory_id)
                            causal_counts[pair] += 1
                            break  # Only count first success after failure

        # Convert to associations
        associations = []
        now = datetime.now(timezone.utc)

        for pair, count in causal_counts.items():
            if count >= min_support:
                # Confidence is based on how often this pattern occurs
                confidence = min(1.0, count / (min_support * 2))

                associations.append(
                    Association(
                        source_id=pair[0],
                        target_id=pair[1],
                        relation_type="CAUSES",
                        confidence=confidence,
                        support=count,
                        discovered_at=now,
                    )
                )

        return associations

    def _discover_sequences(
        self,
        session_records: dict[str, list[UsageRecord]],
        min_support: int,
    ) -> list[Association]:
        """Discover sequence associations (subtask order).

        Args:
            session_records: Records grouped by session
            min_support: Minimum occurrence count

        Returns:
            List of FOLLOWED_BY associations
        """
        # Count subtask sequence patterns
        sequence_counts: dict[tuple[str, str], int] = defaultdict(int)

        for records in session_records.values():
            # Group by subtask
            subtask_records: dict[str, list[UsageRecord]] = defaultdict(list)
            for record in records:
                if record.subtask_id:
                    subtask_records[record.subtask_id].append(record)

            # Sort subtasks by first record's sequence position
            sorted_subtasks = sorted(
                subtask_records.items(),
                key=lambda x: min(r.sequence_position for r in x[1]),
            )

            # Look for consecutive subtask pairs
            for i in range(len(sorted_subtasks) - 1):
                _, recs_a = sorted_subtasks[i]
                _, recs_b = sorted_subtasks[i + 1]

                # Get successful memories from each subtask
                success_a = [r.memory_id for r in recs_a if r.outcome == "success"]
                success_b = [r.memory_id for r in recs_b if r.outcome == "success"]

                # Count pairs
                for mem_a in success_a:
                    for mem_b in success_b:
                        pair = (mem_a, mem_b)
                        sequence_counts[pair] += 1

        # Convert to associations
        associations = []
        now = datetime.now(timezone.utc)

        for pair, count in sequence_counts.items():
            if count >= min_support:
                confidence = min(1.0, count / (min_support * 2))

                associations.append(
                    Association(
                        source_id=pair[0],
                        target_id=pair[1],
                        relation_type="FOLLOWED_BY",
                        confidence=confidence,
                        support=count,
                        discovered_at=now,
                    )
                )

        return associations
