"""Unit tests for the ReAct Agent Loop module.

Tests cover types, tool registry, loop guard, parallel executor, and agent loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from hmem.agents.react.errors import (
    AgentError,
    FatalError,
    FormatError,
    LoopGuardError,
    ToolError,
)
from hmem.agents.react.executor import ParallelExecutor
from hmem.agents.react.guard import LoopGuard, LoopGuardConfig
from hmem.agents.react.tool_base import BaseTool, ToolConfig, ToolRegistry, ToolSchema
from hmem.agents.react.types import (
    AgentState,
    Observation,
    ReActStep,
    Thought,
    ToolCall,
)


# =============================================================================
# Test Types
# =============================================================================


class TestThought:
    """Tests for Thought type."""

    def test_thought_creation(self) -> None:
        thought = Thought(reasoning="Test reasoning", plan="Test plan")
        assert thought.reasoning == "Test reasoning"
        assert thought.plan == "Test plan"
        assert thought.confidence == 0.5  # default

    def test_thought_with_confidence(self) -> None:
        thought = Thought(reasoning="Test", plan="Plan", confidence=0.9)
        assert thought.confidence == 0.9

    def test_thought_immutable(self) -> None:
        thought = Thought(reasoning="Test", plan="Plan")
        with pytest.raises(Exception):  # Pydantic frozen model
            thought.reasoning = "Modified"  # type: ignore


class TestToolCall:
    """Tests for ToolCall type."""

    def test_tool_call_creation(self) -> None:
        call = ToolCall(tool_name="test_tool", arguments={"arg1": "value1"})
        assert call.tool_name == "test_tool"
        assert call.arguments == {"arg1": "value1"}
        assert call.id  # auto-generated

    def test_tool_call_with_id(self) -> None:
        call = ToolCall(id="custom_id", tool_name="test_tool", arguments={})
        assert call.id == "custom_id"

    def test_tool_call_with_max_retries(self) -> None:
        call = ToolCall(tool_name="test_tool", arguments={}, max_retries=5)
        assert call.max_retries == 5


class TestObservation:
    """Tests for Observation type."""

    def test_observation_success(self) -> None:
        obs = Observation(
            call_id="123",
            tool_name="test_tool",
            success=True,
            result={"data": "test"},
            execution_time_ms=100,
        )
        assert obs.success is True
        assert obs.result == {"data": "test"}
        assert obs.error is None

    def test_observation_failure(self) -> None:
        obs = Observation(
            call_id="123",
            tool_name="test_tool",
            success=False,
            error="Something went wrong",
            error_type="retriable",
            execution_time_ms=50,
        )
        assert obs.success is False
        assert obs.error == "Something went wrong"
        assert obs.error_type == "retriable"


class TestReActStep:
    """Tests for ReActStep type."""

    def test_react_step_creation(self) -> None:
        thought = Thought(reasoning="Test", plan="Plan")
        call = ToolCall(tool_name="test_tool", arguments={})
        obs = Observation(
            call_id=call.id,
            tool_name="test_tool",
            success=True,
            execution_time_ms=100,
        )

        step = ReActStep(
            step_number=0,
            thought=thought,
            tool_calls=[call],
            observations=[obs],
        )

        assert step.step_number == 0
        assert step.thought == thought
        assert len(step.tool_calls) == 1
        assert len(step.observations) == 1


class TestAgentState:
    """Tests for AgentState type."""

    def test_agent_state_creation(self) -> None:
        state = AgentState(objective="Test objective")
        assert state.objective == "Test objective"
        assert state.iteration == 0
        assert state.status == "running"
        assert state.steps == ()
        assert state.loaded_skills == ()

    def test_agent_state_with_step(self) -> None:
        state = AgentState(objective="Test")
        thought = Thought(reasoning="Test", plan="Plan")
        step = ReActStep(step_number=0, thought=thought)

        new_state = state.with_step(step)

        assert len(new_state.steps) == 1
        assert new_state.iteration == 1
        # Original state unchanged
        assert len(state.steps) == 0
        assert state.iteration == 0

    def test_agent_state_with_status(self) -> None:
        state = AgentState(objective="Test")
        new_state = state.with_status("failed", "Error message")

        assert new_state.status == "failed"
        assert new_state.error_message == "Error message"
        assert state.status == "running"

    def test_agent_state_with_output(self) -> None:
        state = AgentState(objective="Test")
        new_state = state.with_output({"result": "success"})

        assert new_state.status == "completed"
        assert new_state.final_output == {"result": "success"}

    def test_agent_state_with_skill(self) -> None:
        state = AgentState(objective="Test")
        new_state = state.with_skill("test-skill", "skill content")

        assert "test-skill" in new_state.loaded_skills
        assert new_state.skill_contents["test-skill"] == "skill content"

    def test_agent_state_elapsed_seconds(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        state = AgentState(objective="Test", started_at=past)

        assert state.elapsed_seconds >= 10

    def test_agent_state_last_observations(self) -> None:
        state = AgentState(objective="Test")
        assert state.last_observations == []

        thought = Thought(reasoning="Test", plan="Plan")
        obs = Observation(
            call_id="123",
            tool_name="test",
            success=True,
            execution_time_ms=100,
        )
        step = ReActStep(step_number=0, thought=thought, observations=[obs])
        state = state.with_step(step)

        assert len(state.last_observations) == 1


# =============================================================================
# Test Errors
# =============================================================================


class TestErrors:
    """Tests for error types."""

    def test_agent_error(self) -> None:
        error = AgentError("Test error", details={"key": "value"})
        assert str(error) == "Test error"
        assert error.details == {"key": "value"}

    def test_tool_error(self) -> None:
        error = ToolError("Tool failed", tool_name="test_tool", retry_count=2)
        assert error.tool_name == "test_tool"
        assert error.retry_count == 2

    def test_format_error(self) -> None:
        error = FormatError(
            "Invalid JSON",
            raw_output="not json",
            expected_format="JSON object",
        )
        assert error.raw_output == "not json"
        assert error.expected_format == "JSON object"

    def test_fatal_error(self) -> None:
        cause = ValueError("Original error")
        error = FatalError("Fatal error", cause=cause)
        assert error.cause == cause

    def test_loop_guard_error(self) -> None:
        error = LoopGuardError(
            "Max iterations",
            guard_type="max_iterations",
            current_value=20,
            threshold=20,
        )
        assert error.guard_type == "max_iterations"
        assert error.current_value == 20
        assert error.threshold == 20


# =============================================================================
# Test Tool Base
# =============================================================================


class TestToolConfig:
    """Tests for ToolConfig."""

    def test_default_config(self) -> None:
        config = ToolConfig()
        assert config.max_retries == 3
        assert config.retry_delay_ms == 100
        assert config.timeout_ms == 30000

    def test_custom_config(self) -> None:
        config = ToolConfig(max_retries=5, timeout_ms=60000)
        assert config.max_retries == 5
        assert config.timeout_ms == 60000


class SimpleTool(BaseTool[str]):
    """Simple test tool for testing."""

    def run(self, message: str = "hello") -> str:
        return f"Result: {message}"

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "message": {"type": "string", "description": "Message to echo"},
            },
            required=[],
        )


class FailingTool(BaseTool[str]):
    """Tool that always fails for testing."""

    def __init__(self, error_type: str = "fatal") -> None:
        super().__init__(name="failing_tool", description="A tool that fails")
        self.error_type = error_type

    def run(self, **kwargs: Any) -> str:
        if self.error_type == "timeout":
            raise TimeoutError("Connection timed out")
        raise ValueError("Always fails")

    def classify_error(self, error: Exception) -> str:
        if isinstance(error, TimeoutError):
            return "retriable"
        return "fatal"


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_and_get(self) -> None:
        registry = ToolRegistry()
        tool = SimpleTool(name="simple", description="A simple tool")
        registry.register(tool)

        assert registry.get("simple") == tool
        assert registry.get("nonexistent") is None

    def test_list_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(SimpleTool(name="tool1", description="Tool 1"))
        registry.register(SimpleTool(name="tool2", description="Tool 2"))

        tools = registry.list_tools()
        assert "tool1" in tools
        assert "tool2" in tools

    def test_replace_existing(self) -> None:
        registry = ToolRegistry()
        tool1 = SimpleTool(name="test", description="Original")
        tool2 = SimpleTool(name="test", description="Replacement")

        registry.register(tool1)
        registry.register(tool2)

        assert registry.get("test") == tool2

    def test_contains(self) -> None:
        registry = ToolRegistry()
        registry.register(SimpleTool(name="test", description="Test"))

        assert "test" in registry
        assert "nonexistent" not in registry

    def test_len(self) -> None:
        registry = ToolRegistry()
        assert len(registry) == 0

        registry.register(SimpleTool(name="test", description="Test"))
        assert len(registry) == 1

    def test_get_all_descriptions(self) -> None:
        registry = ToolRegistry()
        registry.register(SimpleTool(name="tool1", description="Tool one"))
        registry.register(SimpleTool(name="tool2", description="Tool two"))

        descriptions = registry.get_all_descriptions()
        assert "tool1" in descriptions
        assert "Tool one" in descriptions


# =============================================================================
# Test Loop Guard
# =============================================================================


class TestLoopGuard:
    """Tests for LoopGuard."""

    def test_check_max_iterations_not_exceeded(self) -> None:
        guard = LoopGuard(LoopGuardConfig(max_iterations=10))
        state = AgentState(objective="Test", iteration=5)

        # Should not raise
        guard.check(state)

    def test_check_max_iterations_exceeded(self) -> None:
        guard = LoopGuard(LoopGuardConfig(max_iterations=10))
        state = AgentState(objective="Test", iteration=10)

        with pytest.raises(LoopGuardError) as exc_info:
            guard.check(state)

        assert exc_info.value.guard_type == "max_iterations"

    def test_check_timeout_not_exceeded(self) -> None:
        guard = LoopGuard(LoopGuardConfig(timeout_seconds=300))
        state = AgentState(objective="Test")

        # Should not raise (just started)
        guard.check(state)

    def test_check_timeout_exceeded(self) -> None:
        guard = LoopGuard(LoopGuardConfig(timeout_seconds=10))  # Minimum is 10
        past = datetime.now(timezone.utc) - timedelta(
            seconds=60
        )  # 60s ago, well over 10s limit
        state = AgentState(objective="Test", started_at=past)

        with pytest.raises(LoopGuardError) as exc_info:
            guard.check(state)

        assert exc_info.value.guard_type == "timeout"

    def test_check_stuck_detection(self) -> None:
        guard = LoopGuard(LoopGuardConfig(stuck_threshold=3))

        # Create state with 3 identical steps
        state = AgentState(objective="Test")
        for i in range(3):
            thought = Thought(reasoning="Same", plan="Same")
            call = ToolCall(tool_name="same_tool", arguments={"key": "value"})
            step = ReActStep(step_number=i, thought=thought, tool_calls=[call])
            state = state.with_step(step)

        with pytest.raises(LoopGuardError) as exc_info:
            guard.check(state)

        assert exc_info.value.guard_type == "stuck"

    def test_check_not_stuck_different_actions(self) -> None:
        guard = LoopGuard(LoopGuardConfig(stuck_threshold=3))

        state = AgentState(objective="Test")
        for i in range(3):
            thought = Thought(reasoning="Test", plan="Plan")
            call = ToolCall(tool_name=f"tool_{i}", arguments={})
            step = ReActStep(step_number=i, thought=thought, tool_calls=[call])
            state = state.with_step(step)

        # Should not raise
        guard.check(state)

    def test_is_stuck(self) -> None:
        guard = LoopGuard(LoopGuardConfig(stuck_threshold=2))

        state = AgentState(objective="Test")
        assert guard.is_stuck(state) is False

        for i in range(2):
            thought = Thought(reasoning="Same", plan="Same")
            call = ToolCall(tool_name="same_tool", arguments={})
            step = ReActStep(step_number=i, thought=thought, tool_calls=[call])
            state = state.with_step(step)

        assert guard.is_stuck(state) is True

    def test_get_progress_report(self) -> None:
        guard = LoopGuard(LoopGuardConfig(max_iterations=20, timeout_seconds=300))
        state = AgentState(objective="Test", iteration=5)

        report = guard.get_progress_report(state)

        assert report["iteration"] == 5
        assert report["max_iterations"] == 20
        assert report["iterations_remaining"] == 15
        assert "elapsed_seconds" in report
        assert "time_remaining" in report


# =============================================================================
# Test Parallel Executor
# =============================================================================


class TestParallelExecutor:
    """Tests for ParallelExecutor."""

    def test_execute_single_tool(self) -> None:
        registry = ToolRegistry()
        registry.register(SimpleTool(name="simple", description="Simple"))
        executor = ParallelExecutor(registry)

        call = ToolCall(tool_name="simple", arguments={"message": "test"})
        results = executor.execute_sync([call])

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].result == "Result: test"

    def test_execute_multiple_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(SimpleTool(name="tool1", description="Tool 1"))
        registry.register(SimpleTool(name="tool2", description="Tool 2"))
        executor = ParallelExecutor(registry)

        calls = [
            ToolCall(tool_name="tool1", arguments={"message": "a"}),
            ToolCall(tool_name="tool2", arguments={"message": "b"}),
        ]
        results = executor.execute_sync(calls)

        assert len(results) == 2
        assert all(r.success for r in results)
        # Results should be in same order as calls
        assert results[0].tool_name == "tool1"
        assert results[1].tool_name == "tool2"

    def test_execute_unknown_tool(self) -> None:
        registry = ToolRegistry()
        executor = ParallelExecutor(registry)

        call = ToolCall(tool_name="nonexistent", arguments={})
        results = executor.execute_sync([call])

        assert len(results) == 1
        assert results[0].success is False
        assert "not found" in results[0].error

    def test_execute_with_failure(self) -> None:
        registry = ToolRegistry()
        registry.register(FailingTool(error_type="fatal"))
        executor = ParallelExecutor(registry, default_retries=0)

        call = ToolCall(tool_name="failing_tool", arguments={})
        results = executor.execute_sync([call])

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error_type == "fatal"

    def test_execute_with_retry(self) -> None:
        registry = ToolRegistry()

        # Create a tool that fails first, then succeeds
        class FlakeyTool(BaseTool[str]):
            def __init__(self) -> None:
                super().__init__(name="flakey", description="Flakey tool")
                self.attempts = 0

            def run(self, **kwargs: Any) -> str:
                self.attempts += 1
                if self.attempts < 2:
                    raise TimeoutError("First attempt fails")
                return "Success"

            def classify_error(self, error: Exception) -> str:
                return "retriable"

        tool = FlakeyTool()
        registry.register(tool)
        executor = ParallelExecutor(registry, default_retries=3, retry_delay_ms=10)

        call = ToolCall(tool_name="flakey", arguments={})
        results = executor.execute_sync([call])

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].retry_count == 1

    def test_execute_empty_list(self) -> None:
        registry = ToolRegistry()
        executor = ParallelExecutor(registry)

        results = executor.execute_sync([])
        assert results == []


# =============================================================================
# Test Agent Loop (with mocked LLM)
# =============================================================================


class TestAgentLoop:
    """Tests for AgentLoop (with mocked LLM)."""

    def test_simple_task_completion(self) -> None:
        """Test that a simple task completes successfully."""
        from hmem.agents.react.loop import AgentLoop, AgentLoopConfig

        # Mock LLM client
        mock_llm = MagicMock()
        mock_llm.llm.invoke.return_value.content = [
            {
                "type": "text",
                "text": '{"thought": {"reasoning": "Done", "plan": "Complete"}, "actions": [], "is_complete": true, "final_answer": "Success"}',
            }
        ]
        mock_llm._extract_text.return_value = '{"thought": {"reasoning": "Done", "plan": "Complete"}, "actions": [], "is_complete": true, "final_answer": "Success"}'

        registry = ToolRegistry()
        loop = AgentLoop(mock_llm, registry, AgentLoopConfig(max_iterations=10))

        result = loop.run("Simple task")
        assert result == "Success"

    def test_multi_step_task(self) -> None:
        """Test a task that requires multiple steps."""
        from hmem.agents.react.loop import AgentLoop, AgentLoopConfig

        # First response: use a tool
        first_response = '{"thought": {"reasoning": "Need to search", "plan": "Use tool"}, "actions": [{"tool_name": "test_tool", "arguments": {}}], "is_complete": false, "final_answer": null}'
        # Second response: complete
        second_response = '{"thought": {"reasoning": "Got result", "plan": "Done"}, "actions": [], "is_complete": true, "final_answer": "Result from tool"}'

        mock_llm = MagicMock()
        mock_llm._extract_text.side_effect = [first_response, second_response]
        mock_llm.llm.invoke.side_effect = [
            MagicMock(content=[{"type": "text", "text": first_response}]),
            MagicMock(content=[{"type": "text", "text": second_response}]),
        ]

        registry = ToolRegistry()
        registry.register(SimpleTool(name="test_tool", description="Test"))

        loop = AgentLoop(mock_llm, registry, AgentLoopConfig(max_iterations=10))
        result = loop.run("Multi-step task")

        assert result == "Result from tool"

    def test_format_error_recovery(self) -> None:
        """Test that format errors trigger recovery."""
        from hmem.agents.react.loop import AgentLoop, AgentLoopConfig

        # First response: invalid JSON
        invalid_response = "This is not JSON"
        # Second response: valid JSON
        valid_response = '{"thought": {"reasoning": "Done", "plan": "Complete"}, "actions": [], "is_complete": true, "final_answer": "Recovered"}'

        mock_llm = MagicMock()
        mock_llm._extract_text.side_effect = [invalid_response, valid_response]
        mock_llm.llm.invoke.side_effect = [
            MagicMock(content=[{"type": "text", "text": invalid_response}]),
            MagicMock(content=[{"type": "text", "text": valid_response}]),
        ]

        registry = ToolRegistry()
        loop = AgentLoop(
            mock_llm, registry, AgentLoopConfig(max_iterations=10, max_format_retries=2)
        )

        result = loop.run("Task with format error")
        assert result == "Recovered"

    def test_output_schema_validation(self) -> None:
        """Test that output is validated against schema."""
        from hmem.agents.react.loop import AgentLoop, AgentLoopConfig

        class OutputSchema(BaseModel):
            value: str
            count: int

        mock_llm = MagicMock()
        mock_llm._extract_text.return_value = '{"thought": {"reasoning": "Done", "plan": "Complete"}, "actions": [], "is_complete": true, "final_answer": {"value": "test", "count": 42}}'
        mock_llm.llm.invoke.return_value.content = [
            {
                "type": "text",
                "text": '{"thought": {"reasoning": "Done", "plan": "Complete"}, "actions": [], "is_complete": true, "final_answer": {"value": "test", "count": 42}}',
            }
        ]

        registry = ToolRegistry()
        loop = AgentLoop(mock_llm, registry, AgentLoopConfig(max_iterations=10))

        result = loop.run("Task", output_schema=OutputSchema)
        assert isinstance(result, OutputSchema)
        assert result.value == "test"
        assert result.count == 42

    def test_loop_guard_triggered(self) -> None:
        """Test that loop guard triggers after max iterations."""
        from hmem.agents.react.loop import AgentLoop, AgentLoopConfig

        # Always returns an action (never completes)
        response = '{"thought": {"reasoning": "Working", "plan": "Continue"}, "actions": [{"tool_name": "test_tool", "arguments": {}}], "is_complete": false, "final_answer": null}'

        mock_llm = MagicMock()
        mock_llm._extract_text.return_value = response
        mock_llm.llm.invoke.return_value.content = [{"type": "text", "text": response}]

        registry = ToolRegistry()
        registry.register(SimpleTool(name="test_tool", description="Test"))

        loop = AgentLoop(mock_llm, registry, AgentLoopConfig(max_iterations=3))

        with pytest.raises(LoopGuardError):
            loop.run("Infinite task")
