# **Core Workflows**

This document describes how indexes are built and maintained. For API contracts and data flow overview, see [architecture.md](architecture.md).

---

## **1. Overview: Index Lifecycle**

```mermaid
flowchart LR
    subgraph BUILD["BUILD<br/>(Offline)"]
        B1[Extract Events]
    end

    subgraph QUERY["QUERY<br/>(Online)"]
        Q1[Lookup Indexes]
    end

    subgraph FEEDBACK["FEEDBACK<br/>(Online)"]
        F1[Track Usage]
    end

    subgraph MAINTAIN["MAINTAIN<br/>(Offline)"]
        M1[Evolve/Decay]
    end

    BUILD --> QUERY --> FEEDBACK --> MAINTAIN
    MAINTAIN -.->|Improve| BUILD

    style BUILD fill:#fff3e0
    style QUERY fill:#e1f5fe
    style FEEDBACK fill:#e8f5e9
    style MAINTAIN fill:#fce4ec
```

| Phase | Trigger | Latency | Purpose |
|-------|---------|---------|---------|
| **Build** | `remember()` | Async | Create L1/L2/L3 indexes |
| **Query** | `recall()` | < 200ms | Lookup and rank |
| **Feedback** | Usage in conversation | Immediate | Track success/failure |
| **Maintain** | Batch schedule | Async | Evolve, decay, cleanup |

---

## **2. Index Building**

### **2.1 L1: Event Extraction**

**Trigger:** New conversation in queue

**Input:** Raw conversation messages

**Output:** Structured Event records in ChromaDB

```mermaid
sequenceDiagram
    participant Q as Queue
    participant ENC as Encoder
    participant LLM as LLM
    participant L1 as ChromaDB

    Q->>ENC: Pop conversation batch
    ENC->>LLM: Extract events (prompt)
    Note over LLM: Identify Task-Action-Result<br/>patterns in conversation
    LLM-->>ENC: Event list

    loop Each Event
        ENC->>L1: Store with embedding
        Note over L1: Vector index updated
    end
```

**Extraction Rules:**
| Pattern | Event Type | Example |
|---------|------------|---------|
| Task + Action + Success | Positive experience | "Used selenium, worked" |
| Task + Action + Failure | Negative experience | "requests.get failed on JS site" |
| User preference stated | Preference | "I prefer dark mode" |
| Correction/update | Knowledge update | "Actually, use v2 API now" |

### **2.2 L2: Fact Extraction**

**Trigger:** Event extracted (chained from L1)

**Input:** L1 Events

**Output:** SemanticTriple in Neo4j

```mermaid
sequenceDiagram
    participant ENC as Encoder
    participant LLM as LLM
    participant L2 as Neo4j

    ENC->>LLM: Extract facts from event
    Note over LLM: Identify entity relationships<br/>(Subject-Predicate-Object)
    LLM-->>ENC: Triple list

    loop Each Triple
        ENC->>L2: Check existing
        alt Conflict detected
            L2->>L2: Resolve (see §4.2)
        else New fact
            L2->>L2: Insert with parent_id
        end
    end
```

**Fact Types:**
| Category | Predicate Examples | Storage |
|----------|-------------------|---------|
| Tool-Domain | GOOD_FOR, REQUIRES, REPLACES | Graph edge |
| User-Preference | LIKES, PREFERS, AVOIDS | Graph edge |
| Entity-Attribute | HAS_VERSION, LOCATED_AT | Graph edge |

### **2.3 L3: Wisdom Induction**

**Trigger:** Batch schedule OR pattern detected

**Input:** Cluster of similar L1 events

**Output:** Principle or Skill in Neo4j

```mermaid
sequenceDiagram
    participant SCH as Scheduler
    participant REF as Reflector
    participant L1 as ChromaDB
    participant LLM as LLM
    participant L3 as Neo4j

    SCH->>REF: Trigger induction
    REF->>L1: Find similar events (clustering)
    L1-->>REF: Event cluster (N >= 3)

    REF->>LLM: Induce pattern
    Note over LLM: Abstract common pattern<br/>from success/failure cases
    LLM-->>REF: Principle or Skill

    REF->>L3: Store with parent_ids
    Note over L3: Links to source events<br/>for provenance
```

