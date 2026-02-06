"""ReAct Agent Loop implementation for h-mem.

This module provides a ReAct (Reasoning + Acting) style agent loop
with parallel tool execution, dynamic skill loading, and robust error handling.
"""

from hmem.agents.react.errors import (
    AgentError,
    FatalError,
    FormatError,
    LoopGuardError,
    ToolError,
)
from hmem.agents.react.executor import ParallelExecutor
from hmem.agents.react.extraction_agent import (
    ExtractionAgent,
    ExtractedKnowledge,
    create_extraction_agent,
)
from hmem.agents.react.guard import LoopGuard, LoopGuardConfig
from hmem.agents.react.loop import AgentLoop, AgentLoopConfig
from hmem.agents.react.tasks import (
    ExtractionOutput,
    InductionOutput,
    RetrievalOutput,
    TaskConfig,
    get_output_schema,
    get_task_config,
)
from hmem.agents.react.tool_base import BaseTool, ToolConfig, ToolRegistry
from hmem.agents.react.types import (
    AgentState,
    Observation,
    ReActStep,
    Thought,
    ToolCall,
)

__all__ = [
    # Types
    "AgentState",
    "Thought",
    "ToolCall",
    "Observation",
    "ReActStep",
    # Errors
    "AgentError",
    "ToolError",
    "FormatError",
    "FatalError",
    "LoopGuardError",
    # Tool infrastructure
    "BaseTool",
    "ToolConfig",
    "ToolRegistry",
    # Core components
    "AgentLoop",
    "AgentLoopConfig",
    "ParallelExecutor",
    "LoopGuard",
    "LoopGuardConfig",
    # Extraction agent
    "ExtractionAgent",
    "ExtractedKnowledge",
    "create_extraction_agent",
    # Task types
    "TaskConfig",
    "ExtractionOutput",
    "InductionOutput",
    "RetrievalOutput",
    "get_task_config",
    "get_output_schema",
]
