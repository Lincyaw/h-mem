"""Retrieval tracer for causal debugging and observability.

Provides full-chain tracing for retrieval operations with:
- Stage-level latency breakdown
- Trace ID propagation
- Performance diagnostics
"""

import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator
import structlog

logger = structlog.get_logger()


class TraceContext:
    """Context manager for tracing with stage tracking."""

    def __init__(self, trace_id: str, query: str | None = None) -> None:
        """Initialize trace context.

        Args:
            trace_id: Unique trace identifier
            query: Optional query being traced
        """
        self.trace_id = trace_id
        self.query = query
        self.stages: dict[str, float] = {}
        self.start_time = time.perf_counter()
        self._current_stage: str | None = None
        self._stage_start: float | None = None

    def __enter__(self) -> "TraceContext":
        return self

    def __exit__(self, *args: object) -> None:
        # Record total duration
        self.stages["total"] = int((time.perf_counter() - self.start_time) * 1000)

    def stage(self, name: str, duration_ms: float | None = None) -> None:
        """Record stage latency.

        Args:
            name: Stage name
            duration_ms: Duration in milliseconds (optional, calculated if not provided)
        """
        if duration_ms is not None:
            self.stages[name] = duration_ms
        elif self._stage_start is not None:
            self.stages[name] = int((time.perf_counter() - self._stage_start) * 1000)

    @contextmanager
    def timed_stage(self, name: str) -> Iterator[None]:
        """Context manager for timing a stage.

        Args:
            name: Stage name

        Example:
            >>> with ctx.timed_stage("vector_search"):
            ...     results = db.search(query)
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = int((time.perf_counter() - start) * 1000)

    def get_breakdown(self) -> dict[str, float]:
        """Get latency breakdown.

        Returns:
            Stage latencies in milliseconds
        """
        return self.stages.copy()


class RetrievalTracer:
    """Full-chain tracing for retrieval operations.

    Tracks latency breakdown across stages:
    - Cache lookup
    - Bloom filter check
    - Vector search
    - Graph traversal
    - Ranking

    Example:
        >>> tracer = RetrievalTracer()
        >>> with tracer.trace("query_123") as ctx:
        ...     with ctx.timed_stage("cache_lookup"):
        ...         cache.get(key)
        ...     with ctx.timed_stage("vector_search"):
        ...         db.search(query)
        >>> tracer.get_breakdown("query_123")
        {'cache_lookup': 5, 'vector_search': 120, 'total': 125}
    """

    def __init__(self, max_traces: int = 1000) -> None:
        """Initialize retrieval tracer.

        Args:
            max_traces: Maximum traces to retain (LRU eviction)
        """
        self._traces: dict[str, TraceContext] = {}
        self._trace_order: list[str] = []
        self.max_traces = max_traces

    @contextmanager
    def trace(
        self, trace_id: str | None = None, query: str | None = None
    ) -> Iterator[TraceContext]:
        """Start new trace.

        Args:
            trace_id: Unique trace identifier (auto-generated if None)
            query: Optional query being traced

        Yields:
            Trace context manager
        """
        trace_id = trace_id or f"trace_{uuid.uuid4().hex[:12]}"
        ctx = TraceContext(trace_id, query)

        try:
            yield ctx
        finally:
            # Store trace
            self._traces[trace_id] = ctx
            self._trace_order.append(trace_id)

            # LRU eviction
            while len(self._traces) > self.max_traces:
                oldest = self._trace_order.pop(0)
                self._traces.pop(oldest, None)

            # Log trace completion
            logger.info(
                "retrieval_trace_complete",
                trace_id=trace_id,
                query=query,
                stages=ctx.stages,
                total_ms=ctx.stages.get("total", 0),
            )

    def get_breakdown(self, trace_id: str) -> dict[str, float]:
        """Get latency breakdown for trace.

        Args:
            trace_id: Trace identifier

        Returns:
            Stage latencies in milliseconds
        """
        ctx = self._traces.get(trace_id)
        return ctx.stages.copy() if ctx else {}

    def get_recent_traces(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get most recent traces.

        Args:
            limit: Maximum traces to return

        Returns:
            List of trace summaries
        """
        recent_ids = self._trace_order[-limit:]
        traces = []

        for tid in reversed(recent_ids):
            ctx = self._traces.get(tid)
            if ctx:
                traces.append(
                    {
                        "trace_id": tid,
                        "query": ctx.query,
                        "stages": ctx.stages,
                        "total_ms": ctx.stages.get("total", 0),
                    }
                )

        return traces

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics.

        Returns:
            Statistics dictionary with P50/P95/P99 latencies
        """
        if not self._traces:
            return {"trace_count": 0}

        totals = [ctx.stages.get("total", 0) for ctx in self._traces.values()]
        totals.sort()

        n = len(totals)
        return {
            "trace_count": n,
            "p50_ms": totals[n // 2] if n > 0 else 0,
            "p95_ms": totals[int(n * 0.95)] if n > 0 else 0,
            "p99_ms": totals[int(n * 0.99)] if n > 0 else 0,
            "avg_ms": sum(totals) / n if n > 0 else 0,
        }


# Global tracer instance for convenience
_global_tracer = RetrievalTracer()


def get_tracer() -> RetrievalTracer:
    """Get the global tracer instance.

    Returns:
        Global RetrievalTracer instance
    """
    return _global_tracer


def generate_trace_id() -> str:
    """Generate a unique trace ID.

    Returns:
        Unique trace ID string
    """
    return f"trace_{uuid.uuid4().hex[:12]}"
