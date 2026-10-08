"""Phân giải yêu cầu thương mại và truy xuất dữ liệu qua repository chỉ đọc.

Các bước nội bộ dùng payload ``dict`` để ghép kết quả. Biên public ``run()``
chuyển payload sang ``AgentResult``/``Evidence`` dùng chung của dự án.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

try:
    from core.agents.base import BaseAgent
    from core.analytics.metric_ontology import resolve_metric_names
    from core.database.commerce_repository import CommerceRepository
    from core.models.agents import AgentResult, Evidence
except ModuleNotFoundError:  # Support importing the package as ``src.core``.
    from src.core.agents.base import BaseAgent
    from src.core.analytics.metric_ontology import resolve_metric_names
    from src.core.database.commerce_repository import CommerceRepository
    from src.core.models.agents import AgentResult, Evidence


SUPPORTED_OPERATIONS = {
    "revenue_cogs_by_month",
    "revenue_by_region",
    "inventory_by_category",
}


def payload_to_agent_result(
    payload: Mapping[str, Any],
    *,
    agent: str = "analytics",
) -> AgentResult:
    """Map an analytics payload to the repository's shared agent contract.

    Analytics payloads deliberately remain plain dictionaries while the SQL and
    interpretation steps compose. This is the single boundary where those
    dictionaries become the canonical ``AgentResult``/``Evidence`` models.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("analytics payload must be a mapping")

    evidence: list[Evidence] = []
    for index, item in enumerate(payload.get("evidence") or [], start=1):
        if not isinstance(item, Mapping):
            raise TypeError("analytics evidence items must be mappings")
        source = item.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("analytics evidence requires a non-empty source")
        item_metadata = item.get("metadata") or {}
        if not isinstance(item_metadata, Mapping):
            raise TypeError("analytics evidence metadata must be a mapping")
        metadata = dict(item_metadata)
        if item.get("period") is not None:
            metadata.setdefault("period", item["period"])
        evidence.append(
            Evidence(
                citation_id=str(item.get("citation_id") or f"S{index}"),
                source_type=str(item.get("source_type") or "database"),
                source=source,
                content=item.get("content"),
                metadata=metadata,
            )
        )

    raw_metadata = payload.get("metadata") or {}
    if not isinstance(raw_metadata, Mapping):
        raise TypeError("analytics payload metadata must be a mapping")
    metadata = dict(raw_metadata)
    metadata.setdefault("ok", bool(payload.get("ok", False)))
    if payload.get("limitations"):
        metadata["limitations"] = list(payload["limitations"])

    # Preserve every payload field in data except the two model-level fields.
    # This avoids silently discarding rows, metrics, findings, or limitations.
    data = {
        key: value
        for key, value in payload.items()
        if key not in {"answer", "evidence", "metadata"}
    }
    answer = payload.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        findings = payload.get("findings") or []
        answer = "\n".join(str(finding) for finding in findings if finding)
        if not answer:
            answer = (
                "Đã hoàn tất phân tích dữ liệu thương mại."
                if payload.get("ok")
                else "Không thể hoàn tất phân tích dữ liệu thương mại."
            )

    return AgentResult(
        answer=answer,
        agent=agent,
        evidence=evidence,
        data=data,
        metadata=metadata,
    )


