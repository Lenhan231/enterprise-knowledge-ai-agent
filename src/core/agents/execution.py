"""Compatibility alias for bounded agent execution."""

import sys
from core.agents.decision_support import execution as _implementation

sys.modules[__name__] = _implementation
