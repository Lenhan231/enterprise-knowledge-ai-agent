"""Resolve supported commerce requests and retrieve rows from the repository.

This module deliberately returns a payload that can be passed to the existing
``AgentResult`` model in the project. It does not define another result class.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any

from src.core.database.commerce_repository import CommerceRepository


SUPPORTED_OPERATIONS = {
    "revenue_cogs_by_month",
    "revenue_by_region",
    "inventory_by_category",
}


class SQLAnalyticsAgent:
    def __init__(self, repository: CommerceRepository) -> None:
        self.repository = repository

    async def run(self, request: Any) -> dict[str, Any]:
        query = self._query_text(request)
        operation = self._resolve_operation(query)

        if operation is None:
            return self._unsupported(query)

        if operation == "inventory_by_category":
            snapshot_date = self._snapshot_date(query)
            if snapshot_date is None:
                return self._missing_period(query, "snapshot date, ví dụ 2022-12-31")
            rows = await self.repository.inventory_by_category(snapshot_date)
            return self._success(
                operation,
                rows,
                source=["commerce.inventory"],
                period=str(snapshot_date),
            )

        period = self._month_period(query)
        if period is None:
            return self._missing_period(query, "tháng/năm, ví dụ tháng 12/2022")
        start_date, end_date = period

        if operation == "revenue_by_region":
            rows = await self.repository.revenue_by_region(start_date, end_date)
            source = [
                "commerce.orders",
                "commerce.order_items",
                "commerce.geography",
            ]
        else:
            rows = await self.repository.revenue_cogs_by_month(start_date, end_date)
            source = ["commerce.sales"]

        return self._success(
            operation,
            rows,
            source=source,
            period=f"{start_date.isoformat()}:{end_date.isoformat()}",
        )

    @staticmethod
    def _query_text(request: Any) -> str:
        if isinstance(request, str):
            return request.strip()
        for field in ("query", "message", "prompt", "text"):
            value = request.get(field) if isinstance(request, dict) else getattr(request, field, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise ValueError("AgentRequest must contain query text")

    @staticmethod
    def _resolve_operation(query: str) -> str | None:
        text = query.casefold()
        inventory_terms = ("inventory", "tồn kho", "stockout", "hết hàng", "reorder", "fill rate")
        if any(term in text for term in inventory_terms):
            if any(term in text for term in ("category", "danh mục", "loại sản phẩm", "segment")):
                return "inventory_by_category"
            return None
        if any(term in text for term in ("region", "regional", "khu vực", "vùng")):
            if any(term in text for term in ("revenue", "sales", "doanh thu")):
                return "revenue_by_region"
        if any(term in text for term in ("revenue", "sales", "doanh thu", "cogs", "giá vốn")):
            return "revenue_cogs_by_month"
        return None

    @staticmethod
    def _month_period(query: str) -> tuple[date, date] | None:
        match = re.search(r"(?<!\d)(20\d{2})[-/](0?[1-9]|1[0-2])(?!\d)", query)
        if not match:
            match = re.search(r"(?:tháng|month)\s+(0?[1-9]|1[0-2])\s*(?:/|năm|year)\s*(20\d{2})", query, re.I)
            if match:
                year, month = int(match.group(2)), int(match.group(1))
            else:
                return None
        else:
            year, month = int(match.group(1)), int(match.group(2))
        start = date(year, month, 1)
        end_month = calendar.monthrange(year, month)[1]
        return start, date(year, month, end_month) + timedelta(days=1)

    @staticmethod
    def _snapshot_date(query: str) -> date | None:
        match = re.search(r"(?<!\d)(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])(?!\d)", query)
        if match:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        period = SQLAnalyticsAgent._month_period(query)
        return period[1].fromordinal(period[1].toordinal() - 1) if period else None

    @staticmethod
    def _success(operation: str, rows: list[dict[str, Any]], *, source: list[str], period: str) -> dict[str, Any]:
        return {
            "ok": True,
            "operation": operation,
            "rows": rows,
            "evidence": [{"source": table, "period": period} for table in source],
            "metadata": {"source": source, "period": period, "currency": "dataset_currency_unknown"},
        }

    @staticmethod
    def _unsupported(query: str) -> dict[str, Any]:
        return {
            "ok": False,
            "operation": None,
            "rows": [],
            "answer": (
                "Truy vấn chưa được hỗ trợ. Hiện hệ thống hỗ trợ doanh thu/giá vốn theo tháng, "
                "doanh thu theo khu vực và tồn kho theo danh mục tại một snapshot."
            ),
            "limitations": [f"Unsupported commerce request: {query}"],
        }

    @staticmethod
    def _missing_period(query: str, expected: str) -> dict[str, Any]:
        return {
            "ok": False,
            "operation": None,
            "rows": [],
            "answer": f"Vui lòng cung cấp {expected}.",
            "limitations": [f"Missing required period in request: {query}"],
        }
