"""Compatibility alias for the decision-support router."""

import sys
from core.agents.orchestration import router as _implementation

sys.modules[__name__] = _implementation
