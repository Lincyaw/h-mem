## Development Conventions

## Role

You are an expert Python developer familiar with best practices in code quality, testing, and code architecture design. You write clean, maintainable, and well-documented code. 

### Deisgn Architecture

Please refer to `docs/design.md`. This project is a new project, so feel free to refactor code aggressively to maintain high quality. No backward compatibility is needed.


### Development Workflow

```bash
# Run main program (use uv exclusively)
uv run python main.py

# Quality checks (MANDATORY before commit)
make check
```

### Code Style and Language

**Critical: All code, comments, docstrings, and commit messages MUST be in English. Chinese is strictly prohibited.**

- Use Pydantic models; never pass raw dictionaries for business data
- All time-series data use `np.ndarray` with shape `(n_timesteps,)`
- Error handling: Raise exceptions instead of returning error codes
- **Type hints**: Use modern syntax (`dict`, `list`, `tuple`, `set`) instead of deprecated `typing.Dict`, `typing.List`, etc. Use `|` for unions instead of `Union[]`
  - ✅ `def func(data: dict[str, int]) -> list[str] | None:`
  - ❌ `def func(data: Dict[str, int]) -> Optional[List[str]]:`
- **Python package management**: Use `uv` exclusively (not pip/poetry/conda)
- **Code quality checks are mandatory before committing**: `make check`
- DO NOT write .md documents unless user specifically requests it
- Use type hints extensively; avoid `Any` type
- **This is a new project; refactor code aggressively to maintain high quality, no backward compatibility needed**
- Do not add comments everywhere, only where necessary for clarity/design rationale


# Reference 

## Code-Documentation Mapping Index

This index tracks the relationship between code modules and documentation files, enabling synchronized updates when requirements change.

### Architecture Layers Mapping

