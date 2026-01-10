# Test Suite for h-mem (Cognitive Agent Memory System)

This directory contains the comprehensive test suite for the h-mem project, implementing Test-Driven Development (TDD) principles based on the design specification in `docs/design.md`.

## Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Shared pytest fixtures and utilities
├── test_acceptance.py       # Acceptance tests (smoke tests)
├── test_models.py           # Unit tests for data models
├── test_config.py           # Unit tests for configuration
├── test_memory_system.py    # Unit tests for core MemorySystem
└── README.md               # This file
```

## Test Categories

### Acceptance Tests (Smoke Tests)

Based on design.md Section 7 "System Acceptance Plan":

1. **Goldfish Test** (`test_acceptance.py::TestGoldfishMemoryPersistence`)
   - Validates memory folding mechanism
   - Ensures information is preserved despite token overflow
   - Tests context compression and summary generation

2. **Don't Repeat Mistakes Test** (`test_acceptance.py::TestDontRepeatMistakes`)
   - Validates episodic memory storage and retrieval
   - Ensures agent learns from past failures
   - Tests success/failure ranking in recall

3. **Change of Mind Test** (`test_acceptance.py::TestChangeOfMind`)
   - Validates semantic memory conflict resolution
   - Ensures knowledge updates are handled correctly
   - Tests optimistic locking and version tracking

4. **Sherlock Test** (`test_acceptance.py::TestSherlockInduction`)
   - Validates deep reflection and principle extraction
   - Ensures cross-task pattern recognition
   - Tests minimum evidence requirements

### Unit Tests

- **`test_models.py`**: Tests for Pydantic models (Memory, Event, Principle, etc.)
- **`test_config.py`**: Tests for configuration loading and validation
- **`test_memory_system.py`**: Tests for core MemorySystem interface

## Running Tests

### Install Test Dependencies

```bash
# Install test dependencies
uv pip install --group test
```

### Run All Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with coverage report
uv run pytest --cov=src/hmem --cov-report=html
```

### Run Specific Test Categories

```bash
# Run only acceptance tests
uv run pytest -m acceptance

# Run only unit tests
uv run pytest -m unit

# Run tests for specific phase
uv run pytest -m phase1

# Run specific test file
uv run pytest tests/test_acceptance.py

# Run specific test class
uv run pytest tests/test_acceptance.py::TestGoldfishMemoryPersistence

# Run specific test method
uv run pytest tests/test_acceptance.py::TestGoldfishMemoryPersistence::test_memory_folding_with_token_overflow
```

### Test Output Options

```bash
# Show print statements
uv run pytest -s

# Show only failed tests
uv run pytest --tb=short

# Show summary of all test outcomes
uv run pytest -ra

# Stop at first failure
uv run pytest -x

# Run last failed tests only
uv run pytest --lf
```

## Test Fixtures

Common fixtures are defined in `conftest.py`:

- **`memory_config`**: Test configuration with reasonable defaults
- **`memory_system`**: MemorySystem instance for testing
- **`mock_llm`**: Mocked LLM with canned responses
- **`sample_events`**: Sample Event objects for testing
- **`sample_memories`**: Sample Memory objects for testing
- **`sample_semantic_triple`**: Sample SemanticTriple for testing

## Test Markers

Tests are marked with categories for easy filtering:

- `@pytest.mark.acceptance`: Acceptance tests from design.md
- `@pytest.mark.unit`: Unit tests for individual components
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.slow`: Tests that take significant time
- `@pytest.mark.phase1`: Phase 1 (MVP) features
- `@pytest.mark.phase2`: Phase 2 (Semantic layer) features
- `@pytest.mark.phase3`: Phase 3 (Intelligence evolution) features

## Test Philosophy

### Test-Driven Development (TDD)

These tests are written following TDD principles:

1. **Red**: Write failing tests first based on requirements
2. **Green**: Implement minimal code to make tests pass
3. **Refactor**: Improve code while keeping tests green

### Current Status

Many tests currently:
- Check that methods exist and have correct signatures
- Skip with `pytest.skip()` when features are not yet implemented
- Use `NotImplementedError` to document planned functionality

As implementation progresses, tests will evolve from:
- **Skeleton tests** (checking interfaces exist) → 
- **Behavioral tests** (validating correct behavior) →
- **Performance tests** (ensuring SLA compliance)

### Writing New Tests

When adding new tests:

1. **Follow English-only policy**: All code, comments, docstrings must be in English
2. **Use type hints**: Leverage modern Python syntax (`dict`, `list`, not `Dict`, `List`)
3. **Document test purpose**: Include clear docstrings explaining what is being tested
4. **Mark appropriately**: Use pytest markers to categorize tests
5. **Keep tests focused**: Each test should validate one specific behavior
6. **Use fixtures**: Leverage shared fixtures from `conftest.py`

## Coverage Goals

Target coverage goals by implementation phase:

- **Phase 1 (MVP)**: 
  - Core interfaces: 100%
  - Models: 100%
  - Memory system basics: 80%

- **Phase 2 (Semantic layer)**:
  - Semantic store: 90%
  - Conflict resolution: 95%
  - Overall: 85%

- **Phase 3 (Intelligence evolution)**:
  - Reflection agent: 85%
  - Full system: 85%+

## Continuous Integration

Tests should be run:

1. **Before committing**: `make check` (includes tests once implemented)
2. **In CI pipeline**: Automated on every push
3. **Before merging**: Required to pass all tests
4. **Nightly**: Full regression suite with slow tests

## Troubleshooting

### Common Issues

**Import errors**:
```bash
# Ensure src is in Python path
export PYTHONPATH=/home/runner/work/h-mem/h-mem/src:$PYTHONPATH
```

**Fixture not found**:
- Check that `conftest.py` is in the tests directory
- Ensure fixture names match exactly

**Tests skipped**:
- Many tests are currently skipped because features are not implemented
- This is expected during Phase 1 development

**Mock not working**:
- Ensure `pytest-mock` is installed
- Use `mocker` fixture provided by pytest-mock

## References

- Design Document: `docs/design.md`
- Pytest Documentation: https://docs.pytest.org/
- Pytest-mock: https://pytest-mock.readthedocs.io/
- Coverage.py: https://coverage.readthedocs.io/
