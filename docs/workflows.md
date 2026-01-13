# **Core Workflows**

## **Workflow 1: Hot Path - Retrieval with Exploration (The Retrieval Loop)**

*Scenario: Agent is generating a response. Supports progressive result return.*

**Key Features:** Hybrid ranking + Adaptive exploration + Usage recording

**Two-Phase Design:**
- **Phase 1 (Sync fast retrieval):** Query memory cache + Bloom Filter, P95 < 50ms
- **Phase 2 (Async deep retrieval):** Vector similarity + Graph queries, P95 < 500ms

```mermaid
sequenceDiagram
    participant A as Agent
    participant MS as MemorySystem
    participant RE as Retrieval Engine
    participant GDB as Semantic (Neo4j)
    participant VDB as Episodic (ChromaDB)
    participant RANK as Hybrid Ranker
    participant SQL as SQLite

    A->>MS: recall(query)
    activate MS

    MS->>RE: Request memories
    activate RE

    par Parallel retrieval
        RE->>GDB: Search entities & principles (Cypher)
        RE->>VDB: Search similar episodes (Vector)
    end

    GDB-->>RE: Facts & Principles (with IndexProfile)
    VDB-->>RE: Top-K Episodes (with IndexProfile)

    RE->>RANK: Hybrid ranking with exploration
    Note over RANK: score = w1*similarity<br/>+ w2*recency<br/>+ w3*importance<br/>+ w4*quality_score<br/>+ w5*exploration_bonus

    RANK-->>RE: Ranked memories

    RE-->>MS: Augmented context
    deactivate RE

    MS->>SQL: Record usage (UsageRecord)
    Note over SQL: memory_id, session_id,<br/>query, rank_position,<br/>sequence_position

    MS-->>A: Return memories (with XML tags)
    Note over A: <skill id="xxx">content</skill><br/><principle id="yyy">content</principle>

    deactivate MS
```

### **Hybrid Ranking Formula**

The ranking combines multiple signals:

| Signal | Weight | Description |
|--------|--------|-------------|
| **Similarity** | 0.4 | Vector similarity score |
| **Recency** | 0.15 | Time decay factor |
| **Importance** | 0.15 | Base importance weight |
| **Quality** | 0.2 | success_rate × confidence from IndexProfile |
| **Exploration** | 0.1 | Bonus for low-usage memories |

### **Adaptive Exploration Rate**

The exploration rate decays as the knowledge base matures:
- **Early stage (small KB):** ~20% exploration
- **Mature stage (large KB):** ~5% exploration
- **Decay formula:** `rate = initial_rate / (1 + total_usage / 1000)`

---

## **Workflow 2: Cold Path - Consolidation & Index Update (The Consolidation Loop)**

*Scenario: After conversation ends or during system idle. Async execution.*

**Key Features:** Feedback collection from XML tags + Index update + Evolution trigger check

```mermaid
sequenceDiagram
    participant Trigger as Scheduler/SessionEnd
    participant MS as MemorySystem
    participant ENC as Memory Encoder
    participant CON as Consolidator
    participant FB as Feedback Collector
    participant IDX as Index Manager
    participant GDB as Neo4j
    participant VDB as ChromaDB
    participant SQL as SQLite

    Trigger->>MS: Trigger consolidation (session_id)

    MS->>ENC: Get session log
    activate ENC
    ENC->>ENC: Extract facts & events
    ENC-->>CON: Structured data
    deactivate ENC

    activate CON
    loop Process each Fact
        CON->>GDB: Check existence/conflict
        alt Conflict
            GDB->>GDB: Update node, mark old edge invalid
        else Consistent
            GDB->>GDB: Increase weight (Reinforce)
        end
    end

    CON->>VDB: Store new Events (Embedding)
    deactivate CON

    MS->>FB: Extract feedback from XML tags
    activate FB
    Note over FB: Parse conversation for:<br/><skill id="xxx" outcome="success"><br/><principle id="yyy" outcome="failure">
    FB-->>MS: Feedback signals
    deactivate FB

    MS->>IDX: Update index profiles
    activate IDX

    loop For each feedback signal
        IDX->>SQL: Get IndexProfile
        IDX->>SQL: Update statistics
        Note over SQL: success_count++<br/>or failure_count++<br/>last_used_at = now()

        IDX->>IDX: Recalculate weight
        Note over IDX: weight = f(success_rate, confidence)
    end

    IDX->>IDX: Check evolution triggers
    loop For memories needing evolution
        alt needs_refinement (usage >= 10 AND success_rate < 0.5)
            IDX->>IDX: Schedule refinement task
        else should_deprecate (usage >= 20 AND success_rate < 0.3)
            IDX->>GDB: Mark as deprecated
        end
    end

    deactivate IDX

    MS->>GDB: Execute decay cleanup (optional)
```

### **Feedback Signal Format**

