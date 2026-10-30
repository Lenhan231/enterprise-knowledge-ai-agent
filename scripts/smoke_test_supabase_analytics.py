#!/usr/bin/env python3
"""Run generated read-only commerce queries against the configured Supabase database."""

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
from core.database.commerce_repository import CommerceRepository, create_repository_from_env  # noqa: E402
from core.models.agents import AgentRequest, AgentResult, VerifiedIdentity  # noqa: E402


ANALYST = VerifiedIdentity(subject="supabase-smoke", permissions={"analytics:read"})
CASES = (
    {"id": "monthly_sales", "question": "Show monthly revenue and COGS for 2022.",
     "sources": {"commerce.sales"}},
    {"id": "orders_by_status", "question": "Count orders by status.",
     "sources": {"commerce.orders"}},
    {"id": "products_by_category", "question": "Count products by category.",
     "sources": {"commerce.products"}},
)


async def verify_read_only(repository: CommerceRepository) -> dict[str, Any]:
    transaction_read_only = None
    write_probe_sqlstate = None
    async with repository.pool.acquire() as connection:
        try:
            async with connection.transaction(readonly=True):
                transaction_read_only = await connection.fetchval("SHOW transaction_read_only")
                await connection.execute("UPDATE commerce.sales SET revenue = revenue WHERE FALSE")
        except Exception as error:
            write_probe_sqlstate = getattr(error, "sqlstate", None)
    blocked = write_probe_sqlstate == "25006"
    if str(transaction_read_only).casefold() != "on" or not blocked:
        raise RuntimeError("The database did not confirm read-only transaction behavior.")
    return {"transaction_read_only": transaction_read_only,
            "write_probe_blocked": blocked, "write_probe_sqlstate": write_probe_sqlstate}


def _case_result(case: dict[str, Any], result: AgentResult) -> dict[str, Any]:
    sources = {item.source for item in result.evidence}
    rows = result.data.get("rows") or []
    passed = (result.metadata.get("ok") is True and bool(rows)
              and case["sources"].issubset(sources))
    return {"id": case["id"], "passed": passed, "agent": result.agent,
            "row_count": len(rows), "sources": sorted(sources), "answer": result.answer,
            "data": result.data}


async def run_smoke(*, repository: CommerceRepository | None = None,
                    llm: Any | None = None) -> dict[str, Any]:
    if repository is None:
        load_dotenv(REPO_ROOT / ".env", override=False)
        repository = await create_repository_from_env()
    agent = AnalyticsAgent(SQLAnalyticsAgent(repository, llm=llm))
    try:
        results = []
        for case in CASES:
            result = await agent.run(AgentRequest(question=case["question"], identity=ANALYST))
            results.append(_case_result(case, result))
        read_only = await verify_read_only(repository)
    finally:
        await agent.close()
    passed_cases = sum(item["passed"] for item in results)
    return {"passed": passed_cases == len(CASES) and read_only["write_probe_blocked"],
            "summary": {"case_count": len(CASES), "passed_cases": passed_cases},
            "read_only": read_only, "cases": results}


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path")
    args = parser.parse_args()
    report = await run_smoke()
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
