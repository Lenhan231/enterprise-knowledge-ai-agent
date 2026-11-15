"""Compatibility alias for bounded agent execution."""

import sys
from core.agents.orchestration import execution as _implementation

sys.modules[__name__] = _implementation
