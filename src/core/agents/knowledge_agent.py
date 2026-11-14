"""Compatibility alias for the Knowledge agent."""

import sys
from core.agents.knowledge import agent as _implementation

sys.modules[__name__] = _implementation
