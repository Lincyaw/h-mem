"""Parallel tool executor with retry logic.

Executes multiple tool calls concurrently and handles retries
for retriable errors.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from hmem.agents.react.tool_base import ToolRegistry
from hmem.agents.react.types import Observation, ToolCall

logger = logging.getLogger(__name__)


class ParallelExecutor:
    """Executes tool calls in parallel with retry logic.

    Uses a thread pool for concurrent execution of blocking tools.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        max_workers: int = 4,
        default_retries: int = 3,
        retry_delay_ms: int = 100,
    ) -> None:
        """Initialize the executor.

        Args:
            registry: Tool registry for looking up tools
            max_workers: Maximum concurrent tool executions
            default_retries: Default retry count for retriable errors
            retry_delay_ms: Delay between retries in milliseconds
        """
        self.registry = registry
        self.max_workers = max_workers
        self.default_retries = default_retries
        self.retry_delay_ms = retry_delay_ms

    def execute_sync(self, calls: list[ToolCall]) -> list[Observation]:
        """Execute tool calls concurrently using thread pool.

        Args:
            calls: List of tool calls to execute

        Returns:
            List of observations in the same order as calls
        """
        if not calls:
            return []

        if len(calls) == 1:
            # Skip thread pool overhead for single call
            return [self._execute_single_sync(calls[0])]

        results: dict[str, Observation] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_call = {
                executor.submit(self._execute_single_sync, call): call for call in calls
            }
            for future in as_completed(future_to_call):
                call = future_to_call[future]
                try:
                    observation = future.result()
                    results[call.id] = observation
                except Exception as e:
                    # This shouldn't happen since _execute_single_sync catches all
                    results[call.id] = Observation(
                        call_id=call.id,
                        tool_name=call.tool_name,
                        success=False,
                        error=f"Executor error: {e}",
                        error_type="fatal",
                        execution_time_ms=0,
                    )

        # Return in original order
        return [results[call.id] for call in calls]

    def _execute_single_sync(self, call: ToolCall) -> Observation:
        """Execute a single tool call with retry logic (sync).

        Args:
            call: The tool call to execute

        Returns:
            Observation with result or error
        """
        tool = self.registry.get(call.tool_name)
        if tool is None:
            return Observation(
                call_id=call.id,
                tool_name=call.tool_name,
                success=False,
                error=f"Tool '{call.tool_name}' not found",
                error_type="fatal",
                execution_time_ms=0,
            )

        max_retries = (
            call.max_retries if call.max_retries is not None else self.default_retries
        )
        retry_count = 0

        while True:
            start_time = time.monotonic()
            try:
                result = tool.run(**call.arguments)
                execution_time_ms = int((time.monotonic() - start_time) * 1000)
                return Observation(
                    call_id=call.id,
                    tool_name=call.tool_name,
                    success=True,
                    result=result,
                    execution_time_ms=execution_time_ms,
                    retry_count=retry_count,
                )
            except Exception as e:
                execution_time_ms = int((time.monotonic() - start_time) * 1000)
                error_type = tool.classify_error(e)

                if error_type == "retriable" and retry_count < max_retries:
                    retry_count += 1
                    logger.warning(
                        f"Tool {call.tool_name} failed (attempt {retry_count}/{max_retries}): {e}"
                    )
                    time.sleep(self.retry_delay_ms / 1000)
                    continue

                return Observation(
                    call_id=call.id,
                    tool_name=call.tool_name,
                    success=False,
                    error=str(e),
                    error_type=error_type,
                    execution_time_ms=execution_time_ms,
                    retry_count=retry_count,
                )
