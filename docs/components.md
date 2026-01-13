# **Component Details & Responsibilities**

## **Layer 1: Perception & Working Memory**

Responsible for processing current interaction flows (inside-trail) and maintaining continuity of "consciousness".

### **A. SensoryBuffer - Sensory Buffer**

* **Responsibility:** Temporarily store raw conversation records, waiting for background consolidation processing.
* **Data Structure:** FIFO queue (deque implementation)
* **Capacity Limit:** Default 1000 messages (configurable)

**Key Operations:**
- `push()`: Add raw conversation to buffer
- `pop_batch()`: Batch extract conversations for processing

### **B. FoldingStrategy - Context Folding Strategy**

* **Responsibility:** Prevent context overflow by intelligently compressing while preserving key information.
* **Design Pattern:** Strategy pattern, supporting pluggable implementations

**Available Strategies:**

| Strategy | Trigger Condition | Use Case |
|----------|-------------------|----------|
| **TokenBasedFolder** | Token count exceeds threshold ratio (default 80%) | General conversations, token-sensitive scenarios |
| **TimeWindowFolder** | Oldest message exceeds time window (default 24h) | Long-running conversations spanning hours/days |

**Configuration Example:**
```yaml
memory:
  folding_strategy: "h_mem.strategies.TokenBasedFolder"
  folding_threshold: 0.8
```

**Threshold Design Considerations:**
- **Too low (0.6):** Frequent folding, losing details
- **Too high (0.95):** Late folding, risk of overflow
- **0.8 (default):** Balanced point, reserving 20% buffer for burst messages

---

## **Layer 2: Hippocampus Processing**

This is the system's **scheduling center**, responsible for transforming short-term memory into long-term memory and extracting wisdom.

### **C. MemoryEncoder - Memory Encoder**

* **Responsibility:** Transform unstructured conversations into structured data.
* **Processing Types:**
  * **Fact Extraction:** Identify entity relationships (e.g., User → Location → Beijing)
  * **Event Extraction:** Identify complete Task-Action-Result chains

### **D. Consolidator - Memory Consolidator**

* **Responsibility:** Simulate the "sleep" process, handling memory writing, conflict correction, and forgetting.
* **Trigger:** Synchronous (Phase 1), Asynchronous (Phase 3)
* **Input:** Structured events and facts
* **Output:** Database CRUD operations + statistics report

**Transaction Management:**
- **Concurrency Control:** Session-level locking to prevent concurrent consolidation
- **Lock Backend:** Pluggable design - file lock (single node) or Redis lock (distributed)

**Conflict Resolution (Optimistic Locking):**
- Semantic facts use version numbers for conflict detection
- On conflict: Update node, increment version, mark old edge invalid

**Error Handling Strategy:**

| Failure Type | Strategy |
|--------------|----------|
| LLM API failure | Raise MemoryError immediately (assumes LLM availability) |
| Event Log write failure | Raise error immediately |
| Derived view failure | Log and async retry |
| Network transient error | Exponential backoff (1s, 2s, 4s, max 3 retries) |
| Consecutive failures (5x) | Circuit breaker, fast fail |

**Event Sourcing Design:**
- **Event Log** serves as the single source of truth (append-only)
- Derived views (ChromaDB, Neo4j) are built asynchronously
- Supports complete audit trail and time-travel queries

### **E. Deep Reflection Agent** `[Experimental]`

* **Responsibility:** **Cross-task induction** and **experience refinement**. Core of generating "philosophy" and continuous optimization.
* **Mechanism:**
  1. **Clustering:** Periodically scan episodic memory, find N similar recent tasks
  2. **Abstraction:** Ignore details, extract common success patterns or failure causes
  3. **Generation:** Output a general "Principle" or "Skill Skeleton"
  4. **Refinement:** When a Skill/Principle accumulates sufficient feedback, trigger deep review

**Refinement Trigger Conditions:**

| Condition | Threshold | Description |
|-----------|-----------|-------------|
| Usage count | ≥ N (default 10) | Sufficient sample size |
| Negative feedback ratio | ≥ 30% | Priority trigger for problematic memories |
| Time window | Recent T days | Avoid using outdated data |
| Weight variance | Above threshold | Indicates unstable usage effectiveness |

**Pluggable Reflection Strategies:**

The system supports multi-scale reflection policies:
- **Immediate (session-level):** Episode count ≥ 10 within 1 day, similarity > 0.75
- **Daily (cross-session):** Episode count ≥ 50 within 1-7 days
- **Weekly (deep philosophy):** Episode count ≥ 100 over 7+ days

**Configuration Example:**
```yaml
reflection:
  policy: "MultiScalePolicy"
  immediate_threshold: 10    # Range: 5-20
  daily_threshold: 50        # Range: 30-100
  weekly_threshold: 100      # Range: 50-200
  similarity_threshold: 0.75 # Range: 0.7-0.85
```

---

## **Layer 3: Long-Term Storage**

Hybrid database architecture, storing different types of data in separate databases. Uses lightweight technology stack, prioritizing embedded solutions.

### **Storage Components Overview**

| Component | Implementation | Upgrade Option | Content | Cognitive Type |
|-----------|---------------|----------------|---------|----------------|
| **Episodic Store** | ChromaDB (embedded) | Milvus (distributed) | Event + embedding | Episodic memory (experiences) |
| **Semantic Store** | Neo4j (native graph) | PostgreSQL+AGE | Triple + Principle + Skill | Semantic memory (facts/wisdom) |
| **Index Store** | SQLite | - | IndexProfile, UsageRecord | Usage statistics |

### **F. EpisodicStore - Episodic Memory Storage**

* **Responsibility:** Store event vectors for similarity search
* **Index Lifecycle Management:**
  - Auto-trigger index rebuild when new insertions reach 10% of current size
  - Background async rebuild with atomic switch on completion
  - Old index deleted asynchronously after switch

### **G. SemanticStore (Neo4j) - Semantic Memory Storage**

* **Responsibility:** Store semantic triples, principles, and skills as unified graph structure
* **Content:**
  - **SemanticTriple:** Entity relationships (S-P-O)
  - **Principle:** Abstracted rules with provenance to source events
  - **Skill:** Procedure templates with provenance to principles/events
* **Advantages:**
  - Native graph traversal, no precomputed closure tables needed
  - Cypher query language is concise and intuitive
  - Supports vector indexing (Neo4j 5.x+)
  - **Complete provenance chain:** Skill → Principle → Events
* **Query Depth Limit:** Maximum 3 hops (hard limit to prevent recursive explosion)

### **H. IndexStore (SQLite) - Index Statistics Storage**

* **Responsibility:** High-frequency read/write of usage statistics
* **Tables:**
  - `index_profiles`: Memory usage statistics (usage_count, success_rate, weight)
  - `usage_records`: Individual usage records with sequence information
  - `associations`: Discovered memory relationships

---

**Related Documents:**
- [System Design Philosophy](design.md) - Design philosophy and core concepts
- [System Architecture](architecture.md) - Overall architecture, constraints and technology choices
- [Core Workflows](workflows.md) - How the system operates
- [Key Interfaces](interfaces.md) - Data model definitions and APIs
