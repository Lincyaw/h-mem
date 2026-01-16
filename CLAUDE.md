# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

h-mem is a **Cognitive Agent Memory System (CAMS)** - a sophisticated memory system for AI agents inspired by cognitive neuroscience principles. It implements a three-layer memory architecture based on the Atkinson-Shiffrin memory model.

## Essential Commands

### Development Workflow
```bash
# Install dependencies (use uv exclusively - not pip/poetry/conda)
uv pip install -e ".[dev]"

# Run quality checks (MANDATORY before commit)
make check

# Run tests
make test

# Run specific test categories
pytest tests/test_acceptance.py -m acceptance
pytest tests/test_models.py -v

# Run with coverage
pytest --cov=src/hmem --cov-report=html
```

### Code Quality Requirements
- **Type hints**: Use modern syntax (`dict`, `list`, `tuple`, `set`) instead of deprecated `typing.Dict`, `typing.List`, etc.
- **Use `|` for unions** instead of `Union[]`
- **All code, comments, docstrings, and commit messages MUST be in English**
- **Use Pydantic models**; never pass raw dictionaries for business data
- **Error handling**: Raise exceptions instead of returning error codes
- **Agent message format**: All LangChain agent calls (HumanMessage, AIMessage, SystemMessage) MUST use `content` as a list of dicts, not a string. Example: `HumanMessage(content=[{"type": "text", "text": "..."}])` instead of `HumanMessage(content="...")`

## Architecture Overview

### Three-Layer Memory Architecture
1. **Sensory Memory** (Perception Layer) - `src/hmem/perception/`
   - SensoryBuffer manages working memory with folding strategies
   - Folding strategies: TokenBasedFolder, TimeWindowFolder

2. **Working Memory** (Hippocampus Processing) - `src/hmem/hippocampus/`
   - MemoryEncoder: Extracts structured events from conversations
   - Consolidator: Handles memory consolidation and conflict resolution
   - RetrievalEngine: Two-phase retrieval with feedback integration
   - ReflectionAgent: Deep reflection for principle induction

3. **Long-Term Memory** (Storage Layer) - `src/hmem/storage/`
   - Episodic Store: ChromaDB for vector similarity search
   - Semantic Store: Neo4j graph database for relationships
   - Skill Store: Key-value storage for procedural knowledge

### Key Components
- **MemorySystem** (`core/memory_system.py`): Core orchestrator implementing the public API
- **Data Models** (`models.py`): Memory, Event, Principle, SemanticTriple, Conversation
- **Configuration** (`config.py`, `config/memory.yaml`): Centralized config management
- **Ranking Strategies** (`strategies/ranking.py`): Hybrid ranking for retrieval results

### Core Workflows
1. **Hot Path (Retrieval)**: Fast memory recall with two-phase ranking
2. **Cold Path (Consolidation)**: Background memory processing and storage
3. **Evolution Path (Reflection)**: Deep analysis for principle induction
4. **Feedback Integration**: Continuous learning from usage patterns

## Testing Strategy

### Four Standardized Acceptance Tests
1. **Goldfish Test**: Memory persistence and folding behavior
2. **Don't Repeat Mistakes Test**: Experience reuse across sessions
3. **Change of Mind Test**: Knowledge updates and conflict resolution
4. **Sherlock Test**: Cross-task induction and principle extraction

### Test Markers
- `acceptance`: Acceptance tests based on design.md
- `unit`: Unit tests for individual components
- `integration`: Integration tests for component interactions
- `phase1/2/3`: Tests corresponding to implementation phases

## Important Development Notes

### When Modifying Code
1. **Model changes require 3-part sync**: `models.py` → Storage layers → Documentation
2. **Config changes require 4-part sync**: `config.py` → `memory.yaml` → Implementation → Documentation
3. **New components require**: Code file → Storage/Config support → Test → Documentation

### Common Refactoring Patterns
- Adding new memory source type: Update models, retrieval regex, storage layers, documentation
- Changing retrieval ranking: Update HybridRanker, adjust weights, update workflows doc
- New reflection policy: Add to policies/, update config, document in workflows
- Storage migration: Create new impl, update factory, config, architecture doc

### Documentation Mapping
- `docs/design.md`: Navigation hub for all documentation
- `docs/architecture.md`: Three-layer architecture and constraints
- `docs/components.md`: Detailed component implementations
- `docs/workflows.md`: Four core workflows and feedback integration
- `docs/interfaces.md`: Data model definitions and APIs
- `docs/acceptance-testing.md`: Four test scenarios implementation

### Technology Stack
- **Vector Store**: ChromaDB (episodic memory)
- **Graph Store**: Neo4j (semantic relationships)
- **LLM Integration**: LiteLLM for unified API
- **Package Management**: UV (exclusively)
- **Type Checking**: MyPy in strict mode
- **Testing**: Pytest with comprehensive coverage