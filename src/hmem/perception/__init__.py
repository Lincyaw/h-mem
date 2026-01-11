"""Layer 1: Perception & Working Memory.

Handles current interaction flow and maintains session continuity
within limited context windows. Folding strategies are available
as plugins for intelligent context compression.
"""

from hmem.perception.sensory_buffer import SensoryBuffer

__all__ = ["SensoryBuffer"]
