"""Layer 1: Perception & Working Memory.

Handles current interaction flow (inside-trail) and maintains
"consciousness" continuity within limited context windows.
"""

from hmem.perception.context_manager import ContextManager
from hmem.perception.sensory_buffer import SensoryBuffer

__all__ = ["ContextManager", "SensoryBuffer"]
