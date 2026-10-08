#!/usr/bin/env python3
"""Kiểm tra trực tiếp luồng analytics trên Supabase bằng các truy vấn chỉ đọc."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.agents.analytics_agent import AnalyticsAgent  # noqa: E402
from core.agents.sql_analytics_agent import SQLAnalyticsAgent  # noqa: E402
from core.database.commerce_repository import (  # noqa: E402
    CommerceRepository,
    create_repository_from_env,
)
from core.models.agents import AgentRequest, AgentResult, Evidence  # noqa: E402


CASES = (
    {
        "id": "revenue_cogs_2022_12",
        "question": "Doanh thu và giá vốn tháng 12/2022",
        "operation": "revenue_cogs_by_month",
        "sources": {"commerce.sales"},
        "expected_row": {
            "match": {"month": "2022-12-01"},
            "values": {"revenue": "52454936.20", "cogs": "53489673.44"},
        },
    },
    {
        "id": "revenue_by_region_2022_12",
        "question": "Doanh thu theo khu vực tháng 12/2022",
        "operation": "revenue_by_region",
        "sources": {"commerce.orders", "commerce.order_items", "commerce.geography"},
        "expected_row": {
            "match": {"region": "East"},
            "values": {"revenue": "14079268.92"},
        },
    },
    {
        "id": "inventory_2022_12_31",
        "question": "Tồn kho theo danh mục tại ngày 2022-12-31",
        "operation": "inventory_by_category",
        "sources": {"commerce.inventory"},
        "expected_row": {
            "match": {"category": "Casual"},
            "values": {"products_observed": "40", "stockout_products": "31"},
        },
    },
)


async def verify_read_only(repository: CommerceRepository) -> dict[str, Any]:
    """Chứng minh transaction ở chế độ read-only mà không thay đổi dữ liệu."""
    transaction_read_only = None
    write_probe_blocked = False
    write_probe_sqlstate = None

    async with repository.pool.acquire() as connection:
        try:
            async with connection.transaction(readonly=True):
                transaction_read_only = await connection.fetchval(
                    "SHOW transaction_read_only"
                )
                # WHERE FALSE bảo đảm không sửa hàng nào ngay cả khi cấu hình
                # read-only bị sai; transaction đúng phải chặn statement này.
                await connection.execute(
                    "UPDATE commerce.sales SET revenue = revenue WHERE FALSE"
                )
        except Exception as error:
            write_probe_sqlstate = getattr(error, "sqlstate", None)
            write_probe_blocked = write_probe_sqlstate == "25006"

    if str(transaction_read_only).casefold() != "on" or not write_probe_blocked:
        raise RuntimeError("Không xác minh được transaction chỉ đọc trên Supabase")

    return {
        "transaction_read_only": transaction_read_only,
        "write_probe_blocked": write_probe_blocked,
        "write_probe_sqlstate": write_probe_sqlstate,
    }


def _case_result(case: dict[str, Any], result: AgentResult) -> dict[str, Any]:
    serialized_data = result.model_dump(mode="json")["data"]
    serialized_rows = serialized_data.get("rows") or []
    sources = {item.source for item in result.evidence}
    evidence_valid = bool(result.evidence) and all(
        isinstance(item, Evidence)
        and item.source_type == "database"
        and bool(item.citation_id)
        for item in result.evidence
    )
    row_count = len(serialized_rows)
    expected = case["expected_row"]
    expected_values_valid = any(
        all(str(row.get(key)) == str(value) for key, value in expected["match"].items())
        and all(str(row.get(key)) == str(value) for key, value in expected["values"].items())
        for row in serialized_rows
    )
    passed = all((
        isinstance(result, AgentResult),
        result.metadata.get("ok") is True,
        result.data.get("operation") == case["operation"],
        row_count > 0,
        evidence_valid,
        expected_values_valid,
        case["sources"].issubset(sources),
    ))
    return {
        "id": case["id"],
        "passed": passed,
        "agent_result": isinstance(result, AgentResult),
        "agent": result.agent,
        "operation": result.data.get("operation"),
        "row_count": row_count,
        "evidence_valid": evidence_valid,
        "expected_values_valid": expected_values_valid,
        "expected_row": expected,
        "evidence_sources": sorted(sources),
        "answer": result.answer,
        "data": serialized_data,
    }


async def run_smoke(
    *,
    repository: CommerceRepository | None = None,
) -> dict[str, Any]:
    """Chạy ba trường hợp thực tế và luôn đóng pool sau khi hoàn tất."""
    if repository is None:
        load_dotenv(REPO_ROOT / ".env", override=False)
        repository = await create_repository_from_env()

    agent = AnalyticsAgent(SQLAnalyticsAgent(repository))
    try:
        rows = []
        for case in CASES:
            result = await agent.run(AgentRequest(question=case["question"]))
            rows.append(_case_result(case, result))
        read_only = await verify_read_only(repository)
    finally:
        await agent.close()

    passed_cases = sum(row["passed"] for row in rows)
    return {
        "passed": passed_cases == len(CASES) and read_only["write_probe_blocked"],
        "summary": {
            "case_count": len(CASES),
            "passed_cases": passed_cases,
        },
        "read_only": read_only,
        "cases": rows,
    }


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Ghi báo cáo JSON vào đường dẫn này")
    args = parser.parse_args()

    report = await run_smoke()
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
