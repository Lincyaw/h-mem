"""Lock providers for distributed coordination.

Supports migration from single-machine to multi-instance deployment.
"""

import fcntl
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class LockProvider(ABC):
    """Abstract lock provider.

    Enables smooth migration:
    - Development: FileLockProvider
    - Production: RedisLockProvider
    """

    @abstractmethod
    @contextmanager
    def acquire(self, resource_id: str, timeout: float = 10.0) -> Iterator[None]:
        """Acquire lock for resource.

        Args:
            resource_id: Resource to lock
            timeout: Lock timeout in seconds

        Yields:
            None (lock held during context)

        Raises:
            LockError: If lock cannot be acquired
        """
        pass


class FileLockProvider(LockProvider):
    """File-based lock for single-machine deployment.

    Uses fcntl for POSIX file locking.

    Example:
        >>> provider = FileLockProvider(lock_dir="/tmp/h-mem-locks")
        >>> with provider.acquire("session_123"):
        ...     # Critical section
        ...     consolidate_memory()
    """

    def __init__(self, lock_dir: Path) -> None:
        """Initialize file lock provider.

        Args:
            lock_dir: Directory for lock files
        """
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def acquire(self, resource_id: str, timeout: float = 10.0) -> Iterator[None]:
        """Acquire file lock."""
        lock_file = self.lock_dir / f"{resource_id}.lock"
        with open(lock_file, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class RedisLockProvider(LockProvider):
    """Redis-based distributed lock.

    For multi-instance production deployment.
    Phase 3 implementation.
    """

    def __init__(self, redis_url: str) -> None:
        """Initialize Redis lock provider.

        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        raise NotImplementedError("Phase 3 implementation")

    @contextmanager
    def acquire(self, resource_id: str, timeout: float = 10.0) -> Iterator[None]:
        """Acquire Redis lock."""
        raise NotImplementedError("Phase 3 implementation")
        yield  # type: ignore
