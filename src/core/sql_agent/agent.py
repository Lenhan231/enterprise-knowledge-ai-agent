"""Compatibility imports for the SQL agent's previous module path."""

from core.agents.sql.agent import (
    AnalyticsPermissionDenied,
    SQLAnalyticsAgent,
    payload_to_agent_result,
)

__all__ = ["AnalyticsPermissionDenied", "SQLAnalyticsAgent", "payload_to_agent_result"]