Agent marks memory usage outcomes in conversation using XML tags:
```
<skill id="xxx" outcome="success">skill content</skill>
<principle id="yyy" outcome="failure">principle content</principle>
```

The Feedback Collector parses these tags to extract:
- `memory_id`: The used memory's identifier
- `outcome`: success / failure
- `source_type`: skill / principle / memory

### **Weight Calculation**

Weight is derived from IndexProfile statistics:
- **Base weight:** 1.0
- **Quality factor:** success_rate × confidence
- **Weight range:** [0.1, 10.0]
- **Formula:** `weight = base + quality_factor × 9.0`

---

## **Workflow 3: Evolution Path - Induction & Philosophy Extraction (The Induction Loop)**

*Scenario: Periodically (e.g., weekly) or after N task accumulations.*

```mermaid
sequenceDiagram
    participant SCH as Scheduler
    participant REF as Deep Reflection Agent
    participant VDB as Episodic (ChromaDB)
    participant GDB as Semantic (Neo4j)

    SCH->>REF: Trigger induction (Topic: "Debugging")
    activate REF
    REF->>VDB: Cluster recent N similar tasks
    VDB-->>REF: Episode list

    REF->>REF: LLM analyze commonalities (Abstraction)
    Note right of REF: "Discovery: Write tests before<br/>fixing code has higher success rate"

    REF->>GDB: Write new Principle (with IndexProfile)
    Note right of GDB: Create: (Agent)-[FOLLOWS]->(Rule)<br/>Initialize IndexProfile
    deactivate REF
```

---

## **Workflow 4: Memory Evolution (Refinement, Split, Merge, Deprecate)**

*Scenario: When evolution triggers are met. Async execution.*

### **Evolution Types**

| Type | Description | Trigger Condition | Result |
|------|-------------|-------------------|--------|
| **Refinement** | Add details, examples, constraints | `usage >= 10 AND success_rate < 0.5` | v1 → v2 |
| **Split** | Break coarse memory into finer pieces | `usage >= 10 AND high variance` | v1 → [v1a, v1b] |
| **Merge** | Combine frequently co-occurring memories | `cooccurrence_rate > 0.8` | [A, B] → C |
| **Deprecate** | Mark as obsolete | `usage >= 20 AND success_rate < 0.3` | deprecated = true |

```mermaid
sequenceDiagram
    participant HOOK as Evolution Hook
    participant EVO as Memory Evolver
    participant SQL as SQLite
    participant GDB as Neo4j
    participant VDB as ChromaDB
    participant LLM as LLM Engine

    HOOK->>EVO: Trigger evolution check
    activate EVO

    EVO->>SQL: Query memories needing evolution
    Note over SQL: WHERE (usage >= 10 AND success_rate < 0.5)<br/>OR (usage >= 20 AND success_rate < 0.3)
    SQL-->>EVO: Candidate list

    loop For each candidate
        EVO->>EVO: Determine evolution type

        alt Refinement needed
            EVO->>SQL: Get usage history
            SQL-->>EVO: UsageRecord list

            EVO->>LLM: Request refinement
            Note over LLM: Prompt:<br/>- Original content<br/>- Success/failure cases<br/>Task: Add details, examples

            LLM-->>EVO: Refined content

            EVO->>GDB: Create new version
            Note over GDB: Memory v2 -[REFINED_FROM]-> v1

            EVO->>SQL: Initialize new IndexProfile
            EVO->>VDB: Create new embedding
            EVO->>GDB: Mark v1 deprecated

        else Deprecation needed
            EVO->>GDB: Mark deprecated
            Note over GDB: is_deprecated = true

        else Split needed
            EVO->>LLM: Request split analysis
            LLM-->>EVO: Sub-memories

            loop For each sub-memory
                EVO->>GDB: Create sub-memory
                Note over GDB: sub -[SPLIT_FROM]-> original
            end

        else Merge needed
            EVO->>LLM: Request merge
            LLM-->>EVO: Merged content

            EVO->>GDB: Create merged memory
            Note over GDB: merged -[MERGED_FROM]-> [A, B]
        end
    end

    deactivate EVO
```

### **Version Evolution Relationships (Neo4j)**

| Relationship | Meaning | Example |
|--------------|---------|---------|
| `REFINED_FROM` | Improved version | v2 → v1 |
| `SPLIT_FROM` | Split from coarse | [v1a, v1b] → v1 |
| `MERGED_FROM` | Combined from multiple | v3 → [v1, v2] |

---

## **Workflow 5: Association Discovery**

*Scenario: Periodically (e.g., every 50 remembers or weekly).*

### **Association Types**

| Type | Meaning | Detection Method | Neo4j Representation |
|------|---------|------------------|---------------------|
| **CAUSES** | A failed → B succeeded | Sequential failure-success pattern | `(A)-[:CAUSES]->(B)` |
| **COMPLEMENTS** | A and B used together successfully | Co-occurrence in same subtask | `(A)-[:COMPLEMENTS]-(B)` |
| **FOLLOWED_BY** | A then B (subtask order) | Sequential pattern across subtasks | `(A)-[:FOLLOWED_BY]->(B)` |

