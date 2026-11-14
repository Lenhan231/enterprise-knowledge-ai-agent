"""Compatibility alias for decision-support planning."""

import sys
from core.agents.decision_support import planning as _implementation

sys.modules[__name__] = _implementation
