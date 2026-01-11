"""Lock providers for distributed coordination.

Re-exports from hmem.strategies.locks for backward compatibility.
The canonical implementation is in hmem.strategies.locks.
"""

from hmem.strategies.locks import (
    FileLockProvider,
    LockProvider,
    LockTimeoutError,
)

__all__ = ["LockProvider", "FileLockProvider", "LockTimeoutError"]
