"""Summarize validated SQL results without changing their data."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from core.agents.base import BaseAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent, payload_to_agent_result
from core.models.agents import AgentResult
from core.latency import measure
from core.agents.runtime import generate
from core.prompts.agents import ANALYTICS_SUMMARY_PROMPT


class AnalyticsAgent(BaseAgent):
    def __init__(self, sql_agent: SQLAnalyticsAgent) -> None:
        self.sql_agent = sql_agent

    async def run(self, request: Any) -> AgentResult:
        return payload_to_agent_result(await self.run_payload(request))

    async def run_payload(self, request: Any) -> dict[str, Any]:
        result = await self.sql_agent.run_payload(request)
        if not result.get("ok"):
            return result
        question = SQLAnalyticsAgent._query_text(request)
        sources = result.get("metadata", {}).get("source", [])
        citations = [f"[S{index}] {source}" for index, source in enumerate(sources, start=1)]
        limitations = result.get("limitations", [])
        prompt = ANALYTICS_SUMMARY_PROMPT.format(
            question=question,
            citations=', '.join(citations),
            metrics=json.dumps(result.get('metadata', {}).get('metrics', {}), ensure_ascii=False),
            limitations=json.dumps(limitations, ensure_ascii=False),
            interpretation=json.dumps(result.get('metadata',{}).get('semantic_interpretation'),ensure_ascii=False),
            rows=json.dumps(result['rows'], default=str, ensure_ascii=False),
        )
        try:
            with measure("answer_generation"):
                answer = await generate(self.sql_agent._provider(), prompt, timeout=60)
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("empty analytics summary")
            answer = answer.strip()[:4_000]
        except Exception:
            answer = self._fallback_answer(result["rows"], sources)
        if citations:
            answer += "\n\nSources: " + "; ".join(citations)
        return {**result, "answer": answer}

    async def close(self) -> None:
        await self.sql_agent.close()

    @staticmethod
    def _fallback_answer(rows: list[dict[str, Any]], sources: list[str]) -> str:
        names = ", ".join(sources) or "the approved data sources"
        return f"The query returned {len(rows)} row(s) from {names}. See the result rows for details."
