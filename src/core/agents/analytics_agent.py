"""Deterministic business interpretation over SQLAnalyticsAgent results."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

try:
    from core.agents.base import BaseAgent
    from core.agents.sql_analytics_agent import SQLAnalyticsAgent, payload_to_agent_result
    from core.models.agents import AgentResult
except ModuleNotFoundError:  # Support importing the package as ``src.core``.
    from src.core.agents.base import BaseAgent
    from src.core.agents.sql_analytics_agent import SQLAnalyticsAgent, payload_to_agent_result
    from src.core.models.agents import AgentResult


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


class AnalyticsAgent(BaseAgent):
    def __init__(self, sql_agent: SQLAnalyticsAgent) -> None:
        self.sql_agent = sql_agent

    async def run(self, request: Any) -> AgentResult:
        return payload_to_agent_result(await self.run_payload(request))

    async def run_payload(self, request: Any) -> dict[str, Any]:
        result = await self.sql_agent.run_payload(request)
        if not result.get("ok"):
            return result

        operation = result["operation"]
        rows = result["rows"]
        if operation == "revenue_cogs_by_month":
            analysis = self._analyze_sales(rows)
        elif operation == "revenue_by_region":
            analysis = self._analyze_regions(rows)
        elif operation == "inventory_by_category":
            analysis = self._analyze_inventory(rows)
        else:
            return {**result, "ok": False, "limitations": ["Phép phân tích chưa được hỗ trợ."]}

        return {**result, **analysis}

    async def close(self) -> None:
        await self.sql_agent.close()

    @staticmethod
    def _analyze_sales(rows: list[dict[str, Any]]) -> dict[str, Any]:
        metrics: list[dict[str, Any]] = []
        findings: list[str] = []
        for row in rows:
            revenue = _decimal(row.get("revenue"))
            cogs = _decimal(row.get("cogs"))
            gross_profit = revenue - cogs
            gross_margin = gross_profit / revenue if revenue else None
            metrics.append({
                "period": row.get("month"),
                "revenue": revenue,
                "cogs": cogs,
                "gross_profit": gross_profit,
                "gross_margin": gross_margin,
            })
            if gross_profit < 0:
                findings.append(f"{row.get('month')}: lợi nhuận gộp âm {abs(gross_profit)}.")
            else:
                findings.append(f"{row.get('month')}: lợi nhuận gộp dương {gross_profit}.")
        return {
            "analysis": "sales_performance",
            "metrics": metrics,
            "findings": findings,
            "recommendations": [
                "Kiểm tra giá vốn, chiết khấu và chính sách giá khi lợi nhuận gộp âm."
            ] if any(item["gross_profit"] < 0 for item in metrics) else [],
        }

    @staticmethod
    def _analyze_regions(rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"analysis": "regional_revenue", "metrics": [], "findings": ["Không có dữ liệu trong kỳ."], "recommendations": []}
        values = [(row.get("region"), _decimal(row.get("revenue"))) for row in rows]
        total = sum(value for _, value in values)
        metrics = [
            {"region": region, "revenue": revenue, "share": revenue / total if total else None}
            for region, revenue in values
        ]
        highest = max(values, key=lambda item: item[1])
        return {
            "analysis": "regional_revenue",
            "metrics": metrics,
            "findings": [f"{highest[0]} có doanh thu cao nhất: {highest[1]}."],
            "recommendations": [
                "So sánh thêm số lượng đơn hàng và giá trị đơn hàng trung bình trước khi kết luận nguyên nhân chênh lệch vùng."
            ],
            "limitations": [
                "Doanh thu theo khu vực được tái dựng từ đơn hàng và chi tiết đơn hàng, không lấy từ commerce.sales."
            ],
        }

    @staticmethod
    def _analyze_inventory(rows: list[dict[str, Any]]) -> dict[str, Any]:
        metrics: list[dict[str, Any]] = []
        for row in rows:
            observed = int(row.get("products_observed") or 0)
            stockout = int(row.get("stockout_products") or 0)
            metrics.append({
                **row,
                "stockout_rate": stockout / observed if observed else None,
                "reorder_rate": int(row.get("reorder_products") or 0) / observed if observed else None,
            })
        highest = max(metrics, key=lambda row: row["stockout_rate"] or 0, default=None)
        findings = [
            f"{highest['category']} có tỷ lệ hết hàng cao nhất: {highest['stockout_rate']:.2%}."
        ] if highest else ["Không có dữ liệu tồn kho tại thời điểm này."]
        return {
            "analysis": "inventory_by_category",
            "metrics": metrics,
            "findings": findings,
            "recommendations": [
                "Kiểm tra các SKU được đánh dấu hết hàng trước khi thay đổi lượng đặt hàng."
            ] if highest else [],
            "limitations": [
                "Tỷ lệ hết hàng được tính bằng số SKU được đánh dấu hết hàng chia cho số SKU quan sát; không phải tỷ lệ theo số ngày-sản phẩm."
            ],
        }
