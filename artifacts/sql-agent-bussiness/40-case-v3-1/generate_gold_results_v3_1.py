"""Regenerate the v3.1 provisional Gold rows through the approved read-only runner."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V3 = HERE.parent / "40-case-v3"
ARTIFACTS = HERE.parent
PREPARATION = ARTIFACTS / "40-case-preparation"
sys.path[:0] = [str(ROOT / "src"), str(ARTIFACTS), str(PREPARATION), str(V3)]

_SPEC = importlib.util.spec_from_file_location("sql_gold_generator_v3", V3 / "generate_gold_results_v3.py")
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("Could not load the reviewed read-only v3 Gold SQL executor")
_GENERATOR = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_GENERATOR)


def _canonical_sha256(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), default=_GENERATOR._json_value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_revision() -> tuple[str, bool]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout
    return revision, bool(status.strip())


def _compare_reference(actual: dict, provisional: dict) -> dict:
    expected_by_id = {item["id"]: item for item in provisional.get("cases", [])}
    comparisons = []
    for item in actual.get("cases", []):
        expected = expected_by_id.get(item["id"])
        checks = {
            "case_present": expected is not None,
            "sql_matches": expected is not None and item.get("sql") == expected.get("sql"),
            "parameters_match": expected is not None and item.get("parameters") == expected.get("parameters"),
            "columns_match": expected is not None and item.get("columns") == expected.get("columns"),
            "rows_match": expected is not None and item.get("rows") == expected.get("rows"),
            "row_count_matches": expected is not None and item.get("row_count") == expected.get("row_count"),
        }
        comparisons.append({"id": item["id"], **checks,
                            "matches_provisional": all(checks.values())})
    mismatches = [item["id"] for item in comparisons if not item["matches_provisional"]]
    return {
        "provisional_file_sha256": None,
        "compared_cases": len(comparisons),
        "matching_cases": len(comparisons) - len(mismatches),
        "mismatching_case_ids": mismatches,
        "all_cases_match": not mismatches and len(comparisons) == len(expected_by_id),
        "cases": comparisons,
    }


async def regenerate(case_path: Path, gold_path: Path, preflight_path: Path,
                     provisional_path: Path, output_path: Path) -> dict:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite immutable Gold evidence: {output_path}")
    case_doc = json.loads(case_path.read_text(encoding="utf-8"))
    gold_doc = json.loads(gold_path.read_text(encoding="utf-8"))
    preflight_doc = json.loads(preflight_path.read_text(encoding="utf-8"))
    provisional_doc = json.loads(provisional_path.read_text(encoding="utf-8"))
    result = await _GENERATOR.generate(case_doc, gold_doc, preflight_doc, preflight_path)
    comparison = _compare_reference(result, provisional_doc)
    comparison["provisional_file_sha256"] = _file_sha256(provisional_path)
    result.update({
        "format_version": "sql-40-case-gold-results.v3.1-rerun",
        "protocol_version": "3.1.0",
        "run_id": "gold-v3-1-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_set_sha256": _canonical_sha256(case_doc),
        "gold_sql_definition_sha256": _canonical_sha256([
            {"id": item["id"], "sql": item["sql"], "parameters": item["parameters"]}
            for item in gold_doc["cases"]
        ]),
        "gold_sql_draft_file_sha256": _file_sha256(gold_path),
        "case_file_sha256": _file_sha256(case_path),
        "preflight_file_sha256": _file_sha256(preflight_path),
        "provisional_reference_file_sha256": _file_sha256(provisional_path),
        "source_hashes_v3_1": {
            str(path.relative_to(ROOT)): _file_sha256(path)
            for path in (
                case_path, gold_path, provisional_path, preflight_path,
                HERE / "generate_gold_results_v3_1.py",
                V3 / "generate_gold_results_v3.py",
                V3 / "followup_adapter.py",
                PREPARATION / "dataset_validator.py",
                PREPARATION / "preflight_40.py",
                ARTIFACTS / "preflight.py",
                ROOT / "src/core/agents/sql/agent.py",
                ROOT / "src/core/agents/sql/metric_validation.py",
                ROOT / "src/core/agents/sql/sql_validation.py",
                ROOT / "src/core/database/commerce_repository.py",
            ) if path.is_file()
        },
        "provisional_reference_comparison": comparison,
        "independent_review_approvals": 0,
        "human_approval_claimed": False,
        "database_write_attempts": 0,
        "heldout_agent_executed": False,
    })
    result["status"] = (
        "PROVISIONAL_COMPLETE_NOT_APPROVED"
        if not result["execution_failures"] and comparison["all_cases_match"]
        else "PROVISIONAL_PARTIAL_NOT_APPROVED"
    )
    result["oracle_status"] = "PROVISIONAL_NOT_APPROVED"
    result["independent_review_approvals"] = 0
    result["human_approval_claimed"] = False
    revision, dirty = _source_revision()
    result["source_revision"] = revision
    result["source_worktree_dirty"] = dirty
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2,
                                default=_GENERATOR._json_value) + "\n")
    return result


async def _main(args):
    result = await regenerate(
        Path(args.cases), Path(args.gold_sql), Path(args.preflight),
        Path(args.provisional_results), Path(args.output),
    )
    print(json.dumps({
        "status": result["status"],
        "execution_count": result["execution_count"],
        "execution_failures": result["execution_failures"],
        "reference_matches": result["provisional_reference_comparison"]["matching_cases"],
        "reference_mismatches": result["provisional_reference_comparison"]["mismatching_case_ids"],
        "fingerprint": result["database_fingerprint_sha256"],
        "read_only_role": result["database_role_read_only"],
        "heldout_agent_executed": result["heldout_agent_executed"],
        "output": args.output,
    }, ensure_ascii=False, indent=2))
    if result["status"] != "PROVISIONAL_COMPLETE_NOT_APPROVED":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(HERE / "cases_v3_1_draft.json"))
    parser.add_argument("--gold-sql", default=str(HERE / "gold_sql_v3_1_draft.json"))
    parser.add_argument("--preflight", required=True)
    parser.add_argument("--provisional-results", default=str(HERE / "gold_results_v3_1_provisional.json"))
    parser.add_argument("--output", required=True)
    asyncio.run(_main(parser.parse_args()))