class SQLAnalyticsAgent(BaseAgent):
    def __init__(self, repository: CommerceRepository) -> None:
        self.repository = repository

    async def run(self, request: Any) -> AgentResult:
        return payload_to_agent_result(
            await self.run_payload(request),
            agent="sql_analytics",
        )

    async def run_payload(self, request: Any) -> dict[str, Any]:
        query = self._query_text(request)
        operation = self._resolve_operation(query)

        if operation is None:
            return self._unsupported(query)

        try:
            if operation == "inventory_by_category":
                snapshot_date = self._snapshot_date(query)
                if snapshot_date is None:
                    return self._missing_period(query, "ngày snapshot, ví dụ 2022-12-31")
                rows = await self.repository.inventory_by_category(snapshot_date)
                if not rows:
                    return self._success(operation, rows, source=["commerce.inventory"], period=str(snapshot_date))
                selected = self._mentioned_groups(query, rows, "category")
                if self._unknown_group(query, rows, "category"):
                    return self._unclear_group("danh mục")
                return self._success(
                    operation,
                    rows,
                    source=["commerce.inventory"],
                    period=str(snapshot_date),
                    filters={"category": selected} if selected else {},
                )

            period = self._date_period(query)
            if period is None:
                return self._missing_period(query, "tháng/năm, ví dụ tháng 12/2022")
            start_date, end_date = period

            regional_rows = None
            if operation == "revenue_cogs_by_month" and resolve_metric_names(query) == {"revenue"}:
                regional_rows = await self.repository.revenue_by_region(start_date, end_date)
                if self._mentioned_groups(query, regional_rows, "region"):
                    operation = "revenue_by_region"

            if operation == "revenue_by_region":
                rows = regional_rows if regional_rows is not None else await self.repository.revenue_by_region(start_date, end_date)
                source = [
                    "commerce.orders",
                    "commerce.order_items",
                    "commerce.geography",
                ]
            else:
                rows = await self.repository.revenue_cogs_by_month(start_date, end_date)
                source = ["commerce.sales"]

            if not rows:
                return self._success(operation, rows, source=source,
                                     period=f"{start_date.isoformat()}:{end_date.isoformat()}")

            dimension = "region" if operation == "revenue_by_region" else None
            selected = self._mentioned_groups(query, rows, dimension) if dimension else []
            if dimension and self._unknown_group(query, rows, dimension):
                return self._unclear_group("khu vực")
            total_revenue = sum((Decimal(str(row["revenue"])) for row in rows), Decimal(0)) if dimension else None
            return self._success(
                operation,
                rows,
                source=source,
                period=f"{start_date.isoformat()}:{end_date.isoformat()}",
                filters={dimension: selected} if selected else {},
                total_revenue=total_revenue,
            )
        except Exception as error:
            return self._database_error(operation, error)

    async def close(self) -> None:
        await self.repository.close()

    @staticmethod
    def _query_text(request: Any) -> str:
        if isinstance(request, str):
            return request.strip()
        for field in ("question", "query", "message", "prompt", "text"):
            value = request.get(field) if isinstance(request, dict) else getattr(request, field, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise ValueError("AgentRequest must contain query text")

    @staticmethod
    def _resolve_operation(query: str) -> str | None:
        text = query.casefold()
        metrics = resolve_metric_names(query)
        inventory_metrics = {
            "stock_on_hand",
            "stockout_rate",
            "days_of_supply",
            "fill_rate",
            "sell_through_rate",
        }
        if metrics & inventory_metrics:
            return "inventory_by_category"
        if "regional_revenue" in metrics or (
            "revenue" in metrics
            and any(term in text for term in ("region", "regional", "khu vực", "vùng"))
        ):
            return "revenue_by_region"
        if metrics & {"revenue", "cogs", "gross_profit"}:
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
    def _date_period(query: str) -> tuple[date, date] | None:
        month = SQLAnalyticsAgent._month_period(query)
        if month:
            return month
        match = re.search(r"(?:năm|year)\s+(20\d{2})(?!\d)", query, re.I)
        if match:
            year = int(match.group(1))
            return date(year, 1, 1), date(year + 1, 1, 1)
        return None

    @staticmethod
    def _snapshot_date(query: str) -> date | None:
        match = re.search(r"(?<!\d)(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])(?!\d)", query)
        if match:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        period = SQLAnalyticsAgent._month_period(query)
        return period[1].fromordinal(period[1].toordinal() - 1) if period else None

    @staticmethod
    def _mentioned_groups(query: str, rows: list[dict[str, Any]], dimension: str | None) -> list[str]:
        if not dimension:
            return []
        return [str(row[dimension]) for row in rows if row.get(dimension) and
                re.search(rf"(?<!\w){re.escape(str(row[dimension]))}(?!\w)", query, re.I)]

    @staticmethod
    def _unknown_group(query: str, rows: list[dict[str, Any]], dimension: str) -> bool:
        marker = "khu vực" if dimension == "region" else "danh mục"
        match = re.search(rf"(?i:{marker})\s+([\w-]+)", query)
        return bool(match and match.group(1)[0].isupper() and match.group(1).casefold() not in {
            str(row[dimension]).casefold() for row in rows
        })

    @staticmethod
    def _unclear_group(dimension: str) -> dict[str, Any]:
        return {"ok": False, "operation": None, "rows": [],
                "answer": f"Không xác định được {dimension} được hỏi. Vui lòng nêu tên có trong dữ liệu.",
                "limitations": [f"{dimension} không khớp với các hàng tổng hợp hiện có."]}

    @staticmethod
    def _success(operation: str, rows: list[dict[str, Any]], *, source: list[str], period: str,
                 filters: dict[str, list[str]] | None = None,
                 total_revenue: Any | None = None) -> dict[str, Any]:
        if not rows:
            return {
                "ok": False, "operation": operation, "rows": [], "evidence": [],
                "answer": f"Không có dữ liệu cho kỳ {period}.",
                "limitations": [f"Không có hàng tổng hợp trong nguồn dữ liệu cho kỳ {period}."],
                "metadata": {"period": period},
            }
        return {
            "ok": True,
            "operation": operation,
            "rows": rows,
            "evidence": [{"source": table, "period": period} for table in source],
            "metadata": {"source": source, "period": period, "currency": "dataset_currency_unknown",
                         "filters": filters or {}, "total_revenue": total_revenue},
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
            "limitations": [f"Yêu cầu phân tích thương mại chưa được hỗ trợ: {query}"],
        }

    @staticmethod
    def _missing_period(query: str, expected: str) -> dict[str, Any]:
        return {
            "ok": False,
            "operation": None,
            "rows": [],
            "answer": f"Vui lòng cung cấp {expected}.",
            "limitations": [f"Yêu cầu còn thiếu thời gian phân tích bắt buộc: {query}"],
        }

    @staticmethod
    def _database_error(operation: str, error: Exception) -> dict[str, Any]:
        return {
            "ok": False,
            "operation": operation,
            "rows": [],
            "answer": "Không thể truy xuất dữ liệu thương mại vào lúc này. Vui lòng thử lại sau.",
            "limitations": ["Truy vấn cơ sở dữ liệu không hoàn tất."],
            "metadata": {"error_type": type(error).__name__},
        }
