# **Cognitive Agent Memory System (CAMS) - Design Documentation**

A memory system for AI agents: **fast in, fast out, smart indexing offline**.

---

## **📚 Documentation Structure**

### **Core Documents** (Start Here)

| # | Document | Focus | Key Questions Answered |
|---|----------|-------|------------------------|
| 1 | **[Architecture](architecture.md)** ⭐ | API + Data Flow | What are the inputs/outputs? How does data flow? |
| 2 | **[Workflows](workflows.md)** ⭐ | Index Building + Maintenance | How are indexes built? How do they evolve? |

### **Reference Documents**

| # | Document | Focus | When to Read |
|---|----------|-------|--------------|
| 3 | [Interface Definitions](interfaces.md) | Data Models + APIs | When implementing |
| 4 | [Component Details](components.md) | Component Responsibilities | When debugging |
| 5 | [Acceptance Testing](acceptance-testing.md) | Test Cases | When validating |

### **Deep Dive Documents**

| # | Document | Focus | When to Read |
|---|----------|-------|--------------|
| 6 | [Design Philosophy](design-philosophy.md) | Why decisions were made | When extending |
| 7 | [Memory Provenance](provenance.md) | Version tracking | When tracing |
| 8 | [Observability](observability.md) | Metrics + Logging | When operating |

---

## **🎯 System Overview**

```mermaid
flowchart TB
    subgraph FAST["FAST PATH (Online)"]
        direction LR
        R1[/"remember(conversation)"/] --> Q[Queue] --> S1[/"session_id"/]
        R2[/"recall(query)"/] --> I[Index] --> M[/"Memory[]"/]
    end

    FAST -.->|Async| BUILD

    subgraph BUILD["INDEX BUILDING (Offline)"]
        direction LR
        C[Conversation] --> L1[(L1: Events<br/>ChromaDB)]
        L1 --> L2[(L2: Facts<br/>Neo4j)]
        L2 --> L3[(L3: Wisdom<br/>Neo4j)]
    end

    style FAST fill:#e1f5fe
    style BUILD fill:#fff3e0
```

**Key Insight:** Skill and Principle are not independent data — they are **indexes** derived from Events to accelerate future retrieval.

---

## **📖 Reading Guide**

**If you want to...**

| Goal | Read |
|------|------|
| Understand the API | [Architecture](architecture.md) §2 |
| See how data flows | [Architecture](architecture.md) §3 |
| Learn index building | [Workflows](workflows.md) §2 |
| Understand ranking | [Workflows](workflows.md) §3 |
| Learn about forgetting | [Workflows](workflows.md) §4.4 |
| Implement a component | [Interfaces](interfaces.md) |
| Write tests | [Acceptance Testing](acceptance-testing.md) |
