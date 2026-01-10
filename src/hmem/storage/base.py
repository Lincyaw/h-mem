"""Base class for storage implementations."""

from abc import ABC, abstractmethod


class BaseStore(ABC):
    """Abstract base for all storage backends.

    Ensures consistent interface for episodic/semantic/skill stores.
    Supports migration path from embedded to distributed solutions.
    """

    @abstractmethod
    def health_check(self) -> dict[str, str | int]:
        """Check store health status.

        Returns:
            Health metrics: status, count, latency
        """
        pass

    @abstractmethod
    def get_stats(self) -> dict[str, int]:
        """Get storage statistics.

        Returns:
            Statistics: total_count, size_bytes, etc.
        """
        pass
