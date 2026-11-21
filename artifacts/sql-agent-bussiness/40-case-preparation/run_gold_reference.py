"""Execute only independently authored gold SQL on the approved read-only DB."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import re
import subprocess
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from preflight import benchmark_repository, collect_preflight, validate_database_environment
from dataset_validator import validate_dataset, validate_gold_sql_drafts


HERE = Path(__file__).resolve().parent
CASES_PATH = HERE / "cases_v2_draft.json"
GOLD_PATH = HERE / "gold_sql_draft.json"
PREFLIGHT_PATH = HERE / "database_preflight_fresh_621d9984.json"
RESULT_PATH = HERE / "gold_results_provisional.json"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _canonical_hash(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_value,
    ).encode("utf-8")).hexdigest()


def bind_parameters(parameters):
    """Bind ISO calendar-date values as date objects; leave other values intact."""
    return tuple(date.fromisoformat(value) if isinstance(value, str) and ISO_DATE.fullmatch(value) else value
                 for value in parameters)


def _sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_revision():
    revision = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--short"], check=True, capture_output=True, text=True).stdout
    return revision, bool(status.strip())


def _schema_contract(schema):
    return {
        "tables": {name: sorted(columns) for name, columns in sorted(schema.get("tables", {}).items())},
        "column_types": schema.get("column_types", {}),
        "primary_keys": {name: sorted(keys) for name, keys in sorted(schema.get("primary_keys", {}).items())},
        "date_columns": sorted(f"{table}.{column}" for table, column in schema.get("date_columns", ())),
        "joins": sorted(
            " = ".join(sorted(f"{table}.{column}" for table, column in edge))
            for edge in schema.get("joins", ())
        ),
    }


async def generate_gold_results(cases, gold, preflight, preflight_path, repository):
    structural = validate_dataset(cases, preflight)
    gold_validation = validate_gold_sql_drafts(cases, gold, preflight)
    if structural["errors"] or gold_validation["errors"]:
        raise ValueError("Pre-execution validation failed: " + "; ".join(
            structural["errors"] + gold_validation["errors"]
        ))
    current = await collect_preflight(repository)
    expected_fingerprint = preflight.get("fingerprint_sha256")
    if current.get("fingerprint_sha256") != expected_fingerprint:
        raise ValueError("Current database fingerprint differs from verified preflight; no gold SQL executed.")
    live_schema = await repository.get_schema()  # includes a fresh read-only role verification
    schema_manifest = _schema_contract(live_schema)
    revision, dirty = _source_revision()
    root = HERE.parent.parent.parent
    source_paths = [
        CASES_PATH, GOLD_PATH, HERE / "build_draft.py", HERE / "dataset_validator.py", HERE / "preflight_40.py",
        HERE / "run_gold_reference.py", HERE.parent / "preflight.py", HERE.parent / "scorer.py",
        HERE.parent / "PROTOCOL.md", HERE.parent / "benchmark_40_plan.json",
        root / "src/core/agents/sql/sql_validation.py", root / "src/core/agents/sql/join_validation.py",
        root / "data/semantic/commerce_schema_metric_contract_v1.md",
    ]
    source_hashes = {str(path.relative_to(root)): _sha256_file(path) for path in source_paths}
    case_by_id = {case["id"]: case for case in cases["cases"]}
    results = []
    for draft in gold["cases"]:
        case = case_by_id[draft["id"]]
        parameters = list(draft["parameters"])
        started = time.perf_counter()
        try:
            rows = await repository.execute_approved_query(draft["sql"], *bind_parameters(parameters))
            serialized_rows = [
                {key: _json_value(value) if isinstance(value, (date, datetime, Decimal)) else value
                 for key, value in row.items()}
                for row in rows
            ]
            columns = list(serialized_rows[0]) if serialized_rows else list(case["output_contract"]["columns"])
            result_hash = _canonical_hash({"columns": columns, "rows": serialized_rows})
            results.append({
                "id": draft["id"],
                "status": "PROVISIONAL_NOT_APPROVED" if serialized_rows else "PROVISIONAL_EMPTY_NOT_APPROVED",
                "sql": draft["sql"],
                "parameters": parameters,
                "columns": columns,
                "rows": serialized_rows,
                "row_count": len(serialized_rows),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "result_sha256": result_hash,
                "human_review": {"reviewer_1": "PENDING", "reviewer_2": "PENDING", "adjudication": "PENDING"},
            })
        except Exception as error:
            results.append({
                "id": draft["id"],
                "status": "EXECUTION_FAILED",
                "sql": draft["sql"],
                "parameters": parameters,
                "columns": list(case["output_contract"]["columns"]),
                "rows": [],
                "row_count": 0,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "result_sha256": None,
                "error_type": type(error).__name__,
                "error_detail": str(error),
                "human_review": {"reviewer_1": "PENDING", "reviewer_2": "PENDING", "adjudication": "PENDING"},
            })
    failures = [item["id"] for item in results if item["status"] == "EXECUTION_FAILED"]
    return {
        "format_version": "sql-40-case-gold-results.v1",
        "status": "PROVISIONAL_COMPLETE_NOT_APPROVED" if not failures else "PROVISIONAL_PARTIAL_NOT_APPROVED",
        "case_set_sha256": structural["case_set_sha256"],
        "gold_sql_definition_sha256": _canonical_hash([
            {"id": item["id"], "sql": item["sql"], "parameters": item["parameters"]}
            for item in gold["cases"]
        ]),
        "gold_sql_draft_file_sha256_at_execution": _sha256_file(GOLD_PATH),
        "preflight_file_sha256": _sha256_file(preflight_path),
        "source_revision": revision,
        "source_worktree_dirty": dirty,
        "python_version": platform.python_version(),
        "source_hashes": source_hashes,
        "database_classification": current["database_classification"],
        "database_role_read_only": True,
        "database_fingerprint_sha256": current["fingerprint_sha256"],
        "schema_sha256": _canonical_hash(schema_manifest),
        "schema": schema_manifest,
        "sql_agent_generation_calls": 0,
        "heldout_agent_executed": False,
        "oracle_status": "PROVISIONAL_NOT_APPROVED",
        "independent_review_approvals": 0,
        "execution_count": len(results),
        "execution_failures": failures,
        "cases": results,
    }


async def _run(output_path: Path, preflight_path: Path):
    if output_path.exists():
        raise SystemExit(f"Refusing to overwrite existing result artifact: {output_path}")
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    validate_database_environment()
    async with benchmark_repository() as repository:
        result = await generate_gold_results(cases, gold, preflight, preflight_path, repository)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_value) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "reference_cases": len(result["cases"]),
        "execution_failures": result["execution_failures"],
        "heldout_agent_executed": result["heldout_agent_executed"],
        "output": str(output_path),
    }, indent=2))
    if result["execution_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(RESULT_PATH))
    parser.add_argument("--preflight", default=str(PREFLIGHT_PATH))
    args = parser.parse_args()
    asyncio.run(_run(Path(args.output), Path(args.preflight)))
