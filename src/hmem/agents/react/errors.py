"""Error hierarchy for the ReAct Agent Loop.

Error types are classified by how they should be handled:
- ToolError: Retriable - the tool failed but we can try again
- FormatError: Self-correctable - LLM output was malformed
- FatalError: Unrecoverable - must stop execution
- LoopGuardError: Safety limit reached
"""


class AgentError(Exception):
    """Base class for all agent errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ToolError(AgentError):
    """Tool execution failed (retriable).

    This error indicates a transient failure that may succeed on retry:
    - Network timeouts
    - Rate limiting
    - Temporary service unavailability
    """

    def __init__(
        self,
        message: str,
        tool_name: str,
        retry_count: int = 0,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details)
        self.tool_name = tool_name
        self.retry_count = retry_count


class FormatError(AgentError):
    """LLM output format error (self-correctable).

    The LLM produced output that couldn't be parsed. The agent will
    send an error message back to the LLM so it can self-correct.
    """

    def __init__(
        self,
        message: str,
        raw_output: str,
        expected_format: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details)
        self.raw_output = raw_output
        self.expected_format = expected_format


class FatalError(AgentError):
    """Unrecoverable error (immediate termination).

    This error indicates a fundamental problem that cannot be fixed:
    - Logic errors in the agent's reasoning
    - Invalid configuration
    - Security violations
    - Resource exhaustion
    """

    def __init__(
        self,
        message: str,
        cause: Exception | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details)
        self.cause = cause


class LoopGuardError(AgentError):
    """Loop guard triggered (safety limit reached).

    This error is raised when the agent appears to be stuck:
    - Maximum iterations exceeded
    - Timeout exceeded
    - Repeated identical actions detected
    """

    def __init__(
        self,
        message: str,
        guard_type: str,
        current_value: int | float,
        threshold: int | float,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details)
        self.guard_type = guard_type
        self.current_value = current_value
        self.threshold = threshold
