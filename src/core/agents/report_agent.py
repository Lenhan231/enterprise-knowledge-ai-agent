"""Compatibility alias for the Report agent."""

import sys
from core.agents.report import agent as _implementation

sys.modules[__name__] = _implementation
