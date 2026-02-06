"""Loop guard for detecting and preventing infinite loops.

Implements multiple detection strategies:
- Maximum iteration count
- Timeout
- Stuck detection (repeated actions)
"""

from __future__ import annotations

import hashlib
from collections import Counter

from pydantic import BaseModel, Field

from hmem.agents.react.errors import LoopGuardError
from hmem.agents.react.types import AgentState, ReActStep


class LoopGuardConfig(BaseModel):
    """Configuration for loop guard checks."""

    max_iterations: int = Field(
        default=20, ge=1, le=100, description="Maximum number of ReAct cycles"
    )
    timeout_seconds: int = Field(
        default=300, ge=10, le=3600, description="Maximum execution time"
    )
    stuck_threshold: int = Field(
        default=3,
        ge=2,
        le=10,
        description="Number of repeated actions before considering stuck",
    )


class LoopGuard:
    """Guards against infinite loops and stuck states.

    Call check() at each iteration to verify the agent should continue.
    Raises LoopGuardError if any limit is exceeded.
    """

    def __init__(self, config: LoopGuardConfig | None = None) -> None:
        self.config = config or LoopGuardConfig()

    def check(self, state: AgentState) -> None:
        """Check if the agent should continue executing.

        Args:
            state: Current agent state

        Raises:
            LoopGuardError: If any limit is exceeded
        """
        self._check_max_iterations(state)
        self._check_timeout(state)
        self._check_stuck(state)

    def _check_max_iterations(self, state: AgentState) -> None:
        """Check if maximum iterations exceeded."""
        if state.iteration >= self.config.max_iterations:
            raise LoopGuardError(
                message=f"Maximum iterations ({self.config.max_iterations}) exceeded",
                guard_type="max_iterations",
                current_value=state.iteration,
                threshold=self.config.max_iterations,
                details={"task_id": state.task_id, "objective": state.objective},
            )

    def _check_timeout(self, state: AgentState) -> None:
        """Check if timeout exceeded."""
        elapsed = state.elapsed_seconds
        if elapsed >= self.config.timeout_seconds:
            raise LoopGuardError(
                message=f"Timeout ({self.config.timeout_seconds}s) exceeded",
                guard_type="timeout",
                current_value=elapsed,
                threshold=self.config.timeout_seconds,
                details={"task_id": state.task_id, "objective": state.objective},
            )

    def _check_stuck(self, state: AgentState) -> None:
        """Check if the agent is stuck repeating the same actions."""
        if len(state.steps) < self.config.stuck_threshold:
            return

        # Get recent action signatures
        recent_steps = state.steps[-self.config.stuck_threshold :]
        signatures = [self._step_signature(step) for step in recent_steps]

        # Check if all recent signatures are identical
        if len(set(signatures)) == 1:
            raise LoopGuardError(
                message=f"Agent stuck: same action repeated {self.config.stuck_threshold} times",
                guard_type="stuck",
                current_value=self.config.stuck_threshold,
                threshold=self.config.stuck_threshold,
                details={
                    "task_id": state.task_id,
                    "repeated_action": signatures[0],
                    "objective": state.objective,
                },
            )

    def _step_signature(self, step: ReActStep) -> str:
        """Generate a signature for a step to detect repetition.

        Uses tool names and argument hashes to detect identical actions.
        """
        parts = []
        for call in step.tool_calls:
            args_hash = hashlib.md5(
                str(sorted(call.arguments.items())).encode()
            ).hexdigest()[:8]
            parts.append(f"{call.tool_name}:{args_hash}")
        return "|".join(sorted(parts)) or "no_action"

    def is_stuck(self, state: AgentState) -> bool:
        """Check if stuck without raising an error."""
        try:
            self._check_stuck(state)
            return False
        except LoopGuardError:
            return True

    def get_progress_report(self, state: AgentState) -> dict:
        """Get a progress report for monitoring/logging."""
        # Count unique vs repeated actions
        if state.steps:
            signatures = [self._step_signature(step) for step in state.steps]
            action_counts = Counter(signatures)
            most_common = action_counts.most_common(3)
        else:
            action_counts = Counter()
            most_common = []

        return {
            "task_id": state.task_id,
            "iteration": state.iteration,
            "max_iterations": self.config.max_iterations,
            "iterations_remaining": self.config.max_iterations - state.iteration,
            "elapsed_seconds": round(state.elapsed_seconds, 1),
            "timeout_seconds": self.config.timeout_seconds,
            "time_remaining": round(
                self.config.timeout_seconds - state.elapsed_seconds, 1
            ),
            "unique_actions": len(action_counts),
            "total_actions": len(state.steps),
            "most_common_actions": most_common,
            "status": state.status,
        }
