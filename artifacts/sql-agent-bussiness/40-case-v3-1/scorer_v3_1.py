"""Versioned v3.1 scorer requiring linked independent semantic audits."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
OLD_SCORER_PATH = HERE.parent / "40-case-v3" / "scorer_v3.py"
AUDIT_PATH = HERE / "semantic_audit_v3_1.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load benchmark module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_base = _load("_sql_benchmark_scorer_v3", OLD_SCORER_PATH)
_audit = _load("_sql_benchmark_semantic_audit_v3_1", AUDIT_PATH)

SCORER_VERSION = "3.1.1"
PROTOCOL_VERSION = "3.1.0"


def _rate(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
        "status": "MEASURABLE" if denominator else "NOT MEASURABLE",
    }


def score(cases_doc: dict, reference_doc: dict, experiment_doc: dict) -> dict:
    """Score business results only when the full audit matches observed inputs."""
    cases = {case["id"]: case for case in cases_doc.get("cases", [])}
    observations = {case["id"]: case for case in experiment_doc.get("cases", [])}
    expected_case_set_hash = _audit.canonical_sha256(cases_doc)
    audits_by_id: dict[str, list[dict]] = {}
    supplied_audits = experiment_doc.get("independent_semantic_audits", [])
    for record in (supplied_audits if isinstance(supplied_audits, list) else []):
        if isinstance(record, dict) and isinstance(record.get("case_id"), str):
            audits_by_id.setdefault(record["case_id"], []).append(record)

    prepared = copy.deepcopy(experiment_doc)
    prepared_observations = {item["id"]: item for item in prepared.get("cases", [])}
    audit_evaluations = {}
    for case_id, observation in prepared_observations.items():
        case = cases.get(case_id)
        if case is None or case.get("expected_behavior") != "execute":
            observation["sql_semantic_valid"] = False
            continue
        candidates = audits_by_id.get(case_id, [])
        if len(candidates) != 1:
            decision, reasons = "INDETERMINATE", [
                "audit_record_missing" if not candidates else "duplicate_audit_records"
            ]
            record = None
        else:
            record = candidates[0]
            decision, reasons = _audit.validate_audit_record(
                record, case=case, case_set_sha256=expected_case_set_hash,
                observation=observation,
            )
        ranking_check = _audit.audit_ranking_contract(case, observation.get("sql", ""))
        if decision == "PASS" and ranking_check["decision"] == "FAIL":
            decision = "FAIL"
            reasons = [*reasons, *ranking_check["evidence"]]
        audit_evaluations[case_id] = {
            "decision": decision,
            "reason_codes": reasons,
            "ranking_check": ranking_check,
            "auditor_id": record.get("auditor_id") if record else None,
            "auditor_version": record.get("auditor_version") if record else None,
        }
        # The model-provided sql_semantic_valid flag is deliberately ignored.
        observation["sql_semantic_valid"] = decision == "PASS"

    result = _base.score(cases_doc, reference_doc, prepared)
    supported_attempted = {
        case_id for case_id, observation in observations.items()
        if cases.get(case_id, {}).get("expected_behavior") == "execute"
        and _base._attempted(observation)
    }
    decisions = {
        case_id: audit_evaluations.get(case_id, {}).get("decision", "INDETERMINATE")
        for case_id in supported_attempted
    }
    passed = sum(decision == "PASS" for decision in decisions.values())
    failed = sum(decision == "FAIL" for decision in decisions.values())
    determinate = passed + failed
    result["format_version"] = "sql-agent-business-scores.v3.1"
    result["protocol_version"] = PROTOCOL_VERSION
    result["scorer_version"] = SCORER_VERSION
    result["metrics"]["sql_semantic_accuracy"] = _rate(passed, len(supported_attempted))
    result["metrics"]["independent_semantic_audit_accuracy"] = _rate(passed, determinate)
    result["metrics"]["independent_semantic_audit_coverage"] = _rate(
        determinate, len(supported_attempted)
    )
    result["metrics"]["semantic_audit_unresolved"] = {
        "count": len(supported_attempted) - determinate,
        "denominator": len(supported_attempted),
        "decisions": {
            decision: sum(value == decision for value in decisions.values())
            for decision in ("REVIEW_REQUIRED", "INDETERMINATE")
        },
    }
    result["semantic_audits"] = audit_evaluations
    result["semantic_audit_policy"] = {
        "agent_sql_semantic_valid_accepted": False,
        "required_linkage": [
            "case_id", "sql_sha256", "parameters_sha256",
            "case_contract_sha256", "case_set_sha256",
        ],
        "business_end_to_end_requires_audit_pass": True,
    }
    return result
