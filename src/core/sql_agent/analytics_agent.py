"""Summarize validated SQL results without changing their data."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from core.agents.base import BaseAgent
from core.sql_agent.agent import SQLAnalyticsAgent, payload_to_agent_result
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
        rows = result.get("rows", [])
        null_columns = [column for column in (rows[0] if rows else {})
                        if all(row.get(column) is None for row in rows)]
        if null_columns:
            columns = ", ".join(null_columns)
            if any(char in question for char in "ăâđêôơưáàảãạấầẩẫậắằẳẵặếềểễệốồổỗộớờởỡợứừửữựýỳỷỹỵ"):
                answer = (f"Truy vấn đã chạy nhưng {columns} trả về NULL. Điều này chưa đủ để kết luận "
                          "không có doanh thu: có thể không có bản ghi phù hợp hoặc các bản ghi đều thiếu giá trị này.")
            else:
                answer = (f"The query completed, but {columns} is NULL. This does not establish zero revenue: "
                          "there may be no matching rows, or the matching rows may have missing values.")
            if citations:
                answer += "\n\nSources: " + "; ".join(citations)
            return {**result, "answer": answer}
        if len(rows) == 1 and {
            "month", "previous_month", "revenue", "previous_month_revenue",
            "revenue_change", "revenue_change_fraction",
        } <= set(rows[0]):
            answer = self._month_over_month_answer(rows[0], question)
            if citations:
                answer += "\n\nSources: " + "; ".join(citations)
            return {**result, "answer": answer}
        prompt = ANALYTICS_SUMMARY_PROMPT.format(
            question=question,
            citations=', '.join(citations),
            metrics=json.dumps(result.get('metadata', {}).get('metrics', {}), ensure_ascii=False),
            limitations=json.dumps(limitations, ensure_ascii=False),
            interpretation=json.dumps(result.get('metadata',{}).get('semantic_interpretation'),ensure_ascii=False),
            rows=json.dumps(rows, default=str, ensure_ascii=False),
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

    @staticmethod
    def _month_over_month_answer(row: dict[str, Any], question: str) -> str:
        def month_label(value):
            value = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
            return f"{value.month:02}/{value.year}"

        def amount(value):
            return format(Decimal(str(value)), ",f")

        current, previous = Decimal(str(row["revenue"])), Decimal(str(row["previous_month_revenue"]))
        change = Decimal(str(row["revenue_change"]))
        fraction = row["revenue_change_fraction"]
        period = f"{month_label(row['month'])} so với {month_label(row['previous_month'])}"
        delta = amount(abs(change))
        if fraction is None:
            rate = ""
        else:
            try:
                rate = f" ({Decimal(str(fraction)) * 100:+.2f}%)"
            except (InvalidOperation, ValueError):
                rate = ""
        if any(char in question for char in "ăâđêôơưáàảãạấầẩẫậắằẳẵặếềểễệốồổỗộớờởỡợứừửữựýỳỷỹỵ"):
            direction = "tăng" if change > 0 else "giảm" if change < 0 else "không đổi"
            suffix = f" {direction} {delta}{rate} so với tháng trước." if change else " không đổi so với tháng trước."
            return (f"Doanh thu tháng {month_label(row['month'])} là {amount(current)}; tháng "
                    f"{month_label(row['previous_month'])} là {amount(previous)}.{suffix}")
        direction = "increased" if change > 0 else "decreased" if change < 0 else "was unchanged"
        suffix = f" {direction} by {delta}{rate}." if change else " was unchanged."
        return (f"Revenue for {period}: {amount(current)}; previous month: {amount(previous)}."
                f"{suffix}")
