"""Compatibility alias; orchestration code now lives in core.agents.orchestration."""
import sys
from core.agents.orchestration import planning as _implementation
sys.modules[__name__] = _implementation
