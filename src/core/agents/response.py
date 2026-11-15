"""Compatibility alias for evidence-based response synthesis."""

import sys
from core.agents.orchestration import response as _implementation

sys.modules[__name__] = _implementation