**Induction Triggers:**
| Condition | Action | Rationale |
|-----------|--------|-----------|
| 3+ similar events | Induce Principle | Enough evidence |
| 5+ similar successes | Induce Skill template | Repeatable pattern |
| 3+ similar failures | Induce anti-pattern | Learn from mistakes |

---

## **3. Index Query (Retrieval)**

### **3.1 Parallel Lookup**

```mermaid
sequenceDiagram
    participant A as Agent
    participant RE as Retrieval Engine
    participant L3 as Neo4j (L3)
    participant L2 as Neo4j (L2)
    participant L1 as ChromaDB (L1)
    participant RANK as Ranker

    A->>RE: recall(query)

    par Parallel
        RE->>L3: Semantic match (Principle/Skill)
        RE->>L2: Graph traversal (Triples)
        RE->>L1: Vector similarity (Events)
    end

    L3-->>RE: Candidates
    L2-->>RE: Candidates
    L1-->>RE: Candidates

    RE->>RANK: Merge & rank
    RANK-->>RE: Sorted results
    RE-->>A: Memory[] with tags
```

### **3.2 Ranking Formula**

```
final_score = w1×similarity + w2×recency + w3×quality + w4×exploration
```

| Factor | Weight | Source | Description |
|--------|--------|--------|-------------|
| **Similarity** | 0.4 | Vector/semantic match | How relevant to query |
| **Recency** | 0.2 | `last_used_at` | Prefer recent knowledge |
| **Quality** | 0.3 | `success_rate × confidence` | Prefer proven knowledge |
| **Exploration** | 0.1 | `1/log(usage_count)` | Try under-used knowledge |

### **3.3 Result Tagging**

Results are tagged for feedback tracking:
```xml
<principle id="p_001">Dynamic sites need browser automation</principle>
<skill id="s_001">Use selenium with explicit waits</skill>
<memory id="e_001">Last time selenium worked for JS site</memory>
```

---

## **4. Index Maintenance**

### **4.1 Feedback Collection**

**Trigger:** `remember()` with conversation containing used memories

**Mechanism:** Parse XML tags to extract usage outcomes

```mermaid
sequenceDiagram
    participant CON as Consolidator
    participant FB as Feedback Parser
    participant IDX as IndexStore

    CON->>FB: Parse conversation
    Note over FB: Find: <skill id="xxx">...<br/>with outcome signals
    FB-->>CON: Feedback signals

    loop Each signal
        CON->>IDX: Update IndexProfile
        Note over IDX: usage_count++<br/>success_count++ or failure_count++
    end
```

**Feedback Signals:**
| Signal | Detection | IndexProfile Update |
|--------|-----------|---------------------|
| Memory used, task succeeded | Positive context after tag | `success_count++` |
| Memory used, task failed | Negative context after tag | `failure_count++` |
| Memory recalled but not used | No follow-up action | `usage_count++` only |

### **4.2 Conflict Resolution**

When new facts conflict with existing ones:

```mermaid
flowchart TD
    A[New Fact] --> B{Conflicts with existing?}
    B -->|No| C[Insert new]
    B -->|Yes| D{Temporal fact?}
    D -->|Yes| E[Supersede: mark old deprecated]
    D -->|No| F{Confidence difference > 0.3?}
    F -->|Yes| G[Higher confidence wins]
    F -->|No| H[Weight voting or coexist]
```

| Strategy | When | Example |
|----------|------|---------|
| **Supersede** | Preferences, status | "I now prefer tea" replaces "I like coffee" |
| **Higher wins** | Different confidence | Expert opinion vs casual mention |
| **Coexist** | Context-dependent | "Tool A for X, Tool B for Y" |

### **4.3 Index Evolution**

**Trigger:** Batch schedule (e.g., every 50 `remember()` calls)