#### Layer 1: Perception & Working Memory
| Code Module | Key Classes | Documentation | Key Concepts |
|---|---|---|---|
| `perception/sensory_buffer.py` | `SensoryBuffer` | [Components: Context Manager](docs/components.md#a-context-manager), [Architecture](docs/architecture.md) | Buffer management, message intake |
| `perception/strategies/folding.py` | `FoldingStrategy`, `TokenBasedFolder`, `TimeWindowFolder` | [Components: Folding Strategies](docs/components.md#a-context-manager) | Memory folding, context compression |
| `perception/strategies/token_based.py` | `TokenBasedFolder` | [Components: TokenBasedFolder](docs/components.md#a-context-manager) | Token-based threshold management |
| `perception/strategies/time_window.py` | `TimeWindowFolder` | [Components: TimeWindowFolder](docs/components.md#a-context-manager) | Time-window based compression |

**When to sync:**
- Adding new folding strategy → Update `perception/strategies/` and add to [Components doc](docs/components.md)
- Changing folding trigger logic → Update threshold explanation in `memory.yaml` config section

#### Layer 2: Hippocampus (Processing)
| Code Module | Key Classes | Documentation | Key Concepts |
|---|---|---|---|
| `core/memory_system.py` | `MemorySystem` | [Interfaces: MemorySystem API](docs/interfaces.md), [Design Philosophy](docs/design-philosophy.md) | Public API, core methods |
| `hippocampus/encoder.py` | `MemoryEncoder` | [Components: Memory Encoder](docs/components.md), [Workflows: Consolidation](docs/workflows.md#flow-2-cold-path) | Event extraction, structuring |
| `hippocampus/consolidator.py` | `Consolidator` | [Components: Consolidator](docs/components.md), [Workflows: Consolidation](docs/workflows.md#flow-2-cold-path) | Conflict resolution, forgetting, weight updates |
| `hippocampus/retrieval_engine.py` | `RetrievalEngine`, `FeedbackSignal` | [Workflows: Retrieval](docs/workflows.md#flow-1-hot-path), [Interfaces: Memory markup](docs/interfaces.md) | Two-phase retrieval, feedback extraction |
| `hippocampus/projector.py` | `EventProjector` | [Components: Event Projection](docs/components.md) | Triple extraction, graph construction |
| `hippocampus/reflection.py` / `agents/reflection.py` | `ReflectionAgent` | [Components: Deep Reflection](docs/components.md), [Workflows: Evolution](docs/workflows.md) | Principle induction, skill extraction |
| `hippocampus/topic_extraction.py` | Topic extraction logic | [Components: Topic Extraction](docs/components.md) | Semantic clustering |
| `hippocampus/policies/reflection.py` | Reflection policies | [Design Philosophy: Configuration](docs/design-philosophy.md) | Policy selection (threshold/cost-aware/multi-scale) |

**When to sync:**
- Adding new conflict resolution strategy → Update `consolidator.py` + [Components doc](docs/components.md) + `memory.yaml`
- Changing reflection trigger policy → Update `policies/reflection.py` + [Workflows: Evolution](docs/workflows.md) + `memory.yaml` feedback section
- Modifying retrieval ranking → Update `retrieval_engine.py` + [Workflows: Retrieval](docs/workflows.md#phase-2)

#### Layer 3: Long-Term Storage
| Code Module | Key Classes | Documentation | Key Concepts |
|---|---|---|---|
| `storage/episodic.py` | `EpisodicStore` | [Architecture: Episodic Store](docs/architecture.md) | Vector DB interface, similarity search |
| `storage/chroma_episodic.py` | `ChromaEpisodicStore` | [Architecture: Technology Stack](docs/architecture.md#3-technology-stack) | ChromaDB implementation, migration path |
| `storage/semantic.py` | `SemanticStoreProtocol` | [Architecture: Semantic Store](docs/architecture.md) | Graph DB interface, relationship queries |
| `storage/neo4j_semantic.py` | `Neo4jSemanticStore` | [Architecture: Neo4j Implementation](docs/architecture.md#3-technology-stack) | Neo4j specifics, Cypher queries |
| `storage/skill.py` | `SkillStore` | [Architecture: Skill Store](docs/architecture.md), [Interfaces: Skill model](docs/interfaces.md) | Procedural knowledge, key-value access |
| `storage/base.py` | Store protocols | [Architecture: Storage Layer](docs/architecture.md) | Common interfaces, abstraction |

**When to sync:**
- Migrating to new vector DB (e.g., Milvus) → Update `storage/episodic.py`, `storage/chroma_episodic.py`, [Architecture doc](docs/architecture.md#3-technology-stack), migration path
- Adding Neo4j features → Update `storage/neo4j_semantic.py` + [Architecture doc](docs/architecture.md)
- Changing skill storage structure → Update `storage/skill.py` + [Interfaces doc](docs/interfaces.md#skill-model)

### Core Data Models Mapping

| Model | File | Documentation | Usage |
|---|---|---|---|
| `Memory` | `models.py` | [Interfaces: Memory](docs/interfaces.md#memory-single-memory) | Retrieved memory with score, source, provenance |
| `Event` | `models.py` | [Interfaces: Event](docs/interfaces.md#event-situational-event) | Structured business event, outcome tracking |
| `Conversation` | `models.py` | [Interfaces: Conversation](docs/interfaces.md) | Raw input, level 0 in memory lineage |
| `Message` | `models.py` | [Interfaces: Message](docs/interfaces.md) | Single conversation turn |
| `Principle` | `models.py` | [Interfaces: Principle](docs/interfaces.md#principle-induced-principle) | Induced rule with evidence, weight, version |
| `SemanticTriple` | `models.py` | [Provenance: Semantic Graph](docs/provenance.md) | Knowledge graph representation (S-P-O) |
| `ConsolidationResult` | `models.py` | [Interfaces: ConsolidationResult](docs/interfaces.md#consolidationresult) | Consolidation operation statistics |

**When to sync:**
- Adding field to `Memory` → Update `models.py` definition + [Interfaces doc](docs/interfaces.md#memory-single-memory) + all storage layers that populate it
- Changing `Principle` weight mechanism → Update `models.py` + [Interfaces doc](docs/interfaces.md#principle) + [Workflows: Consolidation](docs/workflows.md) + `memory.yaml` feedback config
- Adding new memory source type → Update all of: `models.py`, `retrieval_engine.py` (feedback extraction regex), [Interfaces doc](docs/interfaces.md), [Provenance doc](docs/provenance.md)

### Configuration Mapping

| Config File | Code References | Documentation |
|---|---|---|
| `config/memory.yaml` | `config.py` → `MemoryConfig` | [Design Philosophy: Configuration](docs/design-philosophy.md#rule-of-silence), [Architecture: Constraints](docs/architecture.md) |
| Memory.retrieval config | `retrieval_engine.py`, `RetrievalEngine.recall()` | [Workflows: Retrieval](docs/workflows.md#flow-1), [Architecture: SLA](docs/architecture.md#2-system-constraints) |
| Memory.consolidation config | `consolidator.py`, `Consolidator.consolidate()` | [Workflows: Consolidation](docs/workflows.md#flow-2) |
| Memory.reflection config | `hippocampus/policies/reflection.py`, `ReflectionAgent` | [Components: Deep Reflection](docs/components.md), [Workflows: Evolution](docs/workflows.md#flow-3) |
| Memory.feedback config | `consolidator.py` (weight updates), `retrieval_engine.py` (feedback extraction) | [Workflows: Consolidation](docs/workflows.md#feedback-integration), [Design Philosophy](docs/design-philosophy.md) |

**When to sync:**
- Adding new config parameter → Update `config/memory.yaml` + `config.py` + relevant component code + [Design Philosophy: Configuration](docs/design-philosophy.md)

### Test Coverage Mapping

| Test File | Tests | Code Under Test | Documentation |
|---|---|---|---|
| `test_memory_system.py` | Core API tests | `core/memory_system.py` | [Interfaces: MemorySystem API](docs/interfaces.md), [Acceptance Testing](docs/acceptance-testing.md) |
| `test_neo4j_semantic.py` | Graph operations | `storage/neo4j_semantic.py` | [Architecture: Neo4j](docs/architecture.md) |
| `test_acceptance.py` | Acceptance criteria | All layers | [Acceptance Testing: 4 Test Cases](docs/acceptance-testing.md) |
| `test_provenance.py` | Lineage tracking | `models.py` + storage layers | [Provenance: Memory Lifecycle](docs/provenance.md) |
| `test_skill_store.py` | Skill operations | `storage/skill.py` | [Architecture: Skill Store](docs/architecture.md) |
| `test_config.py` | Configuration loading | `config.py` | [Design Philosophy: Configuration](docs/design-philosophy.md) |
| `test_models.py` | Model validation | `models.py` | [Interfaces: Data Models](docs/interfaces.md) |

**When to sync:**
- Adding new component → Add test file + update test mapping
- Changing component behavior → Update both test and corresponding documentation

### Common Refactoring Scenarios

#### Scenario 1: Adding a new memory source type
**Files to modify:**
1. `models.py` → Update `Memory.source` Literal type
2. `retrieval_engine.py` → Add regex pattern to `MEMORY_PATTERN` for feedback extraction
3. `storage/episodic.py` or `storage/semantic.py` → Handle new type in retrieval
4. `hippocampus/consolidator.py` → Handle weight updates for new type
5. `docs/interfaces.md` → Document new source type in Memory model
6. `docs/provenance.md` → Update hierarchy diagram if applicable
7. Tests → Add test cases in `test_acceptance.py` or `test_provenance.py`

#### Scenario 2: Changing retrieval ranking algorithm
**Files to modify:**
1. `strategies/ranking.py` → Update `HybridRanker` scoring logic
2. `hippocampus/retrieval_engine.py` → Adjust weight composition in `_rank_results()`
3. `docs/workflows.md` → Update [Phase 2: Ranking](docs/workflows.md#flow-1) description
4. `memory.yaml` → Add ranking configuration if needed
5. `docs/architecture.md` → Update SLA impact if performance changes
6. Tests → Add tests in test suite validating ranking order

#### Scenario 3: Implementing new reflection policy
**Files to modify:**
1. `hippocampus/policies/reflection.py` → Add new policy class
2. `config.py` → Add policy enum/config
3. `memory.yaml` → Add policy selection config
4. `docs/design-philosophy.md` → Document new policy in configuration section
5. `docs/workflows.md` → Update [Flow 3: Evolution Path](docs/workflows.md#flow-3) diagram if logic changes
6. Tests → Add tests in `test_acceptance.py` validating policy behavior

#### Scenario 4: Migrating storage backend
**Files to modify:**
1. Create new `storage/new_backend.py` implementing store protocol
2. Update `storage/__init__.py` factory function
3. Update `config.py` to support new backend selection
4. Update `memory.yaml` with new backend config
5. `docs/architecture.md` → Update [Technology Stack](docs/architecture.md#3-technology-stack) and migration path
6. Create new test file `test_new_backend_storage.py`
7. Update [acceptance tests](docs/acceptance-testing.md) if necessary

### Documentation File Dependencies

```
design.md (Navigation Hub)
├── design-philosophy.md (Unix principles, config-driven design)
├── architecture.md (3-layer architecture, constraints, tech stack)
│   ├── components.md (Detailed component implementations)
│   ├── workflows.md (4 core workflows, feedback integration)
│   └── interfaces.md (Data model definitions)
├── provenance.md (Memory lineage, 4-level hierarchy)
├── observability.md (Metrics, tracing, adaptive thresholds)
├── acceptance-testing.md (4 test scenarios)
└── implementation-history.md (Decision history, lessons learned)
```

**When updating:**
- Core architecture change → Update `design.md`, `architecture.md`, likely `workflows.md`
- New component → Update `components.md`, `architecture.md`, `interfaces.md` (if new models added)
- Config change → Update `config/memory.yaml`, `design-philosophy.md`, potentially `architecture.md`
- Test additions → Update `acceptance-testing.md`, test files
- Performance optimization → Update `architecture.md` SLA section, `observability.md`

### Key Sync Rules

1. **Model changes require 3-part sync:** `models.py` → Storage layers → Documentation
2. **Config changes require 4-part sync:** `config.py` → `memory.yaml` → Implementation → Documentation
3. **Workflow changes require 5-part sync:** Code logic → Tests → `workflows.md` → `architecture.md` → `design-philosophy.md` (if affected)
4. **New component always requires:** Code file → Storage/Config support → Test → Documentation (components.md + architecture.md)
5. **Storage backend changes:** Create impl → Update factory → Config → Architecture doc → Migration guide
