---
name: python-architecture
description: Advanced Python development guidance with focus on architecture, design patterns, code quality, type safety, and modern best practices. Use when designing Python systems, refactoring codebases, implementing complex features, reviewing architecture decisions, applying design patterns, or ensuring code follows best practices for maintainability, testability, and performance.
---

# Python Architecture & Advanced Development

This skill provides expert guidance for Python development with focus on architecture design, code quality, and engineering excellence.

## Core Principles

### 1. Type Safety First

**Always use comprehensive type hints with modern syntax:**

```python
# ✅ Modern syntax (Python 3.10+)
def process_data(items: list[dict[str, int]]) -> dict[str, float] | None:
    """Process items and return aggregated results."""
    pass

# ❌ Deprecated syntax
from typing import Dict, List, Optional
def process_data(items: List[Dict[str, int]]) -> Optional[Dict[str, float]]:
    pass
```

**Type hierarchy rules:**
- Prefer `Sequence[T]` over `list[T]` for function parameters (accepts lists, tuples, etc.)
- Use `Mapping[K, V]` over `dict[K, V]` for read-only dictionaries
- Use `Iterable[T]` or `Iterator[T]` for iteration contexts
- Avoid `Any` type - use generics, protocols, or union types instead

### 2. Composition Over Inheritance

Favor composition and protocols over deep inheritance hierarchies:

```python
# ✅ Composition with protocols
from typing import Protocol

class DataSource(Protocol):
    def fetch(self) -> bytes: ...

class DataProcessor:
    def __init__(self, source: DataSource):
        self._source = source
    
    def process(self) -> dict[str, any]:
        data = self._source.fetch()
        return self._parse(data)

# ❌ Deep inheritance
class BaseProcessor:
    pass

class HTTPProcessor(BaseProcessor):
    pass

class JSONHTTPProcessor(HTTPProcessor):
    pass
```

### 3. Immutability and Data Validation

**Use Pydantic for all business data:**

```python
from pydantic import BaseModel, Field, validator
from datetime import datetime

class UserAccount(BaseModel):
    user_id: str = Field(..., min_length=1)
    email: str
    created_at: datetime
    balance: float = Field(ge=0)
    
    @validator('email')
    def validate_email(cls, v: str) -> str:
        if '@' not in v:
            raise ValueError('invalid email')
        return v.lower()
    
    class Config:
        frozen = True  # Make immutable
```

**Never pass raw dictionaries for structured data:**
```python
# ❌ Raw dictionaries
def create_user(data: dict[str, any]) -> None:
    name = data.get('name')  # No validation, no IDE support
    
# ✅ Pydantic models
def create_user(data: UserAccount) -> None:
    name = data.user_id  # Validated, typed, IDE-friendly
```

### 4. Error Handling Strategy

**Raise exceptions, don't return error codes:**

```python
# ✅ Exceptions with specific types
class ValidationError(Exception):
    """Raised when data validation fails."""
    pass

def validate_config(config: dict[str, any]) -> Config:
    if 'api_key' not in config:
        raise ValidationError("Missing required field: api_key")
    return Config(**config)

# ❌ Error codes
def validate_config(config: dict[str, any]) -> tuple[Config | None, str]:
    if 'api_key' not in config:
        return None, "error: missing api_key"
    return Config(**config), "ok"
```

**Exception hierarchy:**
- Create custom exception classes for domain errors
- Inherit from appropriate base exceptions
- Include context in exception messages
- Use `raise ... from` to preserve exception chains

### 5. Separation of Concerns

**Layer architecture clearly:**

```
src/
├── domain/          # Business logic, no external dependencies
│   ├── models.py    # Pydantic models
│   └── services.py  # Pure business logic
├── adapters/        # External integrations
│   ├── database.py
│   └── api_client.py
├── application/     # Use cases, orchestration
│   └── workflows.py
└── interface/       # Entry points (CLI, API)
    └── cli.py
```

**Dependency direction:** interface → application → domain ← adapters

### 6. NumPy for Time-Series Data

**All time-series data use `np.ndarray` with consistent shape:**

```python
import numpy as np
from numpy.typing import NDArray

def calculate_moving_average(
    values: NDArray[np.float64],  # shape: (n_timesteps,)
    window: int
) -> NDArray[np.float64]:
    """Calculate moving average over time-series data."""
    if values.ndim != 1:
        raise ValueError(f"Expected 1D array, got {values.ndim}D")
    
    return np.convolve(values, np.ones(window)/window, mode='valid')
```

## Architecture Patterns

### Repository Pattern

For data access abstraction:

```python
from typing import Protocol
from abc import abstractmethod

class UserRepository(Protocol):
    @abstractmethod
    def get_by_id(self, user_id: str) -> User | None: ...
    
    @abstractmethod
    def save(self, user: User) -> None: ...

class InMemoryUserRepository:
    def __init__(self):
        self._users: dict[str, User] = {}
    
    def get_by_id(self, user_id: str) -> User | None:
        return self._users.get(user_id)
    
    def save(self, user: User) -> None:
        self._users[user.user_id] = user
```

