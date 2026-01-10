# Testing Patterns Reference

## Test Organization

### Arrange-Act-Assert (AAA) Pattern

Structure tests with clear phases:

```python
import pytest
from unittest.mock import Mock

def test_user_service_creates_user():
    """Test user creation with AAA pattern."""
    # Arrange: Set up test data and dependencies
    repository = Mock()
    email_service = Mock()
    user_service = UserService(repository, email_service)
    user_data = UserData(name="Alice", email="alice@example.com")
    
    # Act: Execute the operation
    result = user_service.create_user(user_data)
    
    # Assert: Verify outcomes
    assert result.name == "Alice"
    repository.save.assert_called_once()
    email_service.send_welcome.assert_called_once()
```

### Test Fixtures

Share setup across tests:

```python
import pytest
from pathlib import Path

@pytest.fixture
def temp_database():
    """Provide temporary database for tests."""
    db = Database.create_temporary()
    yield db
    db.cleanup()

@pytest.fixture
def sample_data():
    """Provide sample data."""
    return [
        {'id': 1, 'name': 'Alice'},
        {'id': 2, 'name': 'Bob'},
    ]

@pytest.fixture
def data_file(tmp_path: Path):
    """Create temporary data file."""
    file_path = tmp_path / "data.json"
    file_path.write_text('{"key": "value"}')
    return file_path

def test_with_fixtures(temp_database, sample_data, data_file):
    """Test using multiple fixtures."""
    # Fixtures are automatically set up and torn down
    assert temp_database.is_connected()
    assert len(sample_data) == 2
    assert data_file.exists()
```

### Parametrized Tests

Test multiple inputs efficiently:

```python
import pytest

@pytest.mark.parametrize('input_value,expected', [
    (0, 0),
    (1, 1),
    (2, 4),
    (3, 9),
    (-2, 4),
])
def test_square_function(input_value: int, expected: int):
    """Test square function with multiple inputs."""
    assert square(input_value) == expected

@pytest.mark.parametrize('text', [
    'hello@example.com',
    'user+tag@domain.co.uk',
    'test.email@sub.example.com',
])
def test_email_validation_valid(text: str):
    """Test email validation with valid emails."""
    assert is_valid_email(text)

@pytest.mark.parametrize('text', [
    'invalid',
    '@example.com',
    'user@',
    'user @example.com',
])
def test_email_validation_invalid(text: str):
    """Test email validation with invalid emails."""
    assert not is_valid_email(text)
```

## Mocking Patterns

### Mock Objects

Replace dependencies with controlled doubles:

```python
from unittest.mock import Mock, MagicMock, patch

def test_service_with_mock_repository():
    """Test service with mocked repository."""
    # Create mock with specific behavior
    repository = Mock()
    repository.get_by_id.return_value = User(id="123", name="Alice")
    
    service = UserService(repository)
    user = service.get_user("123")
    
    assert user.name == "Alice"
    repository.get_by_id.assert_called_once_with("123")

def test_with_side_effects():
    """Test handling of exceptions from dependencies."""
    repository = Mock()
    repository.save.side_effect = DatabaseError("Connection failed")
    
    service = UserService(repository)
    
    with pytest.raises(ServiceError) as exc_info:
        service.create_user(UserData(name="Alice"))
    
    assert "Connection failed" in str(exc_info.value)
```

### Spy Pattern

Verify calls while using real implementation:

```python
from unittest.mock import Mock, wraps

def test_processor_uses_validator():
    """Verify processor calls validator correctly."""
    # Create spy wrapping real implementation
    real_validator = StrictValidator()
    spy_validator = Mock(wraps=real_validator)
    
    processor = DataProcessor(spy_validator)
    
    # Real validation happens
    result = processor.process({'id': '1', 'name': 'Alice', 'email': 'alice@example.com'})
    
    # Can verify calls
    spy_validator.validate.assert_called_once()
    
    # Real behavior occurred
    assert result.name == 'Alice'
```

