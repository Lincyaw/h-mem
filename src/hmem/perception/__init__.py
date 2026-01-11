"""Layer 1: Perception & Working Memory.

Handles current interaction flow (inside-trail) and maintains
"consciousness" continuity within limited context windows.

Note: ContextManager functionality has been integrated into MemorySystem.chat()
to simplify the API. Folding strategies remain available as plugins.
"""

from hmem.perception.sensory_buffer import SensoryBuffer

__all__ = ["SensoryBuffer"]