```mermaid
sequenceDiagram
    participant SCH as Scheduler
    participant EVO as Evolver
    participant IDX as IndexStore
    participant LLM as LLM
    participant L3 as Neo4j

    SCH->>EVO: Trigger evolution check
    EVO->>IDX: Query candidates
    Note over IDX: WHERE usage >= 10<br/>AND success_rate < 0.5
    IDX-->>EVO: Candidate list

    loop Each candidate
        EVO->>EVO: Determine action
        alt Refine
            EVO->>LLM: Generate improved version
            LLM-->>EVO: Refined content
            EVO->>L3: Create v2, deprecate v1
        else Deprecate
            EVO->>L3: Mark deprecated
        else Split
            EVO->>LLM: Analyze for split
            EVO->>L3: Create sub-indexes
        end
    end
```

**Evolution Types:**
| Type | Trigger | Action | Result |
|------|---------|--------|--------|
| **Refine** | `usage >= 10 AND success_rate < 0.5` | Add details/constraints | v1 → v2 |
| **Deprecate** | `usage >= 20 AND success_rate < 0.3` | Mark unusable | `is_deprecated = true` |
| **Split** | High variance in contexts | Break into specific cases | v1 → [v1a, v1b] |
| **Merge** | `cooccurrence > 0.8` | Combine related | [A, B] → C |

### **4.4 Index Decay (Forgetting)**

**Trigger:** Daily batch job

**Purpose:** Reduce noise from outdated knowledge

```
weight(t) = weight_0 × exp(-λ × days_since_last_use)

Where λ varies by index type:
- Principle: 0.01 (slow decay, wisdom is stable)
- Skill: 0.03 (medium decay)
- Event: 0.05 (fast decay, details fade)
```

**Protection Shields:**
| Shield | Condition | Effect |
|--------|-----------|--------|
| High weight | `weight > 5.0` | Skip decay |
| Recent use | `last_used_at < 7 days` | Skip decay |
| High confidence | `confidence > 0.9` | Half decay rate |
| Has descendants | Active indexes derived from it | Cannot delete |

---

## **5. Complete Data Flow**

```mermaid
stateDiagram-v2
    [*] --> Queue: remember()

    state "Index Building" as BUILD {
        Queue --> EventExtract: Async
        EventExtract --> ChromaDB: Events
        EventExtract --> FactExtract: Chain
        FactExtract --> Neo4j_Facts: Triples
        ChromaDB --> Induce: Batch
        Induce --> Neo4j_Wisdom: Principle/Skill
    }

    state "Index Query" as QUERY {
        Recall --> Lookup: recall()
        Lookup --> ChromaDB: Vector
        Lookup --> Neo4j_Facts: Graph
        Lookup --> Neo4j_Wisdom: Semantic
        ChromaDB --> Rank
        Neo4j_Facts --> Rank
        Neo4j_Wisdom --> Rank
        Rank --> Return: Memory[]
    }

    state "Index Maintenance" as MAINTAIN {
        Return --> Feedback: Usage tracked
        Feedback --> SQLite: Update IndexProfile
        SQLite --> Evolution: Batch check
        Evolution --> Neo4j_Wisdom: Refine/Deprecate
        SQLite --> Decay: Daily
        Decay --> ChromaDB: Weight update
        Decay --> Neo4j_Facts: Weight update
        Decay --> Neo4j_Wisdom: Weight update
    }

    Return --> [*]
```

---

## **6. Timing Summary**

| Operation | Frequency | Trigger | Storage Affected |
|-----------|-----------|---------|------------------|
| Event extraction | Per `remember()` | Queue consumer | ChromaDB |
| Fact extraction | Per event | Chained | Neo4j |
| Wisdom induction | Every N events | Batch/pattern | Neo4j |
| Feedback update | Per `remember()` | XML parsing | SQLite |
| Evolution check | Every 50 remembers | Batch | All |
| Decay job | Daily | Scheduler | All |
| Cleanup | Weekly | Scheduler | All |

---

**Related Documents:**
- [System Architecture](architecture.md) - API contracts and data flow overview
- [Interface Definitions](interfaces.md) - Data model specifications
- [Acceptance Testing](acceptance-testing.md) - Verification test cases