### Patch Decorator

Replace modules or objects temporarily:

```python
from unittest.mock import patch, mock_open

@patch('module.external_api.fetch_data')
def test_service_with_patched_api(mock_fetch):
    """Test service with patched external API."""
    mock_fetch.return_value = {'status': 'success'}
    
    service = DataService()
    result = service.get_remote_data()
    
    assert result['status'] == 'success'
    mock_fetch.assert_called_once()

@patch('builtins.open', new_callable=mock_open, read_data='file content')
def test_file_reader(mock_file):
    """Test file reading with mocked file."""
    content = read_file('data.txt')
    
    assert content == 'file content'
    mock_file.assert_called_once_with('data.txt', 'r')
```

## Test Data Builders

### Builder Pattern for Test Data

Create complex test objects easily:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Self

@dataclass
class User:
    id: str
    name: str
    email: str
    created_at: datetime
    is_active: bool = True
    roles: list[str] = field(default_factory=list)

class UserBuilder:
    """Builder for creating test User objects."""
    
    def __init__(self):
        self._id = "test-user-id"
        self._name = "Test User"
        self._email = "test@example.com"
        self._created_at = datetime(2024, 1, 1)
        self._is_active = True
        self._roles: list[str] = []
    
    def with_id(self, id: str) -> Self:
        self._id = id
        return self
    
    def with_name(self, name: str) -> Self:
        self._name = name
        return self
    
    def with_email(self, email: str) -> Self:
        self._email = email
        return self
    
    def inactive(self) -> Self:
        self._is_active = False
        return self
    
    def with_roles(self, *roles: str) -> Self:
        self._roles.extend(roles)
        return self
    
    def build(self) -> User:
        return User(
            id=self._id,
            name=self._name,
            email=self._email,
            created_at=self._created_at,
            is_active=self._is_active,
            roles=self._roles
        )

# Usage in tests
def test_admin_user():
    """Test admin user functionality."""
    admin = (UserBuilder()
             .with_name("Admin")
             .with_roles("admin", "moderator")
             .build())
    
    assert "admin" in admin.roles

def test_inactive_user():
    """Test inactive user handling."""
    inactive_user = UserBuilder().inactive().build()
    
    assert not inactive_user.is_active
```

### Factory Functions

Simple test data creation:

```python
def create_user(
    id: str = "user-123",
    name: str = "Test User",
    **kwargs
) -> User:
    """Factory function for test users."""
    defaults = {
        'email': f"{name.lower().replace(' ', '.')}@example.com",
        'created_at': datetime.now(),
        'is_active': True,
    }
    defaults.update(kwargs)
    return User(id=id, name=name, **defaults)

def test_user_service():
    """Test using factory function."""
    user = create_user(name="Alice", roles=["admin"])
    assert user.name == "Alice"
    assert "admin" in user.roles
```

## Integration Testing Patterns

### Database Testing

Test with real database:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

@pytest.fixture(scope='function')
def db_session():
    """Provide database session for tests."""
    # Create in-memory database
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    
    session = Session(engine)
    yield session
    
    session.rollback()
    session.close()

def test_repository_saves_user(db_session: Session):
    """Test repository saves user to database."""
    repository = SQLUserRepository(db_session)
    user = User(id="123", name="Alice", email="alice@example.com")
    
    repository.save(user)
    
    retrieved = repository.get_by_id("123")
    assert retrieved is not None
    assert retrieved.name == "Alice"
```

### API Testing

Test HTTP endpoints:

```python
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    """Provide test client."""
    app = create_app()
    return TestClient(app)

def test_create_user_endpoint(client: TestClient):
    """Test user creation endpoint."""
    response = client.post(
        "/users",
        json={"name": "Alice", "email": "alice@example.com"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Alice"
    assert "id" in data

def test_get_user_endpoint(client: TestClient):
    """Test get user endpoint."""
    # Create user first
    create_response = client.post(
        "/users",
        json={"name": "Bob", "email": "bob@example.com"}
    )
    user_id = create_response.json()["id"]
    
    # Get user
    response = client.get(f"/users/{user_id}")
    
    assert response.status_code == 200
    assert response.json()["name"] == "Bob"
```

