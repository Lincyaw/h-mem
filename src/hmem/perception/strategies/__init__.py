"""Pluggable folding strategies for context management."""

from hmem.perception.strategies.folding import FoldingStrategy
from hmem.perception.strategies.token_based import TokenBasedFolder
from hmem.perception.strategies.time_window import TimeWindowFolder

__all__ = ["FoldingStrategy", "TokenBasedFolder", "TimeWindowFolder"]
