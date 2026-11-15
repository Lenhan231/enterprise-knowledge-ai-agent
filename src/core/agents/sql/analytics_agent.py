"""Expose validated SQL results to the shared answer composer."""

from __future__ import annotations

from typing import Any

from core.agents.base import BaseAgent
from core.agents.sql.agent import SQLAnalyticsAgent, payload_to_agent_result
from core.models.agents import AgentResult


class AnalyticsAgent(BaseAgent):
    """Run the SQL specialist and return structured results without summarizing them."""

    def __init__(self, sql_agent: SQLAnalyticsAgent) -> None:
        self.sql_agent = sql_agent

    async def run(self, request: Any) -> AgentResult:
        return payload_to_agent_result(await self.run_payload(request))

    async def run_payload(self, request: Any) -> dict[str, Any]:
        return await self.sql_agent.run_payload(request)

    async def close(self) -> None:
        await self.sql_agent.close()
