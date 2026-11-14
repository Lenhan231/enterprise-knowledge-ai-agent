"""Compatibility alias for the SQL analytics wrapper."""

import sys
from core.agents.sql import analytics_agent as _implementation

sys.modules[__name__] = _implementation