### Dependency Injection

Use explicit dependency injection, avoid global state:

```python
# ✅ Dependency injection
class DataService:
    def __init__(
        self,
        repository: UserRepository,
        cache: Cache,
        logger: logging.Logger
    ):
        self._repository = repository
        self._cache = cache
        self._logger = logger

# ❌ Global state or service locator
class DataService:
    def __init__(self):
        self._repository = global_repository  # Hidden dependency
```

### Strategy Pattern

For algorithm variation:

```python
from typing import Protocol

class ValidationStrategy(Protocol):
    def validate(self, data: dict[str, any]) -> bool: ...

class StrictValidator:
    def validate(self, data: dict[str, any]) -> bool:
        return all(k in data for k in ['id', 'name', 'email'])

class LenientValidator:
    def validate(self, data: dict[str, any]) -> bool:
        return 'id' in data

class DataProcessor:
    def __init__(self, validator: ValidationStrategy):
        self._validator = validator
    
    def process(self, data: dict[str, any]) -> ProcessedData:
        if not self._validator.validate(data):
            raise ValidationError("Data validation failed")
        return ProcessedData(**data)
```

## Code Quality Standards

### Function Design

**Keep functions small and focused:**
- Single responsibility
- 1-20 lines typically (excluding docstrings)
- If > 30 lines, consider splitting
- Maximum 3-4 parameters (use objects for more)

**Write clear docstrings:**

```python
def calculate_metric(
    values: NDArray[np.float64],
    threshold: float,
    normalize: bool = False
) -> dict[str, float]:
    """Calculate statistical metrics for time-series data.
    
    Args:
        values: Time-series data with shape (n_timesteps,)
        threshold: Minimum value for anomaly detection
        normalize: Whether to normalize values to [0, 1] range
    
    Returns:
        Dictionary containing:
            - 'mean': Average value
            - 'std': Standard deviation
            - 'anomalies': Count of values exceeding threshold
    
    Raises:
        ValueError: If values array is empty or not 1D
    """
    pass
```

### Testing Strategy

**Test pyramid:**
- Unit tests: Fast, isolated, test single functions/classes
- Integration tests: Test component interactions
- End-to-end tests: Test complete workflows

```python
import pytest
from unittest.mock import Mock

def test_data_processor_validates_input():
    """Test that DataProcessor validates input using validator."""
    # Arrange
    validator = Mock(spec=ValidationStrategy)
    validator.validate.return_value = False
    processor = DataProcessor(validator)
    
    # Act & Assert
    with pytest.raises(ValidationError):
        processor.process({'invalid': 'data'})
    
    validator.validate.assert_called_once()
```

### Performance Optimization

**Profile before optimizing:**

```python
import cProfile
import pstats

def profile_function(func):
    """Decorator to profile function performance."""
    def wrapper(*args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()
        result = func(*args, **kwargs)
        profiler.disable()
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        stats.print_stats(10)
        return result
    return wrapper
```

**Optimization priorities:**
1. Algorithm complexity (O(n) vs O(n²))
2. Data structures (dict vs list for lookups)
3. Batch operations (vectorization with NumPy)
4. Caching/memoization
5. Micro-optimizations (last resort)

## Refactoring Checklist

When refactoring code, systematically address:

1. **Type safety**: Add comprehensive type hints
2. **Data models**: Replace dicts with Pydantic models
3. **Error handling**: Replace error codes with exceptions
4. **Separation**: Extract mixed concerns into layers
5. **Dependencies**: Make implicit dependencies explicit
6. **Testing**: Add tests before refactoring (if missing)
7. **Documentation**: Update docstrings and comments
8. **Complexity**: Break down large functions/classes

## Code Review Focus Areas

When reviewing code, prioritize:

1. **Correctness**: Does it work? Are edge cases handled?
2. **Type safety**: Are types comprehensive and accurate?
3. **Architecture**: Proper layering and dependency direction?
4. **Testability**: Can this code be easily tested?
5. **Readability**: Is intent clear? Are names descriptive?
6. **Performance**: Any obvious inefficiencies?
7. **Security**: Input validation? Sensitive data handling?

## Anti-Patterns to Avoid

- God objects (classes that do everything)
- Circular dependencies between modules
- Mutable global state
- Catching generic `Exception` without re-raising
- Using `type: ignore` without explanation
- Magic numbers without named constants
- Copy-paste code duplication
- Over-engineering simple solutions

## References

For detailed patterns and examples:
- **Design patterns**: See [patterns.md](references/patterns.md)
- **Testing patterns**: See [testing.md](references/testing.md)
- **Performance optimization**: See [performance.md](references/performance.md)
