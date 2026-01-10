"""Prometheus metrics collectors."""

from prometheus_client import Counter, Gauge, Histogram

# Performance metrics
retrieve_latency = Histogram(
    "memory_retrieve_latency_seconds",
    "Retrieval latency distribution",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)

consolidate_duration = Histogram(
    "memory_consolidate_duration_seconds",
    "Consolidation duration",
    buckets=[1, 5, 10, 30, 60],
)

# Capacity metrics
episodic_count = Gauge(
    "memory_episodic_total",
    "Total episodic memories",
)

semantic_node_count = Gauge(
    "memory_semantic_nodes_total",
    "Semantic graph node count",
)

# Quality metrics
consolidate_success = Counter(
    "memory_consolidate_total",
    "Consolidation attempts",
    ["status"],  # success/failure
)

retrieval_recall = Gauge(
    "memory_retrieval_recall",
    "Retrieval recall rate (from golden dataset)",
)

# Cost metrics
llm_tokens_consumed = Counter(
    "memory_llm_tokens_total",
    "LLM tokens consumed",
    ["operation"],  # encode/reflect/summarize
)

llm_cost_usd = Counter(
    "memory_llm_cost_usd_total",
    "LLM cost in USD",
)
