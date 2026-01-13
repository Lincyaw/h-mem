# **Observability Design**

Ensure the system is monitorable, debuggable, and optimizable.

## **Key Metrics**

### **Performance Metrics**
- `memory.retrieve.latency` (Histogram): Retrieval latency distribution (P50/P95/P99)
- `memory.retrieve.throughput` (Counter): Retrieval operations per second
- `memory.consolidate.duration` (Histogram): Consolidation time duration
- `memory.consolidate.success_rate` (Gauge): Consolidation success rate

### **Capacity Metrics**
- `memory.episodic.count` (Gauge): Total episodic memories
- `memory.semantic.node_count` (Gauge): Semantic graph node count
- `memory.semantic.edge_count` (Gauge): Relationship edge count

### **Cost Metrics**
- `memory.llm.tokens_consumed` (Counter): LLM token consumption
- `memory.llm.cost_usd` (Counter): LLM cost in USD

### **Quality Metrics**
- `memory.retrieval.recall` (Gauge): Retrieval recall rate (requires regular evaluation)
- `memory.consolidation.conflicts` (Counter): Number of conflicts

---

## **Structured Logging**

Use `structlog` to implement end-to-end tracing:

```python
import structlog

logger = structlog.get_logger()

# Assign trace_id for each operation
trace_id = str(uuid.uuid4())

logger.info(
    "memory_retrieve_start",
    trace_id=trace_id,
    query=query,
    user_id=user_id
)

# ... perform retrieval ...

logger.info(
    "memory_retrieve_complete",
    trace_id=trace_id,
    results_count=len(results),
    latency_ms=elapsed * 1000,
    sources={"episodic": 3, "semantic": 2}
)
```

**Log field standards:**
- `trace_id`: Spans the entire operation chain
- `session_id`: Session identifier
- `user_id`: User identifier
- `component`: Component name (retrieval/consolidation/reflection)
- `duration_ms`: Operation duration

---

## **Monitoring Endpoints**

Provide Prometheus-compatible metrics endpoints:

```python
from prometheus_client import Counter, Histogram, Gauge

retrieve_latency = Histogram(
    'memory_retrieve_latency_seconds',
    'Retrieval latency in seconds',
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
)

consolidate_success = Counter(
    'memory_consolidate_total',
    'Total consolidation attempts',
    ['status']  # success/failure
)

episodic_count = Gauge(
    'memory_episodic_total',
    'Total episodic memories'
)
```

---

## **Quality Assurance Monitoring**

### **Golden Dataset Regression Testing**

Establish human-annotated standard query sets to ensure code changes don't break retrieval quality:

```python
class MemoryQualityMonitor:
    """Memory quality monitoring"""

    def check_retrieval_quality(self):
        """Check retrieval accuracy - based on Golden Dataset"""
        golden_dataset = load_golden_queries()  # At least 100 manually annotated queries

        # Detailed stats: by memory type, time span, topic distribution
        stats = {
            "episodic": {"total": 0, "correct": 0},
            "semantic": {"total": 0, "correct": 0},
            "skill": {"total": 0, "correct": 0}
        }

        for query, expected_memories, memory_type in golden_dataset:
            results = list(memory_system.recall(query, limit=5))
            if self._has_overlap(results, expected_memories):
                stats[memory_type]["correct"] += 1
            stats[memory_type]["total"] += 1

        # Calculate recall by type
        for mem_type, stat in stats.items():
            recall = stat["correct"] / stat["total"] if stat["total"] > 0 else 0
            logger.info("recall_by_type", type=mem_type, recall=recall)

            # Below minimum acceptable standard (80%) triggers alert
            if recall < 0.80:
                alert_ops(f"CRITICAL: {mem_type} recall dropped to {recall:.2%}")
            # Below target (85%) sends warning
            elif recall < 0.85:
                logger.warn(f"WARNING: {mem_type} recall below target: {recall:.2%}")

    def check_graph_health(self):
        """Check semantic graph health"""
        # Detect orphaned nodes, cycles, weight anomalies, etc.
        orphan_nodes = db.query("SELECT * FROM nodes WHERE degree = 0")
        if len(orphan_nodes) > 100:
            logger.warn("graph_orphans", count=len(orphan_nodes))
```

### **CI/CD Integration**

```yaml
# .github/workflows/quality-gate.yml
- name: Golden Dataset Regression
  run: |
    pytest tests/test_golden_dataset.py --strict
    # Block merge if recall drops >5%
```

---

## **Causal Tracing and Diagnosis**

When retrieval quality degrades, quickly identify bottlenecks:

