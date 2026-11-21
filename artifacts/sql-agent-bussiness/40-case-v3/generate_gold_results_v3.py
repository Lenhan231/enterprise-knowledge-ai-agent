"""Generate provisional Gold rows through the approved read-only repository."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ARTIFACTS = ROOT / "artifacts/sql-agent-bussiness"
PREPARATION = ARTIFACTS / "40-case-preparation"
sys.path[:0] = [str(ROOT / "src"), str(ARTIFACTS), str(PREPARATION)]

from dataset_validator import validate_dataset, validate_gold_sql_drafts  # noqa: E402
from preflight import benchmark_repository, collect_preflight, validate_database_environment  # noqa: E402


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _canonical_sha256(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_state():
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    return revision, bool(status.strip())


async def generate(case_doc: dict, gold_doc: dict, preflight_doc: dict, preflight_path: Path) -> dict:
    structural = validate_dataset(case_doc, preflight_doc)
    gold_validation = validate_gold_sql_drafts(case_doc, gold_doc, preflight_doc)
    errors = structural["errors"] + gold_validation["errors"]
    if errors:
        raise ValueError("Draft validation failed before DB access: " + "; ".join(errors))
    if preflight_doc.get("status") != "VERIFIED_READ_ONLY_PREFLIGHT":
        raise ValueError("v3 reference generation requires a verified preflight")
    if preflight_doc.get("database_role_read_only") is not True:
        raise ValueError("v3 reference generation requires the verified read-only role")
    validate_database_environment()

    cases = {case["id"]: case for case in case_doc["cases"]}
    results = []
    async with benchmark_repository() as repository:
        fresh = await collect_preflight(repository)
        expected_fingerprint = preflight_doc.get("fingerprint_sha256")
        if fresh.get("fingerprint_sha256") != expected_fingerprint:
            raise ValueError("Current database fingerprint differs from v3 preflight; no Gold SQL executed.")
        schema = await repository.get_schema()
        schema_manifest = {
            "tables": {name: sorted(columns) for name, columns in sorted(schema.get("tables", {}).items())},
            "column_types": schema.get("column_types", {}),
            "primary_keys": {
                name: sorted(keys) for name, keys in sorted(schema.get("primary_keys", {}).items())
            },
            "foreign_keys": list(schema.get("foreign_keys", ())),
            "joins": sorted(
                " = ".join(sorted(f"{table}.{column}" for table, column in edge))
                for edge in schema.get("joins", ())
            ),
            "date_columns": sorted(f"{table}.{column}" for table, column in schema.get("date_columns", ())),
        }
        for item in gold_doc["cases"]:
            case = cases[item["id"]]
            parameters = item["parameters"]
            bound = tuple(
                date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 and value[4] == "-"
                else value
                for value in parameters
            )
            started = asyncio.get_running_loop().time()
            try:
                rows = await repository.execute_approved_query(item["sql"], *bound)
                serialized = [
                    {key: _json_value(value) for key, value in row.items()}
                    for row in rows
                ]
                columns = list(serialized[0]) if serialized else list(case["output_contract"]["columns"])
                results.append({
                    "id": item["id"],
                    "status": "PROVISIONAL_NOT_APPROVED" if serialized else "PROVISIONAL_EMPTY_NOT_APPROVED",
                    "sql": item["sql"],
                    "parameters": parameters,
                    "columns": columns,
                    "rows": serialized,
                    "row_count": len(serialized),
                    "elapsed_ms": round((asyncio.get_running_loop().time() - started) * 1000, 3),
                    "result_sha256": _canonical_sha256({"columns": columns, "rows": serialized}),
                    "human_review": {
                        "reviewer_1": "PENDING",
                        "reviewer_2": "PENDING",
                        "adjudication": "PENDING",
                    },
                })
            except Exception as error:
                results.append({
                    "id": item["id"],
                    "status": "EXECUTION_FAILED",
                    "sql": item["sql"],
                    "parameters": parameters,
                    "columns": list(case["output_contract"]["columns"]),
                    "rows": [],
                    "row_count": 0,
                    "elapsed_ms": round((asyncio.get_running_loop().time() - started) * 1000, 3),
                    "result_sha256": None,
                    "error_type": type(error).__name__,
                    "error_detail": str(error),
                    "human_review": {
                        "reviewer_1": "PENDING",
                        "reviewer_2": "PENDING",
                        "adjudication": "PENDING",
                    },
                })

    failures = [item["id"] for item in results if item["status"] == "EXECUTION_FAILED"]
    revision, dirty = _source_state()
    source_paths = [
        HERE / "cases_v3_draft.json",
        HERE / "gold_sql_v3_draft.json",
        HERE / "build_v3_draft.py",
        HERE / "followup_adapter.py",
        HERE / "generate_gold_results_v3.py",
        PREPARATION / "dataset_validator.py",
        PREPARATION / "preflight_40.py",
        ARTIFACTS / "preflight.py",
        ARTIFACTS / "scorer.py",
        ARTIFACTS / "PROTOCOL.md",
        ROOT / "src/core/agents/sql/agent.py",
        ROOT / "src/core/agents/sql/sql_validation.py",
        ROOT / "src/core/agents/sql/join_validation.py",
        ROOT / "data/semantic/commerce_schema_metric_contract_v1.md",
    ]
    return {
        "format_version": "sql-40-case-gold-results.v3-provisional",
        "status": "PROVISIONAL_COMPLETE_NOT_APPROVED" if not failures else "PROVISIONAL_PARTIAL_NOT_APPROVED",
        "case_set_sha256": _canonical_sha256(case_doc),
        "gold_sql_definition_sha256": _canonical_sha256([
            {"id": item["id"], "sql": item["sql"], "parameters": item["parameters"]}
            for item in gold_doc["cases"]
        ]),
        "gold_sql_draft_file_sha256": _file_sha256(HERE / "gold_sql_v3_draft.json"),
        "preflight_file_sha256": _file_sha256(preflight_path),
        "source_revision": revision,
        "source_worktree_dirty": dirty,
        "python_version": platform.python_version(),
        "source_hashes": {
            str(path.relative_to(ROOT)): _file_sha256(path)
            for path in source_paths
        },
        "database_classification": fresh["database_classification"],
        "database_role_read_only": True,
        "database_fingerprint_sha256": fresh["fingerprint_sha256"],
        "schema_sha256": _canonical_sha256(schema_manifest),
        "schema": schema_manifest,
        "sql_agent_generation_calls": 0,
        "heldout_agent_executed": False,
        "oracle_status": "PROVISIONAL_NOT_APPROVED",
        "independent_review_approvals": 0,
        "structural_validation": structural,
        "gold_sql_validation": gold_validation,
        "execution_count": len(results),
        "execution_failures": failures,
        "cases": results,
    }


async def _main(preflight_path: Path, output_path: Path):
    if output_path.exists():
        raise SystemExit(f"Refusing to overwrite existing reference artifact: {output_path}")
    case_doc = json.loads((HERE / "cases_v3_draft.json").read_text(encoding="utf-8"))
    gold_doc = json.loads((HERE / "gold_sql_v3_draft.json").read_text(encoding="utf-8"))
    preflight_doc = json.loads(preflight_path.read_text(encoding="utf-8"))
    result = await generate(case_doc, gold_doc, preflight_doc, preflight_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, default=_json_value) + "\n")
    print(json.dumps({
        "status": result["status"],
        "gold_cases": len(result["cases"]),
        "execution_failures": result["execution_failures"],
        "heldout_agent_executed": result["heldout_agent_executed"],
        "fingerprint": result["database_fingerprint_sha256"],
        "output": str(output_path),
    }, ensure_ascii=False, indent=2))
    if result["execution_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", default=str(HERE / "database_preflight_v3.json"))
    parser.add_argument("--output", default=str(HERE / "gold_results_v3_provisional.json"))
    args = parser.parse_args()
    asyncio.run(_main(Path(args.preflight), Path(args.output)))
