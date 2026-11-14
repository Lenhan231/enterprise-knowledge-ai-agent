"""Compatibility alias for the SQL agent's previous module path."""

import sys
from core.agents.sql import agent as _implementation

sys.modules[__name__] = _implementation
