"""Core ReAct Agent Loop implementation.

The AgentLoop orchestrates the Thought → Action → Observation cycle,
handling format errors, tool execution, and skill loading.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from hmem.agents.llm import LLMClient
from hmem.agents.react.errors import FatalError, FormatError, LoopGuardError
from hmem.agents.react.executor import ParallelExecutor
from hmem.agents.react.guard import LoopGuard, LoopGuardConfig
from hmem.agents.react.prompts import (
    CONTINUATION_PROMPT,
    FORMAT_ERROR_RECOVERY_PROMPT,
    URGENCY_WARNING_CRITICAL,
    URGENCY_WARNING_LOW,
    build_system_prompt,
    format_observations,
)
from hmem.agents.react.tool_base import ToolRegistry
from hmem.agents.react.types import (
    AgentState,
    Observation,
    ReActStep,
    Thought,
    ToolCall,
)

logger = logging.getLogger(__name__)


class AgentLoopConfig(BaseModel):
    """Configuration for the agent loop."""

    max_iterations: int = 20
    timeout_seconds: int = 300
    stuck_threshold: int = 3
    max_format_retries: int = 2
    tool_retry_default: int = 3
    enable_parallel_tools: bool = True
    max_workers: int = 4


class ThinkResult(BaseModel):
    """Result of a single think step."""

    thought: Thought
    tool_calls: list[ToolCall]
    is_complete: bool
    final_answer: Any | None = None


class AgentLoop:
    """Core ReAct agent loop implementation.

    Orchestrates the think-act-observe cycle with:
    - Parallel tool execution
    - Format error self-correction
    - Dynamic skill loading
    - Loop guard protection

    Example:
        >>> registry = ToolRegistry()
        >>> registry.register(skill_search_tool)
        >>> registry.register(memory_search_tool)
        >>>
        >>> loop = AgentLoop(llm_client, registry)
        >>> result = loop.run(
        ...     objective="Find relevant memories about Neo4j",
        ...     output_schema=RetrievalOutput,
        ... )
    """

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        config: AgentLoopConfig | None = None,
        guard_config: LoopGuardConfig | None = None,
    ) -> None:
        """Initialize the agent loop.

        Args:
            llm: LLM client for reasoning
            registry: Tool registry with available tools
            config: Agent loop configuration
            guard_config: Loop guard configuration
        """
        self.llm = llm
        self.registry = registry
        self.config = config or AgentLoopConfig()
        self.guard = LoopGuard(
            guard_config
            or LoopGuardConfig(
                max_iterations=self.config.max_iterations,
                timeout_seconds=self.config.timeout_seconds,
                stuck_threshold=self.config.stuck_threshold,
            )
        )
        self.executor = ParallelExecutor(
            registry,
            max_workers=self.config.max_workers,
            default_retries=self.config.tool_retry_default,
        )

    def run(
        self,
        objective: str,
        context: dict[str, Any] | None = None,
        output_schema: type[BaseModel] | None = None,
    ) -> Any:
        """Run the ReAct loop to completion.

        Args:
            objective: What the agent should accomplish
            context: Additional context for the task
            output_schema: Optional Pydantic model to validate final output

        Returns:
            Final output, validated against schema if provided

        Raises:
            LoopGuardError: If safety limits are exceeded
            FatalError: If unrecoverable error occurs
        """
        state = AgentState(
            task_id=str(uuid4()),
            objective=objective,
            context=context or {},
            started_at=datetime.now(timezone.utc),
        )

        logger.info(
            "Starting agent loop",
            extra={
                "task_id": state.task_id,
                "objective": objective[:100],
            },
        )

        try:
            while state.status == "running":
                # Check loop guards
                self.guard.check(state)

                # Think: Get thought, actions, and completion status
                think_result = self._think(state)

                # Check if complete
                if think_result.is_complete:
                    logger.info(
                        "Agent completing",
                        extra={
                            "has_final_answer": think_result.final_answer is not None,
                            "final_answer_type": type(think_result.final_answer).__name__,
                        },
                    )
                    state = state.with_output(think_result.final_answer)
                    break

                # Act: Execute tools in parallel
                if think_result.tool_calls:
                    observations = self.executor.execute_sync(think_result.tool_calls)
                else:
                    observations = []

                # Record the step
                step = ReActStep(
                    step_number=state.iteration,
                    thought=think_result.thought,
                    tool_calls=think_result.tool_calls,
                    observations=observations,
                )
                state = state.with_step(step)

                # Handle skill loading from observations
                state = self._handle_skill_loading(state, observations)

                # Check for fatal errors in observations
                for obs in observations:
                    if not obs.success and obs.error_type == "fatal":
                        state = state.with_status(
                            "failed",
                            f"Fatal tool error: {obs.tool_name}: {obs.error}",
                        )
                        break

        except LoopGuardError as e:
            state = state.with_status("stuck", str(e))
            logger.warning(
                "Loop guard triggered",
                extra={
                    "task_id": state.task_id,
                    "guard_type": e.guard_type,
                    "guard_message": str(e),
                },
            )
            raise
        except Exception as e:
            state = state.with_status("failed", str(e))
            logger.error(
                "Agent loop failed",
                extra={
                    "task_id": state.task_id,
                    "error": str(e),
                },
            )
            raise FatalError(f"Agent loop failed: {e}", cause=e) from e

        logger.info(
            "Agent loop completed",
            extra={
                "task_id": state.task_id,
                "status": state.status,
                "iterations": state.iteration,
                "elapsed_seconds": round(state.elapsed_seconds, 1),
                "has_final_output": state.final_output is not None,
                "final_output_type": type(state.final_output).__name__,
            },
        )

        # Validate output against schema if provided
        if output_schema and state.final_output is not None:
            try:
                if isinstance(state.final_output, dict):
                    return output_schema.model_validate(state.final_output)
                return state.final_output
            except Exception as e:
                logger.warning(
                    "Output schema validation failed",
                    extra={"error": str(e)},
                )
                return state.final_output

        return state.final_output

    def _think(self, state: AgentState) -> ThinkResult:
        """Execute a single think step.

        Calls the LLM to reason about the current situation and decide
        on next actions. Handles format errors with self-correction.

        Args:
            state: Current agent state

        Returns:
            ThinkResult with thought, actions, and completion status

        Raises:
            FatalError: If format errors persist after retries
        """
        # Build the prompt
        system_prompt = build_system_prompt(
            objective=state.objective,
            tool_descriptions=self.registry.get_all_descriptions(),
            context=state.context,
            skill_contents=state.skill_contents,
        )

        # Build conversation history
        messages = self._build_messages(state, system_prompt)

        # Try to get valid response with format error recovery
        for attempt in range(self.config.max_format_retries + 1):
            try:
                response = self._invoke_llm(messages)
                logger.debug(
                    "LLM raw response",
                    extra={"response_preview": response[:500] if response else "None"},
                )
                parsed = self._parse_response(response)
                logger.debug(
                    "Parsed response",
                    extra={
                        "is_complete": parsed.get("is_complete"),
                        "has_final_answer": parsed.get("final_answer") is not None,
                        "actions_count": len(parsed.get("actions", [])),
                    },
                )
                return self._create_think_result(parsed)
            except FormatError as e:
                if attempt >= self.config.max_format_retries:
                    raise FatalError(
                        f"Format error persists after {self.config.max_format_retries} retries",
                        cause=e,
                    ) from e

                logger.warning(
                    "Format error, attempting recovery",
                    extra={"attempt": attempt + 1, "error": str(e)},
                )

                # Add recovery prompt
                recovery_prompt = FORMAT_ERROR_RECOVERY_PROMPT.format(
                    error_message=e.message,
                    raw_output=e.raw_output[:500],
                )
                messages.append({"role": "assistant", "content": e.raw_output})
                messages.append({"role": "user", "content": recovery_prompt})

        # Should not reach here
        raise FatalError("Think step failed unexpectedly")

    def _build_messages(
        self, state: AgentState, system_prompt: str
    ) -> list[dict[str, str]]:
        """Build message list for LLM invocation.

        Args:
            state: Current agent state
            system_prompt: System prompt to use

        Returns:
            List of messages for LLM
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]

        max_iterations = self.config.max_iterations

        # Add conversation history from steps
        for step_idx, step in enumerate(state.steps):
            # Add thought
            thought_content = (
                f"Thought: {step.thought.reasoning}\nPlan: {step.thought.plan}"
            )
            messages.append({"role": "assistant", "content": thought_content})

            # Add observations if any
            if step.observations:
                obs_dicts = [obs.model_dump() for obs in step.observations]
                obs_text = format_observations(obs_dicts)

                # Calculate remaining iterations after this step
                # step_idx is 0-based, so after step 0 we've used 1 iteration
                iterations_used = step_idx + 1
                remaining = max_iterations - iterations_used

                # Determine urgency warning
                if remaining <= 2:
                    urgency_warning = URGENCY_WARNING_CRITICAL.format(remaining=remaining)
                elif remaining <= 4:
                    urgency_warning = URGENCY_WARNING_LOW
                else:
                    urgency_warning = ""

                continuation = CONTINUATION_PROMPT.format(
                    observations=obs_text,
                    remaining=remaining,
                    max_iterations=max_iterations,
                    urgency_warning=urgency_warning,
                )
                messages.append({"role": "user", "content": continuation})

        # Add initial user message if no steps yet
        if not state.steps:
            messages.append(
                {"role": "user", "content": f"Begin working on: {state.objective}"}
            )

        return messages

    def _invoke_llm(self, messages: list[dict[str, str]]) -> str:
        """Invoke the LLM with messages.

        Args:
            messages: Messages to send

        Returns:
            Raw response text
        """
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        # Convert to LangChain format (content as list of dicts)
        lc_messages = []
        for msg in messages:
            content = [{"type": "text", "text": msg["content"]}]
            if msg["role"] == "system":
                lc_messages.append(SystemMessage(content=content))
            elif msg["role"] == "user":
                lc_messages.append(HumanMessage(content=content))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=content))

        response = self.llm.llm.invoke(lc_messages)
        return self.llm._extract_text(response.content)

    def _parse_response(self, raw_output: str) -> dict:
        """Parse LLM response as JSON.

        Handles markdown code blocks and validates structure.

        Args:
            raw_output: Raw LLM output

        Returns:
            Parsed JSON dict

        Raises:
            FormatError: If parsing fails
        """
        # Try to extract JSON from markdown code blocks
        json_str = raw_output.strip()

        # Match ```json ... ``` or ``` ... ```
        code_block_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?```",
            json_str,
            re.DOTALL,
        )
        if code_block_match:
            json_str = code_block_match.group(1).strip()

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise FormatError(
                message=f"Invalid JSON: {e}",
                raw_output=raw_output,
                expected_format="JSON object with thought, actions, is_complete, final_answer",
            ) from e

        # Validate required fields
        if not isinstance(parsed, dict):
            raise FormatError(
                message="Response must be a JSON object",
                raw_output=raw_output,
                expected_format="JSON object with thought, actions, is_complete, final_answer",
            )

        if "thought" not in parsed:
            raise FormatError(
                message="Missing required field: thought",
                raw_output=raw_output,
                expected_format="JSON object with thought, actions, is_complete, final_answer",
            )

        return parsed

    def _create_think_result(self, parsed: dict) -> ThinkResult:
        """Create ThinkResult from parsed response.

        Args:
            parsed: Parsed JSON response

        Returns:
            ThinkResult object
        """
        # Extract thought
        thought_data = parsed.get("thought", {})
        if isinstance(thought_data, str):
            thought = Thought(reasoning=thought_data, plan="")
        else:
            thought = Thought(
                reasoning=thought_data.get("reasoning", ""),
                plan=thought_data.get("plan", ""),
                confidence=thought_data.get("confidence", 0.5),
            )

        # Extract actions
        actions_data = parsed.get("actions", [])
        tool_calls = []
        for action in actions_data:
            if isinstance(action, dict) and "tool_name" in action:
                tool_calls.append(
                    ToolCall(
                        tool_name=action["tool_name"],
                        arguments=action.get("arguments", {}),
                        max_retries=action.get("max_retries"),
                    )
                )

        # Extract completion status
        is_complete = bool(parsed.get("is_complete", False))
        final_answer = parsed.get("final_answer")

        return ThinkResult(
            thought=thought,
            tool_calls=tool_calls,
            is_complete=is_complete,
            final_answer=final_answer,
        )

    def _handle_skill_loading(
        self, state: AgentState, observations: list[Observation]
    ) -> AgentState:
        """Handle skill loading from tool observations.

        If a skill_load tool was called, extract the skill content
        and add it to the state.

        Args:
            state: Current agent state
            observations: Observations from tool execution

        Returns:
            Updated state with loaded skills
        """
        for obs in observations:
            if obs.tool_name == "skill_load" and obs.success and obs.result:
                result = obs.result
                if (
                    isinstance(result, dict)
                    and "name" in result
                    and "content" in result
                ):
                    skill_name = result["name"]
                    if skill_name not in state.loaded_skills:
                        state = state.with_skill(skill_name, result["content"])
                        logger.info(
                            "Skill loaded",
                            extra={
                                "task_id": state.task_id,
                                "skill_name": skill_name,
                            },
                        )

        return state

    def get_state_summary(self, state: AgentState) -> dict:
        """Get a summary of the agent state for logging/debugging.

        Args:
            state: Agent state to summarize

        Returns:
            Summary dict
        """
        return {
            "task_id": state.task_id,
            "objective": state.objective[:100],
            "status": state.status,
            "iteration": state.iteration,
            "elapsed_seconds": round(state.elapsed_seconds, 1),
            "loaded_skills": list(state.loaded_skills),
            "total_tool_calls": sum(len(step.tool_calls) for step in state.steps),
            "successful_observations": sum(
                1 for step in state.steps for obs in step.observations if obs.success
            ),
            "failed_observations": sum(
                1
                for step in state.steps
                for obs in step.observations
                if not obs.success
            ),
            "error_message": state.error_message,
            **self.guard.get_progress_report(state),
        }
