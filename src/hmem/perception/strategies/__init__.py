"""Pluggable folding strategies for context management."""

from hmem.perception.strategies.folding import FoldingStrategy
from hmem.perception.strategies.token_based import TokenBasedFolder

__all__ = ["FoldingStrategy", "TokenBasedFolder"]
