"""Pydantic types for the ReAct Agent Loop.

All state objects are immutable to support functional programming patterns
and easier debugging/logging.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Thought(BaseModel):
    """A reasoning step in the ReAct loop.

    Captures the agent's thought process before taking action.
    """

    model_config = {"frozen": True}

    reasoning: str = Field(description="The agent's reasoning process")
    plan: str = Field(description="What the agent plans to do next")
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence level in this reasoning",
    )


class ToolCall(BaseModel):
    """A request to invoke a tool.

    Supports parallel execution when multiple calls are made in one step.
    """

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    tool_name: str = Field(description="Name of the tool to call")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Arguments to pass to the tool"
    )
    max_retries: int | None = Field(
        default=None, description="Override default retry count for this call"
    )


class Observation(BaseModel):
    """Result of executing a tool call.

    Captures both successful results and errors with classification.
    """

    model_config = {"frozen": True}

    call_id: str = Field(description="ID of the ToolCall that produced this")
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None
    error_type: Literal["retriable", "fatal", "format"] | None = None
    execution_time_ms: int = Field(ge=0, description="How long the tool took")
    retry_count: int = Field(default=0, ge=0, description="Number of retries attempted")


class ReActStep(BaseModel):
    """A single complete ReAct cycle: Thought → Action(s) → Observation(s).

    Steps are immutable records of what happened during execution.
    """

    model_config = {"frozen": True}

    step_number: int = Field(ge=0)
    thought: Thought
    tool_calls: list[ToolCall] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentState(BaseModel):
    """Complete state of the ReAct agent.

    Immutable by design - use with_* methods to create updated copies.
    This makes debugging easier and enables time-travel debugging.
    """

    model_config = {"frozen": True}

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    objective: str = Field(description="What the agent is trying to accomplish")
    context: dict[str, Any] = Field(default_factory=dict)
    steps: tuple[ReActStep, ...] = Field(default_factory=tuple)
    iteration: int = Field(default=0, ge=0)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Skill management
    loaded_skills: tuple[str, ...] = Field(
        default_factory=tuple, description="Names of skills that have been loaded"
    )
    skill_contents: dict[str, str] = Field(
        default_factory=dict, description="Cached skill content by name"
    )

    # Execution state
    status: Literal["running", "completed", "failed", "stuck"] = Field(
        default="running"
    )
    final_output: Any | None = None
    error_message: str | None = None

    def with_step(self, step: ReActStep) -> AgentState:
        """Create new state with an additional step."""
        return self.model_copy(
            update={
                "steps": (*self.steps, step),
                "iteration": self.iteration + 1,
            }
        )

    def with_status(
        self,
        status: Literal["running", "completed", "failed", "stuck"],
        error_message: str | None = None,
    ) -> AgentState:
        """Create new state with updated status."""
        return self.model_copy(
            update={
                "status": status,
                "error_message": error_message,
            }
        )

    def with_output(self, output: Any) -> AgentState:
        """Create new state with final output."""
        return self.model_copy(
            update={
                "status": "completed",
                "final_output": output,
            }
        )

    def with_skill(self, name: str, content: str) -> AgentState:
        """Create new state with a loaded skill."""
        return self.model_copy(
            update={
                "loaded_skills": (*self.loaded_skills, name),
                "skill_contents": {**self.skill_contents, name: content},
            }
        )

    @property
    def elapsed_seconds(self) -> float:
        """Time elapsed since the agent started."""
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    @property
    def last_observations(self) -> list[Observation]:
        """Observations from the most recent step, or empty list."""
        if not self.steps:
            return []
        return list(self.steps[-1].observations)

    def get_conversation_history(self) -> list[dict[str, str]]:
        """Format steps as conversation history for LLM context."""
        history: list[dict[str, str]] = []
        for step in self.steps:
            # Add thought as assistant message
            thought_text = (
                f"Thought: {step.thought.reasoning}\nPlan: {step.thought.plan}"
            )
            history.append({"role": "assistant", "content": thought_text})

            # Add tool calls and observations
            for i, call in enumerate(step.tool_calls):
                obs = step.observations[i] if i < len(step.observations) else None
                action_text = f"Action: {call.tool_name}({call.arguments})"
                if obs:
                    if obs.success:
                        action_text += f"\nObservation: {obs.result}"
                    else:
                        action_text += f"\nObservation (error): {obs.error}"
                history.append({"role": "assistant", "content": action_text})

        return history