### File System Testing

Use temporary files:

```python
import pytest
from pathlib import Path

def test_config_reader(tmp_path: Path):
    """Test configuration file reading."""
    # Create test config file
    config_file = tmp_path / "config.json"
    config_file.write_text('{"api_key": "test-key"}')
    
    # Test reading
    config = ConfigReader.load(config_file)
    
    assert config.api_key == "test-key"

def test_file_processor_creates_output(tmp_path: Path):
    """Test file processor creates output file."""
    input_file = tmp_path / "input.txt"
    output_file = tmp_path / "output.txt"
    input_file.write_text("test data")
    
    processor = FileProcessor()
    processor.process(input_file, output_file)
    
    assert output_file.exists()
    assert "processed" in output_file.read_text()
```

## Async Testing

### Testing Async Functions

```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_async_data_fetcher():
    """Test async data fetching."""
    fetcher = AsyncDataFetcher()
    
    result = await fetcher.fetch('https://api.example.com/data')
    
    assert result is not None
    assert 'data' in result

@pytest.mark.asyncio
async def test_concurrent_operations():
    """Test multiple concurrent async operations."""
    service = AsyncService()
    
    results = await asyncio.gather(
        service.operation_1(),
        service.operation_2(),
        service.operation_3(),
    )
    
    assert len(results) == 3
    assert all(r.success for r in results)
```

### Mocking Async Functions

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_service_with_mocked_async_call():
    """Test service with mocked async dependency."""
    mock_client = AsyncMock()
    mock_client.fetch_data.return_value = {'status': 'ok'}
    
    service = DataService(mock_client)
    result = await service.get_data()
    
    assert result['status'] == 'ok'
    mock_client.fetch_data.assert_called_once()

@pytest.mark.asyncio
@patch('module.async_function', new_callable=AsyncMock)
async def test_with_patched_async_function(mock_async):
    """Test with patched async function."""
    mock_async.return_value = 'mocked result'
    
    result = await call_async_function()
    
    assert result == 'mocked result'
```

## Property-Based Testing

Use hypothesis for property testing:

```python
from hypothesis import given, strategies as st

@given(st.integers(), st.integers())
def test_addition_commutative(a: int, b: int):
    """Test that addition is commutative."""
    assert add(a, b) == add(b, a)

@given(st.lists(st.integers(), min_size=1))
def test_sort_idempotent(numbers: list[int]):
    """Test that sorting twice gives same result."""
    sorted_once = sorted(numbers)
    sorted_twice = sorted(sorted_once)
    assert sorted_once == sorted_twice

@given(st.text(min_size=1))
def test_encode_decode_roundtrip(text: str):
    """Test encoding and decoding is lossless."""
    encoded = encode(text)
    decoded = decode(encoded)
    assert decoded == text
```

## Test Doubles Reference

**Dummy**: Passed but never used
```python
def test_with_dummy():
    processor = DataProcessor(dummy_logger)  # Never called
```

**Stub**: Returns fixed data
```python
def test_with_stub():
    stub_repo = Mock()
    stub_repo.get_all.return_value = [user1, user2]
```

**Spy**: Records calls while delegating to real implementation
```python
def test_with_spy():
    spy = Mock(wraps=real_validator)
    spy.validate(data)
    spy.validate.assert_called_once()
```

**Mock**: Pre-programmed with expectations
```python
def test_with_mock():
    mock_service = Mock()
    mock_service.process.return_value = expected_result
```

**Fake**: Working implementation (lighter than real)
```python
class FakeRepository:
    def __init__(self):
        self._data = {}
    
    def save(self, user: User) -> None:
        self._data[user.id] = user
```
