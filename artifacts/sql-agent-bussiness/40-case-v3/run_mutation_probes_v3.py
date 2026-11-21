"""Execute controlled v3 SQL mutations with the approved read-only executor."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ARTIFACTS = ROOT / "artifacts/sql-agent-bussiness"
PREPARATION = ARTIFACTS / "40-case-preparation"
sys.path[:0] = [str(ROOT / "src"), str(ARTIFACTS), str(PREPARATION), str(HERE)]

from preflight import benchmark_repository, collect_preflight, validate_database_environment  # noqa: E402
from core.agents.sql.metric_validation import validate_population_contract  # noqa: E402
from mutation_probes_v3 import construct_mutation, mutation_catalog  # noqa: E402
from scorer_v3 import compare_business_results  # noqa: E402
from followup_adapter import adapt_followup_case  # noqa: E402


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


def _source_hashes() -> dict[str, str]:
    paths = [
        HERE / "cases_v3_draft.json",
        HERE / "gold_sql_v3_draft.json",
        HERE / "gold_results_v3_provisional.json",
        HERE / "mutation_probes_v3.py",
        HERE / "run_mutation_probes_v3.py",
        HERE / "scorer_v3.py",
        HERE / "followup_adapter.py",
        ARTIFACTS / "preflight.py",
        ROOT / "src/core/agents/sql/metric_validation.py",
        ROOT / "src/core/agents/sql/sql_validation.py",
        ROOT / "src/core/agents/sql/join_validation.py",
        ROOT / "src/core/database/commerce_repository.py",
        ROOT / "data/semantic/commerce_schema_metric_contract_v1.md",
    ]
    return {str(path.relative_to(ROOT)): _file_sha256(path) for path in paths}


def _bind(parameters):
    return tuple(
        date.fromisoformat(value)
        if isinstance(value, str) and len(value) == 10 and value[4] == "-"
        else value
        for value in parameters
    )


async def execute_probes(cases_doc: dict, gold_sql_doc: dict, gold_results_doc: dict, preflight_doc: dict,
                         preflight_path: Path, gold_results_path: Path) -> dict:
    if preflight_doc.get("status") != "VERIFIED_READ_ONLY_PREFLIGHT" or preflight_doc.get("database_role_read_only") is not True:
        raise ValueError("Mutation probes require a verified read-only frozen-snapshot preflight.")
    if gold_results_doc.get("status") != "PROVISIONAL_COMPLETE_NOT_APPROVED":
        raise ValueError("Mutation probes require all 30 provisional Gold results to have executed successfully.")
    if gold_results_doc.get("database_fingerprint_sha256") != preflight_doc.get("fingerprint_sha256"):
        raise ValueError("Gold results and current preflight do not reference the same database fingerprint.")
    validate_database_environment()

    cases = {case["id"]: case for case in cases_doc["cases"]}
    gold = {item["id"]: item for item in gold_sql_doc["cases"]}
    gold_results = {item["id"]: item for item in gold_results_doc["cases"]}
    entries = []
    async with benchmark_repository() as repository:
        fresh = await collect_preflight(repository)
        expected_fingerprint = preflight_doc.get("fingerprint_sha256")
        if fresh.get("fingerprint_sha256") != expected_fingerprint:
            raise ValueError("Current database fingerprint differs from the v3 preflight; no mutation SQL executed.")
        # get_schema refreshes and enforces the least-privilege read-only role.
        await repository.get_schema()
        for spec in mutation_catalog():
            started = asyncio.get_running_loop().time()
            mutation = construct_mutation(gold, spec)
            case = cases[spec["case_id"]]
            gold_case = gold_results[spec["case_id"]]
            if gold_case.get("status") not in {"PROVISIONAL_NOT_APPROVED", "PROVISIONAL_EMPTY_NOT_APPROVED"}:
                raise ValueError(f"Gold result for {spec['case_id']} is not a successful provisional result.")

            row = {
                "id": spec["id"],
                "case_id": spec["case_id"],
                "category": spec["category"],
                "description": spec["description"],
                "valid_semantic_mutation": True,
                "construction_verified": mutation["construction_verified"],
                "validator_oracle": spec["validator_oracle"],
                "semantic_validator_oracle": spec.get("semantic_validator_oracle"),
                "sql": mutation["sql"],
                "parameters": mutation["parameters"],
                "sql_sha256": hashlib.sha256(mutation["sql"].encode("utf-8")).hexdigest(),
            }
            semantic_oracle = spec.get("semantic_validator_oracle")
            if semantic_oracle == "required_order_status_population":
                adapted = adapt_followup_case(case)
                gold_request = gold[spec["case_id"]]
                gold_parameters = _bind(gold_request["parameters"])
                mutation_parameters = _bind(mutation["parameters"])
                # The unchanged Gold must pass the same business population contract.
                validate_population_contract(gold_request["sql"], adapted.question, gold_parameters, ())
                try:
                    validate_population_contract(mutation["sql"], adapted.question, mutation_parameters, ())
                    row["semantic_validator_outcome"] = "NOT_REJECTED"
                    row["semantic_validator_detected"] = False
                except Exception as error:
                    correctly_rejected = type(error).__name__ == "MetricDefinitionError"
                    row["semantic_validator_outcome"] = "CORRECT_REJECTION" if correctly_rejected else "UNEXPECTED_REJECTION"
                    row["semantic_validator_detected"] = correctly_rejected
                    row["semantic_validator_error_type"] = type(error).__name__
                    row["semantic_validator_error_detail"] = str(error)[:500]
            try:
                import sqlglot

                parsed = sqlglot.parse(mutation["sql"], read="postgres")
                row["sql_parse_valid"] = len(parsed) == 1 and parsed[0] is not None
                if not row["sql_parse_valid"]:
                    row.update(status="INVALID_MUTATION", detected=False, reason="SQL parser did not produce one query",
                               elapsed_ms=round((asyncio.get_running_loop().time() - started) * 1000, 3))
                    entries.append(row)
                    continue
            except Exception as error:
                row.update(
                    status="INVALID_MUTATION",
                    detected=False,
                    error_type=type(error).__name__,
                    error_detail=str(error)[:500],
                    elapsed_ms=round((asyncio.get_running_loop().time() - started) * 1000, 3),
                )
                entries.append(row)
                continue

            try:
                rows = await repository.execute_approved_query(mutation["sql"], *_bind(mutation["parameters"]))
                serialized = [{key: _json_value(value) for key, value in item.items()} for item in rows]
                comparison = compare_business_results(
                    case,
                    gold_case.get("rows", []),
                    {"columns": list(serialized[0]) if serialized else list(case["output_contract"]["columns"]),
                     "rows": serialized},
                )
                result_hash = _canonical_sha256({
                    "columns": list(serialized[0]) if serialized else list(case["output_contract"]["columns"]),
                    "rows": serialized,
                })
                row.update(
                    status="EXECUTED",
                    executed_via="execute_approved_query",
                    rows=serialized,
                    row_count=len(serialized),
                    result_sha256=result_hash,
                    comparison=comparison,
                    detected=not comparison["business_rows_match"],
                    detection_channel="result" if not comparison["business_rows_match"] else "observationally_equivalent",
                    elapsed_ms=round((asyncio.get_running_loop().time() - started) * 1000, 3),
                )
                if spec["validator_oracle"]:
                    row["validator_oracle_outcome"] = "NOT_REJECTED"
                    row["unexpected_validator_behavior"] = True
            except Exception as error:
                error_type = type(error).__name__
                expected_validator_types = {
                    "approved_join_relationship": {"SQLJoinValidationError"},
                    "join_fanout_aggregation": {"SQLJoinValidationError"},
                }
                expected_types = expected_validator_types.get(spec["validator_oracle"], set())
                correctly_rejected = bool(expected_types) and error_type in expected_types
                row.update(
                    status="VALIDATOR_REJECTED" if correctly_rejected else "EXECUTION_FAILED",
                    executed_via="execute_approved_query",
                    detected=correctly_rejected,
                    detection_channel="approved_join_validator" if correctly_rejected else None,
                    validator_oracle_outcome="CORRECT_REJECTION" if correctly_rejected else "UNEXPECTED_REJECTION",
                    error_type=error_type,
                    error_detail=str(error)[:500],
                    elapsed_ms=round((asyncio.get_running_loop().time() - started) * 1000, 3),
                )
            entries.append(row)

    result_eligible = [item for item in entries if item["status"] == "EXECUTED"]
    detected = sum(item["detected"] for item in result_eligible)
    validator_metrics = {}
    for oracle in sorted({item["validator_oracle"] for item in entries if item.get("validator_oracle")}):
        applicable = [item for item in entries if item.get("validator_oracle") == oracle]
        numerator = sum(item.get("validator_oracle_outcome") == "CORRECT_REJECTION" for item in applicable)
        validator_metrics[oracle] = {
            "numerator": numerator,
            "denominator": len(applicable),
            "value": numerator / len(applicable) if applicable else None,
        }
    semantic_oracle_cases = [item for item in entries if item.get("semantic_validator_oracle")]
    semantic_validator_detected = sum(item.get("semantic_validator_detected") is True for item in semantic_oracle_cases)
    failures = [
        item["id"] for item in entries
        if item["status"] in {"INVALID_MUTATION", "EXECUTION_FAILED"}
        or item.get("unexpected_validator_behavior")
        or item.get("semantic_validator_outcome") in {"NOT_REJECTED", "UNEXPECTED_REJECTION"}
    ]
    revision, dirty = _source_state()
    captured = datetime.now(timezone.utc)
    captured_at_utc = captured.isoformat()
    return {
        "format_version": "sql-40-case-mutation-results.v3",
        "protocol_version": "3.1.0",
        "status": "COMPLETE_NOT_APPROVED" if not failures else "PARTIAL_NOT_APPROVED",
        "run_id": "mutation-v3-" + captured.strftime("%Y%m%dT%H%M%SZ"),
        "captured_at_utc": captured_at_utc,
        "source_revision": revision,
        "source_worktree_dirty": dirty,
        "python_version": platform.python_version(),
        "source_hashes": _source_hashes(),
        "case_set_sha256": _canonical_sha256(cases_doc),
        "gold_sql_file_sha256": _file_sha256(HERE / "gold_sql_v3_draft.json"),
        "gold_results_file_sha256": _file_sha256(gold_results_path),
        "preflight_file_sha256": _file_sha256(preflight_path),
        "database_classification": fresh["database_classification"],
        "database_role_read_only": True,
        "database_fingerprint_sha256": fresh["fingerprint_sha256"],
        "sql_agent_generation_calls": 0,
        "heldout_agent_executed": False,
        "database_write_attempts": 0,
        "mutations_attempted": len(entries),
        "invalid_mutations_not_counted": sum(item["status"] == "INVALID_MUTATION" for item in entries),
        "result_based_mutation_detection": {
            "numerator": detected,
            "denominator": len(result_eligible),
            "value": detected / len(result_eligible) if result_eligible else None,
        },
        "observationally_equivalent": sum(
            item["status"] == "EXECUTED" and not item["detected"] for item in entries
        ),
        "validator_detection": {
            "safety_and_join_validators": validator_metrics,
            "business_semantic_validator": {
                "validator": "validate_population_contract",
                "numerator": semantic_validator_detected,
                "denominator": len(semantic_oracle_cases),
                "value": semantic_validator_detected / len(semantic_oracle_cases) if semantic_oracle_cases else None,
            },
        },
        "failures": failures,
        "mutations": entries,
    }


async def _main(preflight_path: Path, gold_results_path: Path, output_path: Path):
    if output_path.exists():
        raise SystemExit(f"Refusing to overwrite existing mutation evidence: {output_path}")
    case_doc = json.loads((HERE / "cases_v3_draft.json").read_text(encoding="utf-8"))
    gold_sql_doc = json.loads((HERE / "gold_sql_v3_draft.json").read_text(encoding="utf-8"))
    gold_results_doc = json.loads(gold_results_path.read_text(encoding="utf-8"))
    preflight_doc = json.loads(preflight_path.read_text(encoding="utf-8"))
    result = await execute_probes(case_doc, gold_sql_doc, gold_results_doc, preflight_doc, preflight_path, gold_results_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, default=_json_value) + "\n")
    print(json.dumps({
        "status": result["status"],
        "mutations_attempted": result["mutations_attempted"],
        "failures": result["failures"],
        "result_based_mutation_detection": result["result_based_mutation_detection"],
        "validator_detection": result["validator_detection"],
        "database_fingerprint": result["database_fingerprint_sha256"],
        "heldout_agent_executed": result["heldout_agent_executed"],
        "output": str(output_path),
    }, ensure_ascii=False, indent=2))
    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", default=str(HERE / "database_preflight_v3.json"))
    parser.add_argument("--gold-results", default=str(HERE / "gold_results_v3_provisional.json"))
    parser.add_argument("--output", default=str(HERE / "mutation_results.json"))
    args = parser.parse_args()
    asyncio.run(_main(Path(args.preflight), Path(args.gold_results), Path(args.output)))
