"""LangGraph-based agents for memory system operations.

This module provides intelligent agents for various memory operations:
- LLMClient: Lightweight LLM wrapper for text processing tasks
- AgentState: Base state TypedDict for LangGraph agents

LLMClient is a simple class for LLM operations (no LangGraph overhead).
"""

from hmem.agents.base import AgentState
from hmem.agents.llm import LLMClient

__all__ = [
    "AgentState",
    "LLMClient",
]
