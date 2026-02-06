"""Base tool infrastructure for the ReAct Agent Loop.

Provides BaseTool ABC and ToolRegistry for managing available tools.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ToolConfig(BaseModel):
    """Configuration for tool execution."""

    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_ms: int = Field(default=100, ge=0)
    timeout_ms: int = Field(default=30000, ge=1000, le=300000)


class ToolSchema(BaseModel):
    """JSON Schema-like description of a tool's parameters."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class BaseTool(ABC, Generic[T]):
    """Abstract base class for ReAct tools.

    Tools are the actions that an agent can take. Each tool:
    - Has a unique name and description
    - Defines its parameter schema
    - Implements run() to execute the action
    - Classifies errors as retriable or fatal
    """

    name: str
    description: str
    config: ToolConfig

    def __init__(
        self,
        name: str,
        description: str,
        config: ToolConfig | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.config = config or ToolConfig()

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> T:
        """Execute the tool with the given arguments.

        Args:
            *args: Tool-specific positional arguments
            **kwargs: Tool-specific keyword arguments

        Returns:
            Tool-specific result type

        Raises:
            ToolError: If execution fails (may be retriable)
            FatalError: If execution fails unrecoverably
        """

    def classify_error(self, error: Exception) -> Literal["retriable", "fatal"]:
        """Classify an error for retry decisions.

        Override this to customize error classification for specific tools.
        Default: Network/timeout errors are retriable, others are fatal.
        """
        error_type = type(error).__name__.lower()
        retriable_patterns = [
            "timeout",
            "connection",
            "network",
            "rate",
            "throttl",
            "temporary",
            "unavailable",
            "retry",
        ]
        for pattern in retriable_patterns:
            if pattern in error_type or pattern in str(error).lower():
                return "retriable"
        return "fatal"

    def get_schema(self) -> ToolSchema:
        """Get the JSON Schema for this tool's parameters.

        Override to provide custom schema. Default returns basic info.
        """
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={},
            required=[],
        )


class ToolRegistry:
    """Registry of available tools for the agent.

    Provides tool lookup, listing, and schema generation.
    Thread-safe for concurrent access.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool[Any]] = {}

    def register(self, tool: BaseTool[Any]) -> None:
        """Register a tool, replacing any existing tool with the same name."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool[Any] | None:
        """Get a tool by name, or None if not found."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_all_schemas(self) -> list[ToolSchema]:
        """Get schemas for all registered tools."""
        return [tool.get_schema() for tool in self._tools.values()]

    def get_all_descriptions(self) -> str:
        """Format all tool descriptions for inclusion in prompts."""
        lines = []
        for tool in self._tools.values():
            schema = tool.get_schema()
            params_str = ""
            if schema.parameters:
                param_parts = []
                for pname, pinfo in schema.parameters.items():
                    req = "(required)" if pname in schema.required else "(optional)"
                    ptype = pinfo.get("type", "any")
                    pdesc = pinfo.get("description", "")
                    param_parts.append(f"    - {pname} {req}: {ptype} - {pdesc}")
                params_str = "\n" + "\n".join(param_parts)
            lines.append(f"- {tool.name}: {tool.description}{params_str}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
