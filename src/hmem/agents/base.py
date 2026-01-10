"""Base agent interface for memory system operations.

Provides foundational classes for building LangGraph-based agents
with consistent state management, observability, and multi-entry support.

Multi-Entry Pattern:
    Agents can be invoked from different entry points depending on the task.
    This is achieved by compiling the graph with specific entry_point parameter.
"""

from typing import Any, TypedDict

import structlog
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = structlog.get_logger()


class AgentState(TypedDict, total=False):
    """Base state for memory agents.

    Follows LangGraph best practices for state management.
    All agents share this common state structure.
    """

    current_step: str
    error: str | None
    metadata: dict[str, Any]


class BaseMemoryAgent:
    """Base class for LangGraph-based memory agents with multi-entry support.

    Design principles:
    - Each agent is a StateGraph workflow
    - Multiple entry points for different use cases
    - Observable via structured logging
    - Type-safe state management

    Multi-Entry Pattern:
        Agents define multiple entry points, allowing callers to start
        execution from different nodes. This enables:
        - Partial workflow execution (e.g., only topic extraction)
        - Pipeline composition (chain agents together)
        - Incremental processing (continue from checkpoint)

    Example:
        >>> class MyAgent(BaseMemoryAgent):
        ...     def __init__(self):
        ...         super().__init__(name="my_agent")
        ...         self._build_workflow()
        ...
        ...     def _get_entry_points(self) -> list[str]:
        ...         return ["step_a", "step_b"]  # Multiple entries
        ...
        ...     def _build_workflow(self):
        ...         self.graph.add_node("step_a", self._step_a)
        ...         self.graph.add_node("step_b", self._step_b)
        ...
        >>> # Run from different entry points
        >>> agent.run(entry_point="step_a")
        >>> agent.run(entry_point="step_b")
    """

    def __init__(self, name: str) -> None:
        """Initialize base agent.

        Args:
            name: Agent identifier for logging
        """
        self.name = name
        self.graph: StateGraph = StateGraph(AgentState)
        self.logger = logger.bind(agent=name)
        self._compiled_graphs: dict[str, CompiledStateGraph] = {}

    def _build_workflow(self) -> None:
        """Build the agent's workflow graph.

        Subclasses must implement this to define nodes and edges.
        """
        raise NotImplementedError("Subclasses must implement _build_workflow")

    def _get_entry_points(self) -> list[str]:
        """Get available entry points for this agent.

        Override in subclasses to define multiple entry points.

        Returns:
            List of node names that can serve as entry points
        """
        return []

    def _get_compiled_graph(self, entry_point: str | None = None) -> CompiledStateGraph:
        """Get or create compiled graph for an entry point.

        Args:
            entry_point: Node name to start from (None for default)

        Returns:
            Compiled graph ready for execution
        """
        cache_key = entry_point or "__default__"

        if cache_key not in self._compiled_graphs:
            if entry_point:
                # Set the entry point before compiling
                self.graph.set_entry_point(entry_point)
            self._compiled_graphs[cache_key] = self.graph.compile()

        return self._compiled_graphs[cache_key]

    def run(
        self,
        initial_state: dict[str, Any] | None = None,
        entry_point: str | None = None,
    ) -> dict[str, Any]:
        """Execute the agent workflow from specified entry point.

        Args:
            initial_state: Initial state dict (optional)
            entry_point: Node to start execution from (optional)

        Returns:
            Final state after workflow completion

        Raises:
            RuntimeError: If workflow execution fails
            ValueError: If invalid entry point specified
        """
        # Validate entry point
        if entry_point:
            valid_entries = self._get_entry_points()
            if valid_entries and entry_point not in valid_entries:
                raise ValueError(
                    f"Invalid entry point '{entry_point}'. "
                    f"Valid options: {valid_entries}"
                )

        app = self._get_compiled_graph(entry_point)

        state: dict[str, Any] = {
            "current_step": entry_point or "init",
            "error": None,
            "metadata": {},
            **(initial_state or {}),
        }

        self.logger.info(
            "agent_run_start",
            entry_point=entry_point,
            initial_state=state,
        )

        try:
            result = app.invoke(state)
            self.logger.info(
                "agent_run_complete",
                entry_point=entry_point,
                final_step=result.get("current_step"),
                has_error=result.get("error") is not None,
            )
            return dict(result)
        except Exception as e:
            self.logger.error(
                "agent_run_failed",
                entry_point=entry_point,
                error=str(e),
            )
            raise RuntimeError(f"Agent {self.name} failed: {e}") from e

    def get_available_operations(self) -> list[str]:
        """Get list of available operations (entry points).

        Returns:
            List of operation names that can be invoked
        """
        return self._get_entry_points()
