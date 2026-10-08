"""Explain approved commerce aggregates using only requested ontology metrics."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from core.agents.base import BaseAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent, payload_to_agent_result
from core.analytics.metric_ontology import resolve_metric_names
from core.models.agents import AgentResult


def _number(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _format(value: Decimal, percent: bool = False) -> str:
    return f"{value * 100:,.2f}%" if percent else f"{value:,.2f}"


LABELS = {
    "revenue": "Doanh thu", "cogs": "Giá vốn", "gross_profit": "Lợi nhuận gộp",
    "regional_revenue": "Doanh thu", "stock_on_hand": "Tồn kho",
    "stockout_rate": "Tỷ lệ hết hàng", "sell_through_rate": "Tỷ lệ bán hết",
    "fill_rate": "Tỷ lệ đáp ứng", "days_of_supply": "Số ngày đủ hàng",
}
INVENTORY_FIELDS = {
    "stock_on_hand": "stock_on_hand", "stockout_rate": "stockout_rate",
    "sell_through_rate": "avg_sell_through_rate", "fill_rate": "avg_fill_rate",
    "days_of_supply": "avg_days_of_supply",
}
PERCENT_METRICS = {"stockout_rate", "sell_through_rate", "fill_rate"}


class AnalyticsAgent(BaseAgent):
    def __init__(self, sql_agent: SQLAnalyticsAgent) -> None:
        self.sql_agent = sql_agent

    async def run(self, request: Any) -> AgentResult:
        return payload_to_agent_result(await self.run_payload(request))

    async def run_payload(self, request: Any) -> dict[str, Any]:
        question = SQLAnalyticsAgent._query_text(request)
        result = await self.sql_agent.run_payload(request)
        if not result.get("ok"):
            return result

        operation = result["operation"]
        requested = resolve_metric_names(question)
        filters = result.get("metadata", {}).get("filters", {})
        if operation == "revenue_cogs_by_month":
            analysis = self._sales(result["rows"], requested, question)
        elif operation == "revenue_by_region":
            analysis = self._regions(result["rows"], question, filters.get("region", []),
                                     result.get("metadata", {}).get("total_revenue"))
        else:
            analysis = self._inventory(result["rows"], requested, question, filters.get("category", []))
        return {**result, **analysis}

    async def close(self) -> None:
        await self.sql_agent.close()

    @staticmethod
    def _sales(rows: list[dict[str, Any]], requested: set[str], question: str) -> dict[str, Any]:
        metrics = [{"period": row.get("month"), "revenue": _number(row.get("revenue")),
                    "cogs": _number(row.get("cogs")),
                    "gross_profit": _number(row.get("revenue")) - _number(row.get("cogs"))}
                   for row in rows]
        selected = [name for name in ("revenue", "cogs", "gross_profit") if name in requested]
        if not selected:
            return AnalyticsAgent._clarify_metric()
        monthly = bool(re.search(r"theo tháng|tháng nào|mỗi tháng|từng tháng|các tháng", question.casefold()))
        ranking = bool(re.search(r"thấp nhất|ít nhất|nhỏ nhất|cao nhất|nhiều nhất|lớn nhất|lowest|highest",
                                 question.casefold()))
        if monthly:
            if ranking and len(selected) != 1:
                return AnalyticsAgent._clarify_metric()
            display = []
            for row in metrics:
                year, month = str(row["period"])[:7].split("-")
                display.append({"month": f"Tháng {month}/{year}", **{
                    name: _format(row[name]) for name in selected}})
            if len(selected) == 1:
                name = selected[0]
                values = [{"month": shown["month"], "value": raw[name]}
                          for raw, shown in zip(metrics, display)]
                _, answer = AnalyticsAgent._evaluate(values, "month", "value", LABELS[name], question, [])
            else:
                answer = "; ".join(
                    f"{row['month']} — " + ", ".join(f"{LABELS[name]}: {row[name]}" for name in selected)
                    for row in display) + "."
            if "gross_profit" in selected:
                answer += " gross_profit = revenue - cogs."
            return {
                "answer": answer, "analysis": "sales_performance", "metrics": metrics,
                "table": {"columns": [{"key": "month", "label": "Tháng"}] +
                          [{"key": name, "label": LABELS[name]} for name in selected], "rows": display},
                "findings": [answer], "recommendations": [],
            }
        if ranking and len(metrics) > 1:
            return {"ok": False, "answer": "Vui lòng làm rõ muốn xếp hạng theo tháng hay kỳ khác.",
                    "limitations": ["Chưa xác định được mức thời gian cho phép so sánh."]}
        revenue = sum((_number(row.get("revenue")) for row in rows), Decimal(0))
        cogs = sum((_number(row.get("cogs")) for row in rows), Decimal(0))
        values = {"revenue": revenue, "cogs": cogs, "gross_profit": revenue - cogs}
        answer = "; ".join(f"{LABELS[name]}: {_format(values[name])}" for name in selected)
        if "gross_profit" in selected:
            answer += " (gross_profit = revenue - cogs)"
        table = {
            "columns": [{"key": "metric", "label": "Chỉ số"}, {"key": "value", "label": "Giá trị"}],
            "rows": [{"metric": LABELS[name], "value": _format(values[name])} for name in selected],
        }
        return {
            "answer": answer + ".", "analysis": "sales_performance", "table": table,
            "metrics": metrics,
            "findings": [answer + "."], "recommendations": [],
        }

    @staticmethod
    def _regions(rows: list[dict[str, Any]], question: str, groups: list[str],
                 total_revenue: Any = None) -> dict[str, Any]:
        values = [{"region": row["region"], "revenue": _number(row["revenue"])} for row in rows]
        total = _number(total_revenue) if total_revenue is not None else sum(
            (row["revenue"] for row in values), Decimal(0))
        values, answer = AnalyticsAgent._evaluate(values, "region", "revenue", "Doanh thu", question, groups)
        metrics = [{**row, "share": row["revenue"] / total if total else None} for row in values]
        display = [{"region": row["region"], "revenue": _format(row["revenue"]),
                    "share": _format(row["share"], True) if row["share"] is not None else "—"}
                   for row in metrics]
        return {
            "answer": answer, "analysis": "regional_revenue", "metrics": metrics,
            "table": {"columns": [{"key": "region", "label": "Khu vực"},
                                  {"key": "revenue", "label": "Doanh thu"},
                                  {"key": "share", "label": "Tỷ trọng"}], "rows": display},
            "findings": [answer], "recommendations": [],
            "limitations": ["Doanh thu khu vực tính từ đơn đã giao; có thể khác commerce.sales."],
        }

    @staticmethod
    def _inventory(rows: list[dict[str, Any]], requested: set[str], question: str,
                   groups: list[str]) -> dict[str, Any]:
        selected = [name for name in INVENTORY_FIELDS if name in requested]
        if not selected:
            return AnalyticsAgent._clarify_metric()
        metrics = []
        for row in rows:
            observed = _number(row.get("products_observed"))
            metric = {**row, "stockout_rate": _number(row.get("stockout_products")) / observed if observed else None,
                      "reorder_rate": _number(row.get("reorder_products")) / observed if observed else None}
            metrics.append(metric)
        primary = selected[0]
        field = INVENTORY_FIELDS[primary]
        values = [{"category": row["category"], "value": _number(row.get(field))} for row in metrics]
        values, answer = AnalyticsAgent._evaluate(values, "category", "value", LABELS[primary],
                                                   question, groups, percent=primary in PERCENT_METRICS)
        if groups:
            metrics = [row for row in metrics if row["category"] in groups]
        if len(selected) > 1:
            answer = "; ".join(
                f"{row['category']} — " + ", ".join(
                    f"{LABELS[name]}: {_format(_number(row.get(INVENTORY_FIELDS[name])), name in PERCENT_METRICS)}"
                    for name in selected) for row in metrics) + "."
        columns = [{"key": "category", "label": "Danh mục"}]
        columns += [{"key": name, "label": LABELS[name]} for name in selected]
        if primary == "stock_on_hand":
            columns += [{"key": name, "label": label} for name, label in
                        (("stockout_products", "SKU hết hàng"), ("reorder_products", "SKU cần nhập"),
                         ("overstock_products", "SKU dư tồn"))]
        display = []
        for row in metrics:
            entry = {"category": row["category"]}
            for name in selected:
                entry[name] = _format(_number(row.get(INVENTORY_FIELDS[name])), name in PERCENT_METRICS)
            if primary == "stock_on_hand":
                entry.update({name: row.get(name, 0) for name in
                              ("stockout_products", "reorder_products", "overstock_products")})
            display.append(entry)
        return {
            "answer": answer, "analysis": "inventory_by_category", "metrics": metrics,
            "table": {"columns": columns, "rows": display}, "findings": [answer],
            "recommendations": [],
            "limitations": ["Tỷ lệ hết hàng = số SKU gắn cờ hết hàng / số SKU quan sát."]
            if primary == "stockout_rate" else [],
        }

    @staticmethod
    def _evaluate(rows: list[dict[str, Any]], dimension: str, metric: str, label: str,
                  question: str, groups: list[str], *, percent: bool = False) -> tuple[list[dict[str, Any]], str]:
        if groups:
            rows = [row for row in rows if row[dimension] in groups]
        text = question.casefold()
        direction = "min" if re.search(r"thấp nhất|ít nhất|nhỏ nhất|lowest|minimum", text) else (
            "max" if re.search(r"cao nhất|nhiều nhất|lớn nhất|highest|maximum", text) else None)
        if direction:
            winner = (min if direction == "min" else max)(rows, key=lambda row: row[metric])
            rank = "thấp nhất" if direction == "min" else "cao nhất"
            return rows, f"{winner[dimension]} có {label.casefold()} {rank}: {_format(winner[metric], percent)}."
        return rows, "; ".join(f"{row[dimension]} — {label}: {_format(row[metric], percent)}" for row in rows) + "."

    @staticmethod
    def _clarify_metric() -> dict[str, Any]:
        return {"ok": False, "answer": "Vui lòng làm rõ chỉ số cần phân tích.",
                "limitations": ["Không xác định chắc chỉ số được hỏi."]}
