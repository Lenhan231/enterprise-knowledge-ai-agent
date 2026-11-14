"""Compatibility alias for SQL schema discovery."""

import sys
from core.agents.sql import schema as _implementation

sys.modules[__name__] = _implementation
