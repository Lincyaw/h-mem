"""Lock providers for transaction management.

Implements pluggable locking mechanisms to prevent concurrent
consolidation of the same session. Supports file-based locks
(single machine) and can be extended to Redis locks (distributed).
"""

import fcntl
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import structlog

from hmem.exceptions import LockTimeoutError

logger = structlog.get_logger()


class LockProvider(ABC):
    """Abstract base class for lock providers.

    Supports migration from single-machine to distributed deployments
    by providing a common interface for different lock backends.
    """

    @abstractmethod
    @contextmanager
    def acquire(self, key: str, timeout: float = 30.0) -> Iterator[None]:
        """Acquire exclusive lock with timeout.

        Args:
            key: Unique identifier for the lock
            timeout: Maximum seconds to wait for lock

        Yields:
            None when lock is acquired

        Raises:
            LockTimeoutError: If lock cannot be acquired within timeout
        """
        pass


class FileLockProvider(LockProvider):
    """File-based lock implementation for single-machine deployment.

    Uses fcntl for advisory file locking. Suitable for:
    - Development environments
    - Single-instance production deployments
    - Systems with shared filesystem

    Not suitable for:
    - Multi-instance deployments without shared storage
    - High-throughput scenarios (file I/O overhead)
    """

    def __init__(self, lock_dir: str | Path = "/tmp/h-mem-locks"):
        """Initialize file lock provider.

        Args:
            lock_dir: Directory to store lock files
        """
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def acquire(self, key: str, timeout: float = 30.0) -> Iterator[None]:
        """Acquire file-based exclusive lock.

        Args:
            key: Lock identifier (will be sanitized for filesystem)
            timeout: Maximum seconds to wait

        Yields:
            None when lock acquired

        Raises:
            LockTimeoutError: If timeout exceeded
        """
        # Sanitize key for filesystem
        safe_key = key.replace("/", "_").replace(":", "_")
        lock_path = self.lock_dir / f"{safe_key}.lock"

        lock_file = None
        start_time = time.time()

        try:
            lock_file = open(lock_path, "w")

            # Try to acquire lock with timeout
            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break  # Lock acquired
                except BlockingIOError:
                    # Lock held by another process
                    elapsed = time.time() - start_time
                    if elapsed >= timeout:
                        raise LockTimeoutError(
                            f"Failed to acquire lock '{key}' within {timeout}s"
                        )
                    time.sleep(0.1)  # Wait before retry

            # Lock acquired, yield control
            yield

        finally:
            if lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                except Exception:
                    pass  # Best effort cleanup

                # Clean up lock file
                try:
                    os.unlink(lock_path)
                except Exception:
                    pass  # File may be in use by another process


