"""Deterministic business interpretation over SQLAnalyticsAgent results."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.core.agents.sql_analytics_agent import SQLAnalyticsAgent


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


class AnalyticsAgent:
    def __init__(self, sql_agent: SQLAnalyticsAgent) -> None:
        self.sql_agent = sql_agent

    async def run(self, request: Any) -> dict[str, Any]:
        result = await self.sql_agent.run(request)
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
            return {**result, "ok": False, "limitations": ["Unknown analysis operation"]}

        return {**result, **analysis}

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
                findings.append(f"{row.get('month')}: gross profit âm {abs(gross_profit)}.")
            else:
                findings.append(f"{row.get('month')}: gross profit dương {gross_profit}.")
        return {
            "analysis": "sales_performance",
            "metrics": metrics,
            "findings": findings,
            "recommendations": [
                "Kiểm tra giá vốn, discount và chính sách giá khi gross profit âm."
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
            "recommendations": ["So sánh thêm order count và AOV trước khi kết luận nguyên nhân chênh lệch vùng."],
            "limitations": ["Regional revenue được tái dựng từ orders và order_items, không phải commerce.sales."],
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
            f"{highest['category']} có stockout rate cao nhất: {highest['stockout_rate']:.2%}."
        ] if highest else ["Không có dữ liệu inventory trong snapshot này."]
        return {
            "analysis": "inventory_by_category",
            "metrics": metrics,
            "findings": findings,
            "recommendations": [
                "Kiểm tra các SKU có stockout_flag = true trước khi thay đổi lượng đặt hàng."
            ] if highest else [],
            "limitations": ["stockout_rate = flagged SKU / observed SKU; không phải tỷ lệ product-days."],
        }