```mermaid
sequenceDiagram
    participant HOOK as Association Hook
    participant AD as Association Discovery
    participant SQL as SQLite
    participant GDB as Neo4j

    HOOK->>AD: Trigger association discovery
    activate AD

    AD->>SQL: Get recent UsageRecords
    Note over SQL: GROUP BY session_id<br/>ORDER BY sequence_position
    SQL-->>AD: Usage sequences

    AD->>AD: Mine patterns
    Note over AD: 1. COMPLEMENTS: co-occurrence<br/>2. CAUSES: failure → success<br/>3. FOLLOWED_BY: subtask sequence

    loop For each discovered association
        AD->>GDB: Check if exists
        alt New association
            AD->>GDB: Create relationship
            Note over GDB: (A)-[:CAUSES {confidence, support}]->(B)
        else Existing
            AD->>GDB: Update confidence/support
        end
    end

    deactivate AD
```

### **Association-Aware Retrieval Enhancement**

When retrieving memories, the system can leverage discovered associations:
1. For top results, find complementary memories
2. Apply slight score penalty (e.g., ×0.8) to complementary results
3. Return enhanced result set

---

## **Memory Lifecycle State Diagram**

```mermaid
stateDiagram-v2
    [*] --> SensoryBuffer: User input / Environment perception

    state "Working Memory" as WM {
        SensoryBuffer --> ContextWindow: Inject processing
        ContextWindow --> MemoryFolding: Capacity overflow
        MemoryFolding --> ContextWindow: Summary backfill
    }

    ContextWindow --> Consolidation: Session end

    state "Long-Term Consolidation" as LC {
        Consolidation --> FactExtraction: Extract semantics
        Consolidation --> EventEncoding: Extract episodes

        FactExtraction --> SemanticStore: Write/Update
        EventEncoding --> EpisodicStore: Write
    }

    state "Index & Evolution" as IE {
        Consolidation --> FeedbackCollection: Extract from XML tags
        FeedbackCollection --> IndexUpdate: Update IndexProfile

        IndexUpdate --> EvolutionCheck: Check triggers
        EvolutionCheck --> Refinement: needs_refinement
        EvolutionCheck --> Deprecation: should_deprecate
        EvolutionCheck --> Split: high variance
        EvolutionCheck --> Merge: high cooccurrence

        Refinement --> NewVersion: Create v2
        Split --> SubMemories: Create sub-memories
        Merge --> MergedMemory: Create merged
    }

    state "Association Discovery" as AD {
        IndexUpdate --> PatternMining: Batch trigger
        PatternMining --> AssociationStorage: Store relationships
    }

    SemanticStore --> Recall: Retrieved
    EpisodicStore --> Recall: Retrieved

    Recall --> UsageTracking: Record usage
    UsageTracking --> IndexUpdate: Incremental update

    NewVersion --> SemanticStore: Store new version
    SubMemories --> SemanticStore: Store sub-memories
    MergedMemory --> SemanticStore: Store merged
    AssociationStorage --> SemanticStore: Store relationships

    note right of IndexUpdate
        Index update is continuous:
        - Record usage on each recall
        - Update stats on each remember
        - Batch evolution check
    end note
```

---

## **Storage Responsibilities Summary**

### **SQLite - High-frequency structured data**
- IndexProfile: Memory usage statistics
- UsageRecord: Individual usage records with sequence information
- Association metadata (confidence, support counts)

### **Neo4j - Graph relationships**
- Memory nodes with content and version info
- Version evolution relationships (REFINED_FROM, SPLIT_FROM, MERGED_FROM)
- Association relationships (CAUSES, COMPLEMENTS, FOLLOWED_BY)
- Semantic triples (subject-predicate-object)

### **ChromaDB - Vector retrieval**
- Memory embeddings for similarity search
- Metadata filtering support

---

## **Index Refresh Timing Summary**

| Timing | Operation | Frequency | Storage |
|--------|-----------|-----------|---------|
| **Immediate (recall)** | Create UsageRecord | Each recall | SQLite |
| **Immediate (remember)** | Extract feedback from XML | Each remember | - |
| **Short-term (post-remember)** | Update IndexProfile | Each consolidation | SQLite |
| **Medium-term (batch)** | Evolution check & execution | Every N remembers | All |
| **Medium-term (batch)** | Association discovery | Every N remembers | Neo4j |
| **Long-term (periodic)** | Cleanup low-quality memories | Weekly | All |

---

**Related Documents:**
- [System Design Philosophy](design.md) - Design philosophy and core concepts
- [System Architecture](architecture.md) - Overall architecture and technical choices
- [Component Details](components.md) - Component responsibilities and implementations
- [Key Interface Definitions](interfaces.md) - Data models and API interfaces
- [Memory Provenance](provenance.md) - Memory provenance and hierarchical semantic graph
