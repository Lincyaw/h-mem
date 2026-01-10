class MemoryError(Exception):
    pass


class RetrievalError(MemoryError):
    pass


class ConsolidationError(MemoryError):
    pass


class ReflectionError(MemoryError):
    pass


class LockTimeoutError(MemoryError):
    pass


class ConfigurationError(MemoryError):
    pass
