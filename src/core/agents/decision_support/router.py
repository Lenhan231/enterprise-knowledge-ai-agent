"""Compatibility alias; workflow coordination lives in orchestrator.py."""
import sys

from core.agents.decision_support import orchestrator as _implementation

sys.modules[__name__] = _implementation
