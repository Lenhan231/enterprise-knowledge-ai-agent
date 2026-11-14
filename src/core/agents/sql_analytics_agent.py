"""Backward-compatible imports for the SQL analytics agent."""

from core.agents.sql.agent import AnalyticsPermissionDenied, SQLAnalyticsAgent

__all__ = ["AnalyticsPermissionDenied", "SQLAnalyticsAgent"]
