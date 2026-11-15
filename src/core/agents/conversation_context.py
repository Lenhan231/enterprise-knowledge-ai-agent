"""Compatibility alias for decision-support conversation state."""

import sys
from core.agents.decision_support import conversation_context as _implementation

sys.modules[__name__] = _implementation
