"""Phoenix observability integration for tracing LLM calls.

Provides integration with Arize Phoenix for visualizing agent conversation traces.
Set environment variable PHOENIX_COLLECTOR_ENDPOINT to enable tracing.
"""

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def setup_phoenix(project_name: str = "h-mem") -> bool:
    """Initialize Phoenix tracing for LangChain operations.

    Only activates if PHOENIX_COLLECTOR_ENDPOINT is set (e.g., http://localhost:6006).
    This connects to an existing Phoenix server without starting a new one.

    Args:
        project_name: Project name for Phoenix dashboard grouping

    Returns:
        True if setup successful, False otherwise
    """
    # Only enable if endpoint is explicitly configured
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    if not endpoint:
        return False

    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from phoenix.otel import register
    except ImportError as e:
        print(
            f"⚠️  Phoenix dependencies not installed. Run:\n"
            f"   uv add arize-phoenix openinference-instrumentation-langchain\n"
            f"   Error: {e}"
        )
        return False

    try:
        os.environ["PHOENIX_PROJECT_NAME"] = project_name

        # Connect to existing Phoenix server
        tracer_provider = register(
            project_name=project_name,
            endpoint=endpoint,
        )
        print(f"🔭 Phoenix tracing enabled -> {endpoint}")

        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
        print("✅ LangChain instrumentation active")
        return True

    except Exception as e:
        print(f"❌ Failed to initialize Phoenix tracing: {e}")
        return False


def get_current_trace_url() -> str | None:
    """Get the Phoenix trace URL for the current span.

    Returns:
        Trace URL if available, None otherwise
    """
    try:
        from opentelemetry import trace

        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            trace_id = format(current_span.get_span_context().trace_id, "032x")
            return f"http://localhost:6006/traces/{trace_id}"
    except Exception:
        pass
    return None
