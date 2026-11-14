"""Compatibility alias for the SQL analytics agent."""

import sys
from core.agents.sql import agent as _implementation

sys.modules[__name__] = _implementation
