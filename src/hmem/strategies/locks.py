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

from hmem.exceptions import LockTimeoutError


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
            lock_file = open(lock_path, 'w')
            
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
