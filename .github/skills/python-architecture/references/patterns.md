# Design Patterns Reference

## Creational Patterns

### Factory Pattern

Use when object creation logic is complex or varies:

```python
from typing import Protocol
from abc import ABC, abstractmethod

class Parser(Protocol):
    def parse(self, content: str) -> dict[str, any]: ...

class JSONParser:
    def parse(self, content: str) -> dict[str, any]:
        import json
        return json.loads(content)

class YAMLParser:
    def parse(self, content: str) -> dict[str, any]:
        import yaml
        return yaml.safe_load(content)

class ParserFactory:
    """Factory for creating appropriate parser based on file type."""
    
    _parsers: dict[str, type[Parser]] = {
        'json': JSONParser,
        'yaml': YAMLParser,
        'yml': YAMLParser,
    }
    
    @classmethod
    def create(cls, file_type: str) -> Parser:
        parser_class = cls._parsers.get(file_type.lower())
        if not parser_class:
            raise ValueError(f"Unsupported file type: {file_type}")
        return parser_class()

# Usage
parser = ParserFactory.create('json')
data = parser.parse('{"key": "value"}')
```

### Builder Pattern

Use for complex object construction with many optional parameters:

```python
from dataclasses import dataclass, field
from typing import Self

@dataclass
class QueryConfig:
    table: str
    columns: list[str] = field(default_factory=list)
    where: list[str] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    limit: int | None = None

class QueryBuilder:
    """Builder for constructing SQL-like queries."""
    
    def __init__(self, table: str):
        self._config = QueryConfig(table=table)
    
    def select(self, *columns: str) -> Self:
        self._config.columns.extend(columns)
        return self
    
    def where(self, condition: str) -> Self:
        self._config.where.append(condition)
        return self
    
    def order_by(self, *columns: str) -> Self:
        self._config.order_by.extend(columns)
        return self
    
    def limit(self, n: int) -> Self:
        self._config.limit = n
        return self
    
    def build(self) -> QueryConfig:
        return self._config

# Usage
query = (QueryBuilder('users')
         .select('name', 'email')
         .where('age > 18')
         .order_by('created_at')
         .limit(10)
         .build())
```

### Singleton Pattern

Use sparingly, only for truly global resources:

```python
from threading import Lock

class DatabaseConnection:
    """Thread-safe singleton for database connection."""
    
    _instance: 'DatabaseConnection | None' = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """Initialize connection (called once)."""
        self._connection = self._create_connection()
    
    def _create_connection(self):
        # Create actual connection
        pass

# Better alternative: Dependency injection
class DatabaseService:
    def __init__(self, connection: DatabaseConnection):
        self._connection = connection  # Injected, not global
```

## Structural Patterns

### Adapter Pattern

Convert one interface to another:

```python
from typing import Protocol

class ModernAPI(Protocol):
    def fetch_data(self, query: dict[str, any]) -> list[dict[str, any]]: ...

class LegacySystem:
    """Old system with different interface."""
    
    def get_records(self, sql: str) -> list[tuple]:
        # Legacy implementation
        pass

class LegacyAdapter:
    """Adapt legacy system to modern API."""
    
    def __init__(self, legacy: LegacySystem):
        self._legacy = legacy
    
    def fetch_data(self, query: dict[str, any]) -> list[dict[str, any]]:
        # Convert modern query to legacy SQL
        sql = self._convert_to_sql(query)
        records = self._legacy.get_records(sql)
        # Convert tuples to dicts
        return [self._convert_record(r) for r in records]
    
    def _convert_to_sql(self, query: dict[str, any]) -> str:
        # Conversion logic
        pass
    
    def _convert_record(self, record: tuple) -> dict[str, any]:
        # Conversion logic
        pass
```

### Decorator Pattern

Add behavior without modifying original class:

```python
from typing import Protocol
import time
import logging

class DataFetcher(Protocol):
    def fetch(self, url: str) -> bytes: ...

class HTTPFetcher:
    def fetch(self, url: str) -> bytes:
        # Actual HTTP fetch
        pass

class CachedFetcher:
    """Decorator adding caching to any fetcher."""
    
    def __init__(self, fetcher: DataFetcher):
        self._fetcher = fetcher
        self._cache: dict[str, bytes] = {}
    
    def fetch(self, url: str) -> bytes:
        if url in self._cache:
            return self._cache[url]
        data = self._fetcher.fetch(url)
        self._cache[url] = data
        return data

class LoggedFetcher:
    """Decorator adding logging to any fetcher."""
    
    def __init__(self, fetcher: DataFetcher, logger: logging.Logger):
        self._fetcher = fetcher
        self._logger = logger
    
    def fetch(self, url: str) -> bytes:
        self._logger.info(f"Fetching: {url}")
        start = time.time()
        data = self._fetcher.fetch(url)
        elapsed = time.time() - start
        self._logger.info(f"Fetched {len(data)} bytes in {elapsed:.2f}s")
        return data

# Usage: Stack decorators
fetcher = LoggedFetcher(
    CachedFetcher(
        HTTPFetcher()
    ),
    logger=logging.getLogger(__name__)
)
```

### Facade Pattern

Simplify complex subsystem:

```python
from typing import Protocol

class EmailService(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...

class SMSService(Protocol):
    def send_sms(self, phone: str, message: str) -> None: ...

class PushService(Protocol):
    def push(self, user_id: str, title: str, message: str) -> None: ...

class NotificationFacade:
    """Simplified interface for all notification types."""
    
    def __init__(
        self,
        email: EmailService,
        sms: SMSService,
        push: PushService
    ):
        self._email = email
        self._sms = sms
        self._push = push
    
    def notify_user(
        self,
        user_id: str,
        message: str,
        channels: list[str]
    ) -> None:
        """Send notification via specified channels."""
        if 'email' in channels:
            self._email.send(
                to=self._get_user_email(user_id),
                subject="Notification",
                body=message
            )
        if 'sms' in channels:
            self._sms.send_sms(
                phone=self._get_user_phone(user_id),
                message=message
            )
        if 'push' in channels:
            self._push.push(
                user_id=user_id,
                title="Notification",
                message=message
            )
```

## Behavioral Patterns

### Observer Pattern

Notify dependents of state changes:

```python
from typing import Protocol, Callable

class Observer(Protocol):
    def update(self, data: dict[str, any]) -> None: ...

class Subject:
    """Observable subject that notifies observers."""
    
    def __init__(self):
        self._observers: list[Observer] = []
        self._state: dict[str, any] = {}
    
    def attach(self, observer: Observer) -> None:
        self._observers.append(observer)
    
    def detach(self, observer: Observer) -> None:
        self._observers.remove(observer)
    
    def notify(self) -> None:
        for observer in self._observers:
            observer.update(self._state)
    
    def set_state(self, state: dict[str, any]) -> None:
        self._state = state
        self.notify()

class ConcreteObserver:
    def __init__(self, name: str):
        self._name = name
    
    def update(self, data: dict[str, any]) -> None:
        print(f"{self._name} received: {data}")

# Usage
subject = Subject()
observer1 = ConcreteObserver("Observer1")
observer2 = ConcreteObserver("Observer2")

subject.attach(observer1)
subject.attach(observer2)
subject.set_state({'event': 'update', 'value': 42})
```

### Command Pattern

Encapsulate requests as objects:

```python
from typing import Protocol
from abc import abstractmethod

class Command(Protocol):
    @abstractmethod
    def execute(self) -> None: ...
    
    @abstractmethod
    def undo(self) -> None: ...

class Document:
    def __init__(self):
        self.content = ""
    
    def insert_text(self, text: str, position: int) -> None:
        self.content = (
            self.content[:position] + 
            text + 
            self.content[position:]
        )
    
    def delete_text(self, start: int, length: int) -> None:
        self.content = (
            self.content[:start] + 
            self.content[start + length:]
        )

class InsertCommand:
    def __init__(self, document: Document, text: str, position: int):
        self._document = document
        self._text = text
        self._position = position
    
    def execute(self) -> None:
        self._document.insert_text(self._text, self._position)
    
    def undo(self) -> None:
        self._document.delete_text(self._position, len(self._text))

class CommandHistory:
    def __init__(self):
        self._history: list[Command] = []
        self._current = -1
    
    def execute(self, command: Command) -> None:
        # Remove any commands after current position
        self._history = self._history[:self._current + 1]
        command.execute()
        self._history.append(command)
        self._current += 1
    
    def undo(self) -> None:
        if self._current >= 0:
            self._history[self._current].undo()
            self._current -= 1
    
    def redo(self) -> None:
        if self._current < len(self._history) - 1:
            self._current += 1
            self._history[self._current].execute()
```

### Chain of Responsibility

Pass requests along a chain of handlers:

```python
from typing import Protocol
from abc import abstractmethod

class Request:
    def __init__(self, data: dict[str, any]):
        self.data = data
        self.handled = False

class Handler(Protocol):
    @abstractmethod
    def handle(self, request: Request) -> None: ...

class BaseHandler:
    def __init__(self):
        self._next: Handler | None = None
    
    def set_next(self, handler: Handler) -> Handler:
        self._next = handler
        return handler
    
    def handle(self, request: Request) -> None:
        if self._should_handle(request):
            self._do_handle(request)
            request.handled = True
        elif self._next:
            self._next.handle(request)
    
    @abstractmethod
    def _should_handle(self, request: Request) -> bool: ...
    
    @abstractmethod
    def _do_handle(self, request: Request) -> None: ...

class AuthenticationHandler(BaseHandler):
    def _should_handle(self, request: Request) -> bool:
        return 'user_token' in request.data
    
    def _do_handle(self, request: Request) -> None:
        # Validate token
        request.data['authenticated'] = True

class ValidationHandler(BaseHandler):
    def _should_handle(self, request: Request) -> bool:
        return request.data.get('authenticated', False)
    
    def _do_handle(self, request: Request) -> None:
        # Validate request data
        request.data['validated'] = True

# Usage
auth_handler = AuthenticationHandler()
validation_handler = ValidationHandler()
auth_handler.set_next(validation_handler)

request = Request({'user_token': 'abc123', 'action': 'create'})
auth_handler.handle(request)
```

## Modern Python Patterns

### Context Manager Pattern

Manage resources with automatic cleanup:

```python
from typing import Self
from contextlib import contextmanager

class DatabaseTransaction:
    """Context manager for database transactions."""
    
    def __init__(self, connection):
        self._connection = connection
        self._in_transaction = False
    
    def __enter__(self) -> Self:
        self._connection.begin()
        self._in_transaction = True
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._connection.commit()
        else:
            self._connection.rollback()
        self._in_transaction = False
        return False

# Function-based context manager
@contextmanager
def temporary_config(config: dict[str, any]):
    """Temporarily modify configuration."""
    original = get_config()
    try:
        set_config(config)
        yield config
    finally:
        set_config(original)

# Usage
with temporary_config({'debug': True}):
    # Code runs with debug enabled
    pass
# Debug automatically restored
```

### Async Iterator Pattern

For asynchronous iteration:

```python
from typing import AsyncIterator
import asyncio

class AsyncDataStream:
    """Async iterator for streaming data."""
    
    def __init__(self, source: str):
        self._source = source
        self._position = 0
    
    def __aiter__(self) -> AsyncIterator[bytes]:
        return self
    
    async def __anext__(self) -> bytes:
        await asyncio.sleep(0.1)  # Simulate async I/O
        
        if self._position >= 100:
            raise StopAsyncIteration
        
        chunk = self._fetch_chunk(self._position)
        self._position += len(chunk)
        return chunk
    
    def _fetch_chunk(self, position: int) -> bytes:
        # Fetch data chunk
        pass

# Usage
async def process_stream():
    async for chunk in AsyncDataStream('data.bin'):
        await process_chunk(chunk)
```
