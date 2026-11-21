"""Regenerate frozen SQL reference rows against the approved non-production DB."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from preflight import ROOT, benchmark_repository, collect_preflight


DEFAULT_CASES = ROOT / "artifacts/sql-agent-bussiness/cases.json"


def _load_scorer():
    path = ROOT / "artifacts/sql-agent-bussiness/scorer.py"
    spec = importlib.util.spec_from_file_location("sql_agent_business_scorer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _bind_parameters(case, parameters):
    date_values = set()
    filters = case.get("semantic", {}).get("filters", {})
    for name, value in filters.items():
        if name == "date_range" and isinstance(value, dict):
            date_values.update(value.get(bound) for bound in ("start", "end_exclusive", "end_inclusive"))
        elif "date" in name and isinstance(value, str):
            date_values.add(value)
    date_values.discard(None)
    return tuple(date.fromisoformat(value) if isinstance(value, str) and value in date_values else value
                 for value in parameters)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=_json_value, separators=(",", ":")).encode()).hexdigest()


async def generate_reference(case_set, repository):
    scorer = _load_scorer()
    environment = await collect_preflight(repository)
    results = []
    for case in case_set["cases"]:
        if not case["supported"]:
            results.append({"id": case["id"], "status": "unsupported_no_query", "sql": None,
                            "parameters": [], "rows": [], "matches_frozen_gold": None})
            continue
        sql = case["gold"]["sql"]
        parameters = case["gold"].get("parameters", [])
        rows = await repository.execute_approved_query(sql, *_bind_parameters(case, parameters))
        rows = [{key: _json_value(value) for key, value in row.items()} for row in rows]
        columns = list(rows[0]) if rows else [column for column in case["requested_columns"]]
        observation = {"sql": sql, "parameters": parameters, "columns": columns, "rows": rows}
        comparison = scorer._result_comparison(
            case, observation
        )
        semantic = scorer._sql_semantics(case, observation)
        results.append({
            "id": case["id"], "status": "reference_generated", "sql": sql,
            "parameters": parameters, "rows": rows, "columns": columns,
            "matches_frozen_gold": comparison["business_rows_match"] and semantic["passed"],
            "comparison": comparison,
            "semantic": semantic,
            "result_sha256": _digest({"columns": columns, "rows": rows}),
        })
    return {
        "format_version": "sql-business-reference.v1",
        "case_set_sha256": hashlib.sha256(
            json.dumps(case_set, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest(),
        "environment": environment,
        "all_supported_references_match_frozen_gold": all(
            item["matches_frozen_gold"] for item in results if item["matches_frozen_gold"] is not None
        ),
        "cases": results,
    }


async def _main(case_path, output_path):
    output = Path(output_path)
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing reference artifact: {output}")
    case_set = json.loads(Path(case_path).read_text(encoding="utf-8"))
    ids = [case["id"] for case in case_set["cases"]]
    if len(ids) != len(set(ids)):
        raise SystemExit("Case IDs must be unique.")
    async with benchmark_repository() as repository:
        result = await generate_reference(case_set, repository)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_value) + "\n",
                      encoding="utf-8")
    if not result["all_supported_references_match_frozen_gold"]:
        raise SystemExit("New database results differ from frozen gold; do not run the model until reviewed.")


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    asyncio.run(_main(arguments.cases, arguments.output))