```python
class RetrievalTracer:
    """End-to-end retrieval tracing"""

    def trace_recall(self, query: str, trace_id: str):
        """Record duration and results at each stage"""
        trace = {
            "trace_id": trace_id,
            "query": query,
            "stages": []
        }

        # Stage 1: Query embedding
        start = time.time()
        embedding = self.embed(query)
        trace["stages"].append({
            "name": "embedding",
            "duration_ms": (time.time() - start) * 1000,
            "output_dim": len(embedding)
        })

        # Stage 2: Vector search
        start = time.time()
        vector_results = self.vector_db.search(embedding, k=20)
        trace["stages"].append({
            "name": "vector_search",
            "duration_ms": (time.time() - start) * 1000,
            "candidates": len(vector_results)
        })

        # Stage 3: Graph expansion
        start = time.time()
        graph_results = self.graph_db.expand(vector_results)
        trace["stages"].append({
            "name": "graph_expansion",
            "duration_ms": (time.time() - start) * 1000,
            "additional": len(graph_results) - len(vector_results)
        })

        # Stage 4: Reranking
        start = time.time()
        final_results = self.reranker.rank(vector_results + graph_results)
        trace["stages"].append({
            "name": "reranking",
            "duration_ms": (time.time() - start) * 1000,
            "final_count": len(final_results)
        })

        # Log complete trace
        logger.info("retrieval_trace", **trace)
        return final_results
```

**Grafana visualization:**
- P99 latency breakdown chart: Shows time proportion of each stage
- Auto-highlight anomalies when recall drops
- Canary queries: Execute fixed query set hourly, monitor trends

### **Monitoring Frequency**
- Real-time metrics: Update on each operation
- Quality checks: Run daily on schedule
- Capacity alerts: Trigger when reaching 80% limit

---

## **Meta-Cognitive Mechanisms**

System's self-evaluation and self-adaptive optimization of memory quality.

### **Adaptive Retrieval Threshold**

**Problem:** Fixed `score_threshold=0.5` cannot adapt to different scenarios. Too high causes low recall, too low causes noise.

**Solution:** Track retrieval result "effectiveness" and dynamically adjust threshold.

```python
class AdaptiveThresholdManager:
    """Retrieval threshold adaptive management

    Effectiveness measurement methods:
    1. Explicit reference detection (reliable but incomplete):
       - Check if LLM output contains keywords from memory
       - Use simple TF-IDF matching

    2. Implicit evaluation (experimental):
       - Compare response quality with vs without memory
       - Requires manual annotation or user feedback

    Current implementation: Only uses method 1 (conservative but reliable)
    """

    def __init__(self, initial_threshold: float = 0.5):
        self.threshold = initial_threshold
        self.effectiveness_tracker = []  # (query, threshold, effectiveness)

    def track_effectiveness(
        self,
        query: str,
        results: List[Memory],
        llm_output: str,
        feedback: Optional[float] = None  # Optional user feedback (0-1)
    ):
        """Track actual usage of retrieval results"""
        if feedback is not None:
            # Prioritize real feedback
            effectiveness = feedback
        else:
            # Fall back to heuristic detection
            used_count = self._detect_explicit_references(results, llm_output)
            effectiveness = used_count / len(results) if results else 0

    def recalibrate(self):
        """Recalibrate threshold daily"""
        if len(self.effectiveness_tracker) < 50:
            return  # Insufficient samples

        recent = self.effectiveness_tracker[-100:]  # Last 100 queries
        avg_effectiveness = sum(r["effectiveness"] for r in recent) / len(recent)

        # Target: effectiveness > 60%
        if avg_effectiveness < 0.6:
            # Raise threshold, filter low-quality results
            self.threshold = min(0.8, self.threshold + 0.05)
            logger.info("threshold_increased", new=self.threshold, reason="low_effectiveness")
        elif avg_effectiveness > 0.8:
            # Lower threshold, increase recall
            self.threshold = max(0.3, self.threshold - 0.05)
            logger.info("threshold_decreased", new=self.threshold, reason="high_effectiveness")
```

### **Predictive Memory Prefetching**

Predict likely next queries based on session context and warm relevant memories to cache.

```python
class PredictivePrefetcher:
    """Predictive memory prefetcher"""

    def observe_query(self, session_id: str, query: str):
        """Observe query, predict and prefetch next"""
        predicted_queries = self.ngram_model.predict_next(session_id, top_k=3)

        # Async prefetch (doesn't block current query)
        for pred_query, confidence in predicted_queries:
            if confidence > 0.3:
                asyncio.create_task(self._prefetch(pred_query))
```

**Performance benefits:**
- On cache hit: P50 < 10ms (50x improvement vs normal 500ms)
- Hit rate: 30-40% (based on bigram model)

---

**Related Documents:**
- [System Design Philosophy](design.md) - Design philosophy and core concepts
- [System Architecture](architecture.md) - Overall architecture, constraints and technology stack
