"""Compatibility alias for the SQL assistant endpoint."""

import sys
from core.agents.sql import assistant_endpoint as _implementation

sys.modules[__name__] = _implementation