class RedisLockProvider(LockProvider):
    """Redis-based distributed lock implementation (Phase 3).

    Uses Redis SET NX with expiration for distributed locking.
    Suitable for:
    - Multi-instance deployments
    - Distributed systems
    - High-availability scenarios

    Requires:
    - Redis server
    - redis-py package

    Example:
        >>> provider = RedisLockProvider("redis://localhost:6379/0")
        >>> with provider.acquire("session_123", timeout=10.0):
        ...     # Critical section
        ...     process_session()
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "hmem:lock:",
        lock_ttl: float = 60.0,
    ):
        """Initialize Redis lock provider.

        Args:
            redis_url: Redis connection URL
            key_prefix: Prefix for lock keys in Redis
            lock_ttl: Lock time-to-live in seconds (auto-release)
        """
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.lock_ttl = lock_ttl
        self._client: Any = None
        self._lock_value: str | None = None

    @property
    def client(self) -> Any:
        """Lazy initialization of Redis client."""
        if self._client is None:
            try:
                import redis  # type: ignore[import-not-found]
            except ImportError:
                raise ImportError(
                    "Redis package not installed. Install with: pip install redis"
                )

            self._client = redis.from_url(self.redis_url)

            # Test connection
            try:
                self._client.ping()
                logger.info("redis_lock_connected", url=self.redis_url)
            except Exception as e:
                logger.error("redis_lock_connection_failed", error=str(e))
                raise

        return self._client

    def _generate_lock_value(self) -> str:
        """Generate unique lock value for ownership verification."""
        import uuid

        return f"{os.getpid()}:{uuid.uuid4().hex[:8]}"

    @contextmanager
    def acquire(self, key: str, timeout: float = 30.0) -> Iterator[None]:
        """Acquire Redis-based distributed lock.

        Uses SET NX (set if not exists) with expiration for atomic
        lock acquisition. The lock auto-expires after lock_ttl seconds
        to prevent deadlocks from crashed processes.

        Args:
            key: Lock identifier
            timeout: Maximum seconds to wait for lock

        Yields:
            None when lock acquired

        Raises:
            LockTimeoutError: If timeout exceeded
        """
        lock_key = f"{self.key_prefix}{key}"
        lock_value = self._generate_lock_value()
        start_time = time.time()

        try:
            # Try to acquire lock with timeout
            while True:
                # SET NX with expiration (atomic operation)
                acquired = self.client.set(
                    lock_key,
                    lock_value,
                    nx=True,  # Only set if not exists
                    ex=int(self.lock_ttl),  # Expiration in seconds
                )

                if acquired:
                    logger.debug(
                        "redis_lock_acquired",
                        key=key,
                        lock_key=lock_key,
                        ttl=self.lock_ttl,
                    )
                    break

                # Check timeout
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise LockTimeoutError(
                        f"Failed to acquire Redis lock '{key}' within {timeout}s"
                    )

                # Wait before retry with exponential backoff
                wait_time = min(0.1 * (1 + elapsed / timeout), 1.0)
                time.sleep(wait_time)

            # Lock acquired, yield control
            yield

        finally:
            # Release lock only if we own it (verify value)
            # Use Lua script for atomic check-and-delete
            release_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            try:
                self.client.eval(release_script, 1, lock_key, lock_value)
                logger.debug("redis_lock_released", key=key)
            except Exception as e:
                logger.warning("redis_lock_release_failed", key=key, error=str(e))

    def extend(self, key: str, additional_ttl: float) -> bool:
        """Extend lock TTL for long-running operations.

        Args:
            key: Lock identifier
            additional_ttl: Additional seconds to add to TTL

        Returns:
            True if extended successfully
        """
        lock_key = f"{self.key_prefix}{key}"

        try:
            # Use EXPIRE to extend TTL
            current_ttl = self.client.ttl(lock_key)
            if current_ttl > 0:
                new_ttl = int(current_ttl + additional_ttl)
                return bool(self.client.expire(lock_key, new_ttl))
            return False
        except Exception as e:
            logger.warning("redis_lock_extend_failed", key=key, error=str(e))
            return False

    def is_locked(self, key: str) -> bool:
        """Check if a key is currently locked.

        Args:
            key: Lock identifier

        Returns:
            True if locked
        """
        lock_key = f"{self.key_prefix}{key}"
        return bool(self.client.exists(lock_key))

    def force_release(self, key: str) -> bool:
        """Force release a lock (admin operation).

        Use with caution - can break lock ownership guarantees.

        Args:
            key: Lock identifier

        Returns:
            True if released
        """
        lock_key = f"{self.key_prefix}{key}"
        try:
            return bool(self.client.delete(lock_key))
        except Exception as e:
            logger.error("redis_lock_force_release_failed", key=key, error=str(e))
            return False


def create_lock_provider(backend: str, **kwargs: Any) -> LockProvider:
    """Factory function to create lock provider.

    Args:
        backend: Lock backend URI (file:// or redis://)
        **kwargs: Additional arguments for the provider

    Returns:
        Configured LockProvider instance

    Example:
        >>> provider = create_lock_provider("file:///tmp/locks")
        >>> provider = create_lock_provider("redis://localhost:6379/0")
    """
    if backend.startswith("file://"):
        lock_dir = backend.replace("file://", "")
        return FileLockProvider(lock_dir=lock_dir)
    elif backend.startswith("redis://"):
        return RedisLockProvider(redis_url=backend, **kwargs)
    else:
        # Default to file-based
        logger.warning(
            "unknown_lock_backend",
            backend=backend,
            fallback="file:///tmp/h-mem-locks",
        )
        return FileLockProvider(lock_dir="/tmp/h-mem-locks")
