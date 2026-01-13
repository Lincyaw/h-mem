# **Cognitive Agent Memory System (CAMS) - Design Documentation Navigation**

Welcome to the complete design documentation of h-mem (Cognitive Agent Memory System). This system is based on cognitive neuroscience principles and provides AI agents with brain-like memory management capabilities.

---

## **📚 Documentation Navigation**

### **Essential Reading**

1. **[System Design Philosophy - Complete Edition](design-philosophy.md)** ⭐
   - Understand the system's core design philosophy
   - Cognitive neuroscience foundations (Atkinson-Shiffrin Model)
   - Core problems the system solves
   - Unix philosophy in system design

2. **[System Architecture & Constraints](architecture.md)**
   - Three-layer architecture design (Perception Layer → Hippocampus Processing Layer → Storage Layer)
   - System performance boundaries and SLA definitions
   - Technology stack selection and implementation phase planning

### **In-Depth Understanding**

3. **[Component Details & Responsibilities](components.md)**
   - Detailed explanations of 5 core components
   - Transaction management and concurrency control
   - Event sourcing architecture design

4. **[Core Workflows](workflows.md)**
   - 4 core workflow processes
   - Hot path (retrieval), cold path (consolidation), evolution path (reflection)
   - Feedback-driven weight update mechanism

5. **[Memory Provenance & Hierarchical Semantic Graph](provenance.md)**
   - Complete memory lifecycle
   - Multi-level memory association architecture
   - Provenance chain application scenarios

### **API & Testing**

6. **[Key Interface Definitions](interfaces.md)**
   - Core data models (Memory, Event, Principle, Skill, etc.)
   - Exception definitions
   - MemorySystem core API

7. **[System Acceptance Plan](acceptance-testing.md)**
   - 4 standardized test cases
   - "Goldfish Test", "Don't Repeat Mistakes Test", "Change of Mind Test", "Sherlock Test"
   - Pytest implementation framework

### **Advanced Topics**

8. **[Observability Design](observability.md)**
   - Key metrics (performance, capacity, cost, quality)
   - Structured logging and tracing
   - Adaptive threshold management
   - Predictive prefetching mechanism

9. **[Design Philosophy - Unix Principles](design-philosophy.md)**
   - "Do One Thing Well": interface minimization
   - "Rule of Silence": configuration-driven design
   - "Rule of Modularity": component replaceability
   - "Rule of Transparency": observability built-in
