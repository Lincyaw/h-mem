"""Base agent interface for memory system operations.

Provides foundational classes for building LangGraph-based agents
with consistent state management.
"""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Base state for memory agents.

    Follows LangGraph best practices for state management.
    All agents share this common state structure.
    """

    current_step: str
    error: str | None
    metadata: dict[str, Any]
