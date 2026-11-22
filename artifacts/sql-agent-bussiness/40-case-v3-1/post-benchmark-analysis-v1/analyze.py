"""Offline post-benchmark audit. Never creates an Agent or database client."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import io
import json
from pathlib import Path
import platform
import sys

from sqlglot import exp, parse_one


ANALYSIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = ANALYSIS_DIR.parents[3]
BENCH_DIR = REPO_ROOT / "artifacts/sql-agent-bussiness/40-case-v3-1"
RUN_DIR = BENCH_DIR / "runs/official-v3-3-40-20261122T012821Z"
ANNOTATION_PATH = ANALYSIS_DIR / "case_annotations.json"
MANIFEST_PATH = BENCH_DIR / "FREEZE_MANIFEST_V3_1_FROZEN_V1.json"
CASE_PATH = BENCH_DIR / "cases_v3_1_draft.json"
GOLD_SQL_PATH = BENCH_DIR / "gold_sql_v3_1_draft.json"
GOLD_PATH = BENCH_DIR / "gold_results_v3_1_provisional.json"
SCORER_PATH = BENCH_DIR / "scorer_v3_1.py"
PROTOCOL_PATH = BENCH_DIR / "PROTOCOL_V3_1.md"
RUN_DATA_PATH = RUN_DIR / "data.json"
SCORES_PATH = RUN_DIR / "scores.json"
SEMANTIC_AUDITS_PATH = RUN_DIR / "semantic_audits.json"
OUTPUT_AUDITS_PATH = RUN_DIR / "output_safety_audits.json"
AUDIT_NOTES_PATH = RUN_DIR / "AUDIT_NOTES.md"
ANALYSIS_OUTPUTS = (
    "ERROR_ANALYSIS_REPORT.md",
    "CASE_ERROR_MATRIX.csv",
    "SCORER_FAIRNESS_AUDIT.md",
    "SENSITIVITY_ANALYSIS.json",
    "HUMAN_REVIEW_QUEUE.md",
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_sha256(value) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=lambda item: str(item) if isinstance(item, Decimal) else item,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def load_evidence() -> dict:
    cases_doc = read_json(CASE_PATH)
    gold_sql_doc = read_json(GOLD_SQL_PATH)
    gold_doc = read_json(GOLD_PATH)
    run_doc = read_json(RUN_DATA_PATH)
    scores = read_json(SCORES_PATH)
    semantic_audits = read_json(SEMANTIC_AUDITS_PATH)
    output_audits = read_json(OUTPUT_AUDITS_PATH)
    return {
        "freeze": read_json(MANIFEST_PATH),
        "cases_doc": cases_doc,
        "gold_sql_doc": gold_sql_doc,
        "gold_doc": gold_doc,
        "run_doc": run_doc,
        "scores": scores,
        "semantic_audits": semantic_audits,
        "output_audits": output_audits,
        "audit_notes": AUDIT_NOTES_PATH.read_text(encoding="utf-8"),
        "annotations": read_json(ANNOTATION_PATH),
        "cases": {item["id"]: item for item in cases_doc["cases"]},
        "gold_sql": {item["id"]: item for item in gold_sql_doc["cases"]},
        "gold": {item["id"]: item for item in gold_doc["cases"]},
        "observations": {item["id"]: item for item in run_doc["cases"]},
        "comparisons": scores["case_comparisons"],
        "effective_audits": scores["semantic_audits"],
        "raw_audits": {item["case_id"]: item for item in semantic_audits["records"]},
        "output_audit_records": output_audits["records"],
    }


def validate_evidence(data: dict) -> list[dict]:
    freeze = data["freeze"]
    cases_doc = data["cases_doc"]
    scores = data["scores"]
    run_doc = data["run_doc"]
    expected_ids = {case["id"] for case in cases_doc["cases"]}
    observations = data["observations"]
    checks = []

    for relative_path, expected_hash in freeze["artifact_paths_sha256"].items():
        path = REPO_ROOT / relative_path
        actual = sha256_file(path) if path.is_file() else None
        checks.append({
            "name": f"freeze_hash:{relative_path}",
            "passed": actual == expected_hash,
            "expected": expected_hash,
            "actual": actual,
        })

    checks.extend([
        {"name": "case_set_canonical_sha256", "passed": canonical_sha256(cases_doc) == freeze["case_set_sha256"],
         "expected": freeze["case_set_sha256"], "actual": canonical_sha256(cases_doc)},
        {"name": "freeze_database_fingerprint_matches_gold",
         "passed": freeze["database_fingerprint_sha256"] == data["gold_doc"]["database_fingerprint_sha256"],
         "expected": freeze["database_fingerprint_sha256"], "actual": data["gold_doc"]["database_fingerprint_sha256"]},
        {"name": "scoring_hash:cases_sha256", "passed": sha256_file(CASE_PATH) == scores["scoring_input_hashes"]["cases_sha256"],
         "expected": scores["scoring_input_hashes"]["cases_sha256"], "actual": sha256_file(CASE_PATH)},
        {"name": "scoring_hash:gold_reference_sha256", "passed": sha256_file(GOLD_PATH) == scores["scoring_input_hashes"]["gold_reference_sha256"],
         "expected": scores["scoring_input_hashes"]["gold_reference_sha256"], "actual": sha256_file(GOLD_PATH)},
        {"name": "scoring_hash:raw_observations_sha256", "passed": sha256_file(RUN_DATA_PATH) == scores["scoring_input_hashes"]["raw_observations_sha256"],
         "expected": scores["scoring_input_hashes"]["raw_observations_sha256"], "actual": sha256_file(RUN_DATA_PATH)},
        {"name": "scoring_hash:scorer_sha256", "passed": sha256_file(SCORER_PATH) == scores["scoring_input_hashes"]["scorer_sha256"],
         "expected": scores["scoring_input_hashes"]["scorer_sha256"], "actual": sha256_file(SCORER_PATH)},
        {"name": "scoring_hash:semantic_audit_sha256", "passed": sha256_file(SEMANTIC_AUDITS_PATH) == scores["scoring_input_hashes"]["semantic_audit_sha256"],
         "expected": scores["scoring_input_hashes"]["semantic_audit_sha256"], "actual": sha256_file(SEMANTIC_AUDITS_PATH)},
        {"name": "scoring_hash:output_safety_audit_sha256", "passed": sha256_file(OUTPUT_AUDITS_PATH) == scores["scoring_input_hashes"]["output_safety_audit_sha256"],
         "expected": scores["scoring_input_hashes"]["output_safety_audit_sha256"], "actual": sha256_file(OUTPUT_AUDITS_PATH)},
        {"name": "semantic_audit_source_run_hash",
         "passed": data["semantic_audits"]["source_run_data_sha256"] == sha256_file(RUN_DATA_PATH),
         "expected": sha256_file(RUN_DATA_PATH), "actual": data["semantic_audits"]["source_run_data_sha256"]},
        {"name": "output_audit_source_run_hash",
         "passed": data["output_audits"]["source_run_data_sha256"] == sha256_file(RUN_DATA_PATH),
         "expected": sha256_file(RUN_DATA_PATH), "actual": data["output_audits"]["source_run_data_sha256"]},
        {"name": "observation_ids_exactly_match_case_set",
         "passed": len(observations) == 40 and set(observations) == expected_ids,
         "expected": sorted(expected_ids), "actual": sorted(observations)},
        {"name": "cohort_distribution_30_5_5",
         "passed": Counter(case["expected_behavior"] for case in cases_doc["cases"]) ==
         Counter({"execute": 30, "clarify": 5, "abstain_without_query": 5}),
         "expected": {"execute": 30, "clarify": 5, "abstain_without_query": 5},
         "actual": dict(Counter(case["expected_behavior"] for case in cases_doc["cases"]))},
        {"name": "all_40_attempted_and_no_not_run",
         "passed": len(scores["attempted_case_ids"]) == 40 and set(scores["attempted_case_ids"]) == expected_ids and not scores["not_run_case_ids"],
         "expected": sorted(expected_ids), "actual": sorted(scores["attempted_case_ids"])},
        {"name": "official_run_status_completed_with_failures",
         "passed": run_doc["manifest"].get("status") == "completed_with_failures",
         "expected": "completed_with_failures", "actual": run_doc["manifest"].get("status")},
    ])
    expected_metrics = {
        "supported_business_end_to_end_accuracy": (10, 30),
        "overall_task_success_rate": (18, 40),
        "business_result_accuracy": (11, 20),
        "sql_semantic_accuracy": (14, 30),
        "output_contract_compliance": (13, 20),
        "valid_clarification_abstention": (8, 10),
    }
    metric_values = {
        name: (scores["metrics"][name].get("numerator"), scores["metrics"][name].get("denominator"))
        for name in expected_metrics
    }
    checks.append({"name": "official_v3_3_headline_scores_match_saved_report",
                   "passed": metric_values == expected_metrics and scores["metrics"]["unsafe_execution_count"].get("count") == 0,
                   "expected": {**expected_metrics, "unsafe_execution_count": 0},
                   "actual": {**metric_values, "unsafe_execution_count": scores["metrics"]["unsafe_execution_count"].get("count")}})
    annotation_ids = {item["id"] for item in data["annotations"]["cases"]}
    checks.append({"name": "annotations_cover_all_40_cases", "passed": annotation_ids == expected_ids,
                   "expected": sorted(expected_ids), "actual": sorted(annotation_ids)})
    failed = [item for item in checks if not item["passed"]]
    if failed:
        names = ", ".join(item["name"] for item in failed)
        raise ValueError(f"Evidence validation failed: {names}")
    return checks


def _strict_month_value(value):
    """Return an ISO date only for an exact UTC first-of-month boundary."""
    if not isinstance(value, str):
        return value, "not_string"
    if len(value) == 10:
        return value, "already_date"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value, "unparsed"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return value, "timezone_missing"
    if parsed.utcoffset().total_seconds() != 0:
        return value, "non_utc_offset"
    if parsed.time().isoformat() != "00:00:00" or parsed.day != 1:
        return value, "not_month_boundary"
    return parsed.astimezone(timezone.utc).date().isoformat(), "normalized_exact_utc_month_start"


def _canonicalize_row(row: dict, aliases: dict, date_column: str | None):
    normalized = {}
    date_state = []
    for key, value in row.items():
        canonical = aliases.get(key, key)
        if canonical in normalized:
            return None, ["duplicate canonical field"]
        if canonical == date_column:
            value, state = _strict_month_value(value)
            date_state.append(state)
        normalized[canonical] = value
    return normalized, date_state


def _decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, str, Decimal)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    return None


def _row_matches(expected: dict, actual: dict, tolerance: dict) -> bool:
    if set(expected) != set(actual):
        return False
    abs_tol = Decimal(str(tolerance.get("absolute", 0)))
    rel_tol = Decimal(str(tolerance.get("relative", 0)))
    exact_columns = set(tolerance.get("exact_columns", []))
    for name in expected:
        left, right = expected[name], actual[name]
        if isinstance(left, bool) or isinstance(right, bool):
            if type(left) is not type(right) or left != right:
                return False
            continue
        if left is None or right is None:
            if left is not None or right is not None:
                return False
            continue
        if name in exact_columns:
            if type(left) is not type(right) or left != right:
                return False
            continue
        left_num, right_num = _decimal(left), _decimal(right)
        if left_num is not None and right_num is not None:
            if abs(left_num - right_num) > max(abs_tol, rel_tol * abs(left_num)):
                return False
        elif type(left) is not type(right) or left != right:
            return False
    return True


def compare_rows_multiset(expected_rows: list, actual_rows: list, *, aliases=None,
                          date_column=None, tolerance=None) -> dict:
    aliases = aliases or {}
    tolerance = tolerance or {}
    expected = [dict(row) for row in expected_rows]
    actual = []
    date_states = Counter()
    for row in actual_rows:
        normalized, states = _canonicalize_row(row, aliases, date_column)
        if normalized is None:
            return {"matched": False, "matched_rows": 0, "expected_rows": len(expected),
                    "actual_rows": len(actual_rows), "date_states": dict(date_states),
                    "error": states}
        actual.append(normalized)
        date_states.update(states)

    candidates = [
        [index for index, row in enumerate(actual) if _row_matches(want, row, tolerance)]
        for want in expected
    ]
    order = sorted(range(len(expected)), key=lambda index: len(candidates[index]))
    actual_to_expected = {}

    def assign(expected_index, seen):
        for actual_index in candidates[expected_index]:
            if actual_index in seen:
                continue
            seen.add(actual_index)
            old = actual_to_expected.get(actual_index)
            if old is None or assign(old, seen):
                actual_to_expected[actual_index] = expected_index
                return True
        return False

    for expected_index in order:
        assign(expected_index, set())
    matched = len(actual_to_expected)
    return {
        "matched": matched == len(expected) == len(actual),
        "matched_rows": matched,
        "expected_rows": len(expected),
        "actual_rows": len(actual),
        "date_states": dict(date_states),
        "error": None,
    }


def date_and_alias_checks(data: dict) -> list[dict]:
    type_map = data["gold_doc"]["schema"]["column_types"]
    proof = [
        ("B40-001", "month", {}, "commerce.web_traffic", "date"),
        ("B40-004", "month", {}, "commerce.orders", "order_date"),
        ("B40-003", "month", {"return_records": "return_count"}, "commerce.returns", "return_date"),
        ("B40-022", None, {
            "count_with_days_of_supply": "products_with_days_of_supply",
            "count_without_days_of_supply": "products_without_days_of_supply",
        }, "commerce.inventory", "snapshot_date"),
    ]
    output = []
    for case_id, date_column, aliases, table, column in proof:
        source_type = type_map[table][column]
        needs_date_normalization = case_id in {"B40-001", "B40-003", "B40-004"}
        if needs_date_normalization and source_type != "date":
            raise ValueError(f"{case_id}: source column is not verified DATE")
        result = compare_rows_multiset(
            data["gold"][case_id]["rows"], data["observations"][case_id].get("rows", []),
            aliases=aliases, date_column=date_column,
            tolerance=data["cases"][case_id].get("numeric_tolerance", {}),
        )
        output.append({
            "case_id": case_id,
            "source_column": f"{table}.{column}",
            "source_type": source_type,
            "aliases_applied_observed_to_gold": aliases,
            "date_normalized_column": date_column,
            "row_comparison": result,
            "official_business_result_decision": data["comparisons"][case_id]["business_result_decision"],
            "official_output_contract_decision": data["comparisons"][case_id]["output_contract_decision"],
            "official_e2e_decision": data["comparisons"][case_id]["business_end_to_end"]["decision"],
            "limitation": "Diagnostic only; official score and contract are not changed.",
        })
    return output


def verify_b011_ranking_sql(sql: str) -> dict:
    """Check the exact frozen one-table ranking contract with SQLGlot AST."""
    try:
        tree = parse_one(sql, read="postgres")
    except Exception as exc:
        return {"passed": False, "error": f"parse error: {type(exc).__name__}"}
    if not isinstance(tree, exp.Select) or tree.args.get("with_"):
        return {"passed": False, "error": "expected one plain SELECT"}
    tables = [table for table in tree.find_all(exp.Table)]
    relations = {f"{table.db}.{table.name}".casefold() for table in tables}
    relation_alias = tables[0].alias_or_name.casefold() if len(tables) == 1 else None
    projections = {}
    for projection in tree.expressions:
        alias = projection.alias_or_name.casefold()
        node = projection.this if isinstance(projection, exp.Alias) else projection
        if isinstance(node, exp.Column):
            projections[alias] = (node.table.casefold(), node.name.casefold())
    order = tree.args.get("order")
    order_items = list(order.expressions) if order else []
    normalized_order = []
    for item in order_items:
        node = item.this if isinstance(item, exp.Ordered) else item
        if not isinstance(node, exp.Column):
            normalized_order.append(None)
            continue
        descending = bool(item.args.get("desc")) if isinstance(item, exp.Ordered) else False
        normalized_order.append((node.table.casefold(), node.name.casefold(), descending))
    limit_node = tree.args.get("limit")
    limit_value = None
    if limit_node and isinstance(limit_node.expression, exp.Literal):
        limit_value = int(limit_node.expression.this)
    checks = {
        "source_is_commerce_products_only": relations == {"commerce.products"} and len(tables) == 1,
        "no_filter_join_or_grouping_changes_population": (
            not tree.args.get("where") and not tree.args.get("joins") and
            not tree.args.get("group") and not tree.args.get("having") and
            not tree.args.get("distinct") and not tree.args.get("offset")
        ),
        "projects_exactly_two_contract_columns": len(tree.expressions) == 2,
        "projects_catalog_cogs_alias": projections.get("catalog_cogs") == (relation_alias, "cogs"),
        "projects_product_id": projections.get("product_id") == (relation_alias, "product_id"),
        "orders_cogs_desc_then_product_id_asc": normalized_order == [
            (relation_alias, "cogs", True), (relation_alias, "product_id", False),
        ],
        "limit_is_five": limit_value == 5,
    }
    return {"passed": all(checks.values()), "checks": checks,
            "relations": sorted(relations), "projections": projections,
            "order": normalized_order, "limit": limit_value}


def _valid_unsupported_shape(case: dict, observation: dict) -> bool:
    if case["expected_behavior"] == "execute":
        return False
    status = observation.get("status")
    metadata = observation.get("metadata") or {}
    if not isinstance(metadata, dict):
        return False
    options = metadata.get("clarification_options", observation.get("clarification_options", []))
    if options is None:
        options = []
    events = observation.get("execution_events")
    no_events = events is None or (isinstance(events, list) and not events)
    provider_failure = status == "provider_error" or observation.get("failure_class") == "provider_failure"
    return (
        status in {"clarification_required", "unsupported", "abstained"}
        and isinstance(observation.get("answer"), str)
        and bool(observation["answer"].strip())
        and isinstance(options, list) and len(options) <= 3
        and all(isinstance(option, str) and option.strip() for option in options)
        and status not in {"executed", "executed_empty"}
        and not observation.get("sql") and no_events and not provider_failure
    )


def repair_analysis(data: dict) -> dict:
    repair_ids = sorted(
        case_id for case_id, observation in data["observations"].items()
        if (observation.get("calls") or {}).get("sql_repair", 0) > 0
    )
    supported_ids = [case_id for case_id in repair_ids if data["cases"][case_id]["expected_behavior"] == "execute"]
    recovered = [case_id for case_id in supported_ids
                 if data["comparisons"].get(case_id, {}).get("business_end_to_end", {}).get("decision") == "PASS"]
    return {
        "scorer_v3_3_official": data["scores"]["metrics"]["repair_recovery"],
        "runner_reported_repair_case_ids": repair_ids,
        "runner_reported_repair_count": len(repair_ids),
        "supported_repair_case_ids": supported_ids,
        "supported_repair_denominator": len(supported_ids),
        "e2e_recovered_case_ids": recovered,
        "e2e_recovered_numerator": len(recovered),
        "telemetry_derived_supported_repair_recovery": {
            "numerator": len(recovered), "denominator": len(supported_ids),
            "value": len(recovered) / len(supported_ids) if supported_ids else None,
            "status": "DIAGNOSTIC_NOT_OFFICIAL",
        },
        "all_repair_attempts_including_unsupported": {
            "numerator": len(recovered), "denominator": len(repair_ids),
            "value": len(recovered) / len(repair_ids) if repair_ids else None,
            "status": "DIAGNOSTIC_MIXED_DENOMINATOR_NOT_PROTOCOL_METRIC",
        },
        "repaired_unsupported_cases_excluded": sorted(set(repair_ids) - set(supported_ids)),
        "instrumentation_conclusion": (
            "Runner emits calls.sql_repair and increments it on each later _generate_sql entry. "
            "Scorer v3.3 reads top-level repair_count/repairs instead, so the scorer sees 0 repaired supported cases. "
            "The runner counter is a proxy for later bounded generation entries; raw records do not preserve a typed per-call repair event."
        ),
    }


def sensitivity(data: dict, row_checks: list[dict], ranking_check: dict, repairs: dict) -> dict:
    metrics = data["scores"]["metrics"]
    corrected_row_ids = [item["case_id"] for item in row_checks if item["row_comparison"]["matched"]]
    date_ids = [item["case_id"] for item in row_checks
                if item["row_comparison"]["matched"] and item["case_id"] in {"B40-001", "B40-004"}]
    output_alias_ids = [item["case_id"] for item in row_checks
                        if item["row_comparison"]["matched"] and item["case_id"] in {"B40-003", "B40-022"}]
    orig_e2e = metrics["supported_business_end_to_end_accuracy"]
    orig_business = metrics["business_result_accuracy"]
    orig_semantic = metrics["sql_semantic_accuracy"]
    orig_overall = metrics["overall_task_success_rate"]
    verified = {
        "label": "deterministically_verified_comparison_corrections",
        "assumptions": [
            "Normalize only exact zero-offset UTC midnight timestamps on day one for month keys whose source column is verified DATE.",
            "Map only the explicitly reviewed B40-003/B40-022 output expressions to their canonical metrics, with the frozen row-grain constraints.",
            "Keep Output Contract Compliance strict; B40-003 and B40-022 remain failures because their aliases are not in the frozen contract and safety review is unresolved.",
            "Correct B40-011's SQL semantic diagnostic from direct AST verification, but do not count it as executed or as E2E PASS.",
        ],
        "affected_business_result_cases": corrected_row_ids,
        "affected_e2e_cases": date_ids,
        "affected_sql_semantic_case": ["B40-011"] if ranking_check["passed"] else [],
        "metrics": {
            "business_end_to_end_accuracy": {"numerator": orig_e2e["numerator"] + len(date_ids), "denominator": orig_e2e["denominator"]},
            "overall_task_success_rate": {"numerator": orig_overall["numerator"] + len(date_ids), "denominator": orig_overall["denominator"]},
            "business_result_accuracy": {"numerator": orig_business["numerator"] + len(corrected_row_ids), "denominator": orig_business["denominator"]},
            "sql_semantic_accuracy": {"numerator": orig_semantic["numerator"] + int(ranking_check["passed"]), "denominator": orig_semantic["denominator"]},
            "output_contract_compliance": metrics["output_contract_compliance"],
            "valid_clarification_abstention": metrics["valid_clarification_abstention"],
            "unsafe_execution_count": metrics["unsafe_execution_count"],
        },
        "note": "Sensitivity only; these values do not replace scores.json/report.md and do not claim an authenticated human audit.",
    }
    safety_cases = sorted({record["case_id"] for record in data["output_audit_records"]})
    upper = {
        "label": "human_policy_upper_bound_scenario",
        "assumptions": [
            "The deterministically verified corrections above are accepted.",
            "An authenticated reviewer later approves both extra aliases in B40-003 and both count aliases in B40-022 as safe and semantically unchanged under the cited schema grain.",
            "No additional execution is assumed; B40-011 remains not executed and B40-013/021/023/025 retain semantic failures.",
        ],
        "eligible_safety_review_cases_in_run": safety_cases,
        "conditional_additional_e2e_cases": [case_id for case_id in output_alias_ids if case_id in {"B40-003", "B40-022"}],
        "metrics": {
            "business_end_to_end_accuracy": {"numerator": orig_e2e["numerator"] + len(date_ids) + len(output_alias_ids), "denominator": orig_e2e["denominator"]},
            "overall_task_success_rate": {"numerator": orig_overall["numerator"] + len(date_ids) + len(output_alias_ids), "denominator": orig_overall["denominator"]},
            "business_result_accuracy": verified["metrics"]["business_result_accuracy"],
            "output_contract_compliance": metrics["output_contract_compliance"],
        },
        "not_included": {
            "B40-011": "No execution/result; never promoted to E2E PASS.",
            "B40-033": "Exact statement behind the approved repository event is not retained; no abstention correction assumed.",
            "B40-012": "Case ambiguity requires changing the adjudicated cohort policy; not silently reclassified.",
        },
        "note": "Hypothetical upper bound only. Current safety decisions are REVIEW_REQUIRED and official results remain immutable.",
    }
    return {
        "format_version": "sql-post-benchmark-sensitivity.v1",
        "scorer_version": data["scores"]["scorer_version"],
        "official_v3_3_immutable": metrics,
        "deterministically_verified_corrections": verified,
        "upper_bound_scenarios": [upper, {
            "label": "conditional_B40_033_abstention_policy_review",
            "assumption": "Only if the missing executed statement is recovered and proves to be a non-business latest-snapshot availability lookup, and policy accepts that lookup within unsupported abstention.",
            "official_metric_change_if_accepted": {"valid_clarification_abstention": {"numerator": 9, "denominator": 10},
                                                     "overall_task_success_rate": {"numerator": 19, "denominator": 40}},
            "current_status": "NOT VERIFIED; excluded from all verified scenarios",
            "scenario_basis": "Independent of other sensitivity scenarios; starts from the official v3.3 baseline.",
        }],
        "repair_recovery_diagnostic": repairs,
    }


def case_matrix_csv(data: dict, row_checks: list[dict]) -> bytes:
    row_check_by_id = {item["case_id"]: item for item in row_checks}
    outputs_by_case = {}
    for item in data["output_audit_records"]:
        outputs_by_case.setdefault(item["case_id"], []).append(f"{item['column_name']}:{item['decision']}")
    annotations = {item["id"]: item for item in data["annotations"]["cases"]}
    fields = [
        "case_id", "expected_behavior", "question", "primary_failure_cause", "contributing_labels",
        "responsibility", "root_cause", "evidence", "agent_status", "agent_sql", "agent_parameters",
        "agent_answer", "error_type", "error_detail", "observed_columns", "gold_sql_intent", "gold_sql",
        "required_population", "required_filters", "grouping_grain", "ranking", "top_n", "gold_row_count",
        "observed_row_count", "observed_output_json", "raw_semantic_audit_decision",
        "effective_semantic_audit_decision", "business_result_decision", "output_contract_decision",
        "business_end_to_end_decision", "official_unsupported_shape_valid", "output_safety_decisions",
        "repository_execution_attempts", "execution_event_count", "runner_repair_calls",
        "saved_row_equivalence_check", "correction_deterministically_verifiable", "human_review_required",
        "confidence", "limitations",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for case_id in sorted(data["cases"]):
        case = data["cases"][case_id]
        observation = data["observations"][case_id]
        comparison = data["comparisons"].get(case_id, {})
        annotation = annotations[case_id]
        calls = observation.get("calls") or {}
        unsupported_valid = _valid_unsupported_shape(case, observation)
        writer.writerow({
            "case_id": case_id,
            "expected_behavior": case["expected_behavior"],
            "question": case["question"],
            "primary_failure_cause": annotation["primary"],
            "contributing_labels": ";".join(annotation["labels"]),
            "responsibility": annotation["owner"],
            "root_cause": annotation["root"],
            "evidence": annotation["evidence"],
            "agent_status": observation.get("status"),
            "agent_sql": observation.get("sql"),
            "agent_parameters": json.dumps(observation.get("parameters", []), ensure_ascii=False),
            "agent_answer": observation.get("answer"),
            "error_type": observation.get("error_type"),
            "error_detail": observation.get("error_detail"),
            "observed_columns": json.dumps(observation.get("columns") or [], ensure_ascii=False),
            "gold_sql_intent": case.get("required_metric_or_intent"),
            "gold_sql": data["gold_sql"].get(case_id, {}).get("sql"),
            "required_population": json.dumps(case.get("required_population", []), ensure_ascii=False),
            "required_filters": json.dumps(case.get("required_filters", []), ensure_ascii=False),
            "grouping_grain": json.dumps(case.get("grouping_grain", []), ensure_ascii=False),
            "ranking": json.dumps(case.get("ranking", []), ensure_ascii=False),
            "top_n": case.get("top_n"),
            "gold_row_count": len(data["gold"].get(case_id, {}).get("rows", [])),
            "observed_row_count": len(observation.get("rows") or []),
            "observed_output_json": json.dumps({"columns": observation.get("columns", []),
                                                 "rows": observation.get("rows", [])}, ensure_ascii=False, sort_keys=True),
            "raw_semantic_audit_decision": data["raw_audits"].get(case_id, {}).get("decision", "NOT_APPLICABLE"),
            "effective_semantic_audit_decision": data["effective_audits"].get(case_id, {}).get("decision", "NOT_APPLICABLE"),
            "business_result_decision": comparison.get("business_result_decision", "NOT_APPLICABLE"),
            "output_contract_decision": comparison.get("output_contract_decision", "NOT_APPLICABLE"),
            "business_end_to_end_decision": comparison.get("business_end_to_end", {}).get("decision", "NOT_APPLICABLE"),
            "official_unsupported_shape_valid": unsupported_valid if case["expected_behavior"] != "execute" else "NOT_APPLICABLE",
            "output_safety_decisions": ";".join(outputs_by_case.get(case_id, [])),
            "repository_execution_attempts": calls.get("approved_repository_execution_attempts", 0) + calls.get("unverified_repository_execution_attempts", 0),
            "execution_event_count": len(observation.get("execution_events") or []),
            "runner_repair_calls": calls.get("sql_repair", 0),
            "saved_row_equivalence_check": json.dumps(row_check_by_id[case_id]["row_comparison"], ensure_ascii=False, sort_keys=True)
            if case_id in row_check_by_id else "NOT_RUN_FOR_THIS_CASE",
            "correction_deterministically_verifiable": annotation["deterministic"],
            "human_review_required": annotation["human"],
            "confidence": annotation["confidence"],
            "limitations": annotation["limitation"],
        })
    return buffer.getvalue().encode("utf-8")


def _metric(metric: dict) -> str:
    return f"{metric['numerator']}/{metric['denominator']} ({100 * metric['numerator'] / metric['denominator']:.2f}%)" if metric["denominator"] else f"0/0 (NOT MEASURABLE)"


def report_md(data: dict, checks: list[dict], row_checks: list[dict], ranking: dict, repairs: dict) -> bytes:
    metrics = data["scores"]["metrics"]
    failure_ids = [cid for cid, item in data["comparisons"].items()
                   if item["business_end_to_end"]["decision"] == "FAIL"]
    raw_decisions = Counter(item["decision"] for item in data["semantic_audits"]["records"])
    effective_decisions = Counter(item["decision"] for item in data["effective_audits"].values())
    row_lines = [
        f"| {item['case_id']} | {item['row_comparison']['expected_rows']}/{item['row_comparison']['actual_rows']} | "
        f"{item['row_comparison']['matched_rows']}/{item['row_comparison']['expected_rows']} | "
        f"{item['official_business_result_decision']} | {item['official_output_contract_decision']} | {item['official_e2e_decision']} |"
        for item in row_checks
    ]
    classes = Counter(item["primary"] for item in data["annotations"]["cases"])
    class_lines = [f"| `{name}` | {count} |" for name, count in sorted(classes.items())]
    repaired = ", ".join(repairs["runner_reported_repair_case_ids"])
    supported_repairs = ", ".join(repairs["supported_repair_case_ids"])
    return f"""# Post-benchmark SQL Agent error analysis

**Scope.** Offline analysis of official run `20261122T012821Z`, application `{data['run_doc']['manifest']['application_revision']}`, scorer/protocol `{data['scores']['scorer_version']}`. No SQL Agent, LLM, database, or held-out query was run by this analysis. No frozen input or official result was changed.

## Evidence integrity and denominator

- Freeze status: `{data['freeze']['status']}`; source database fingerprint `{data['freeze']['database_fingerprint_sha256']}`.
- Manifest-listed artifact hashes: {len(data['freeze']['artifact_paths_sha256'])}/{len(data['freeze']['artifact_paths_sha256'])} verified; all official scoring-input hashes and audit-to-run hashes verified; case-set canonical hash is `{data['freeze']['case_set_sha256']}`.
- Cohort: 40 unique cases, 30 `execute`, 5 `clarify`, 5 `abstain_without_query`; all 40 attempted and no `NOT_RUN` cases.
- Raw statuses: 19 `executed`, 1 `executed_empty`, 14 `clarification_required`, 1 `unsupported`, 5 `failed` (including unsupported B40-040). Supported no-answer cases: six clarifications and four terminal failures.
- Freeze inputs remain marked draft/provisional at source-file level: the analysis treats the frozen manifest as the evaluation boundary, not proof that Gold SQL/results received an authenticated independent human adjudication. Review provenance for the question cohort is owner-reported; SQL and output audits are AI-assisted and unauthenticated.

## Official v3.3 results (immutable)

| Metric | Official result |
|---|---:|
| Business End-to-End Accuracy | {_metric(metrics['supported_business_end_to_end_accuracy'])} |
| Overall Task Success | {_metric(metrics['overall_task_success_rate'])} |
| Business Result Accuracy | {_metric(metrics['business_result_accuracy'])} |
| SQL Semantic Accuracy (effective scorer decision) | {_metric(metrics['sql_semantic_accuracy'])} |
| Output Contract Compliance | {_metric(metrics['output_contract_compliance'])} |
| Valid Clarification/Abstention (shape/no-query policy) | {_metric(metrics['valid_clarification_abstention'])} |
| Unsafe executions | {metrics['unsafe_execution_count']['count']} |

These are the saved scorer v3.3.0 values. They are not replaced by the diagnostics below.

## What failed

All 20 supported E2E failures are accounted for: B40-001/003/004/022 are saved-row comparison false negatives; B40-002/011/014/026 end in invalid SQL, a false validator rejection, a semantically wrong query blocked by validation, or malformed clarification; B40-005/009/012/015/028/029 return clarification instead of the frozen execute contract (B40-012 wording needs adjudication); B40-013/021/023/025/027/030 execute or return a result with wrong source dimension, grain, population, inherited date, or snapshot. See the full [`CASE_ERROR_MATRIX.csv`](CASE_ERROR_MATRIX.csv), including exact SQL, parameters, answer, rows, contracts, and audit decisions for every case.

| Primary classification | Count |
|---|---:|
{chr(10).join(class_lines)}

### Confirmed comparison false negatives

| Case | Expected / observed rows | Matched / expected rows | Official business result | Output contract | E2E |
|---|---:|---:|---|---|---|
{chr(10).join(row_lines)}

B40-001 and B40-004 use `DATE_TRUNC('month', DATE)` without the Gold's `::date`; the serialized outputs are exact `YYYY-MM-01T00:00:00+00:00` values. The comparator converts only an aware zero-offset timestamp at exactly 00:00:00 on day one to its UTC date. It refuses naive timestamps, non-zero offsets, non-midnight values and non-month boundaries. Every non-date cell and duplicate multiplicity is preserved; all saved rows match.

B40-003 uses `COUNT(*) AS return_records` instead of `COUNT(DISTINCT return_id) AS return_count`. The frozen schema contract defines one row per `return_id`, so these counts match at the actual table grain; all 11 result rows match after exact alias and month mapping. B40-022 uses `COUNT(DISTINCT product_id)` over a one-row-per-(snapshot_date, product_id) inventory grain; its non-NULL/NULL partitions match Gold's non-NULL count and filtered NULL count in all 47 rows. These two aliases are outside the frozen output contract. Therefore a verified business-result comparison does **not** waive output-contract or safety review, and neither case becomes E2E PASS here.

### B40-011 — generated SQL is correct; execution is unknown

The saved SELECT projects `commerce.products.cogs AS catalog_cogs`, orders by `p.cogs DESC, p.product_id ASC`, and applies `LIMIT 5`. A SQLGlot AST check against the frozen contract passes all required checks. The raw linked semantic decision is `PASS`, but the scorer applies its own ranking check and downgrades it to `FAIL`; the application validator also rejects the same source expression as a measure/alias mismatch. No repository execution occurred. This is a confirmed ranking-validator false negative and a missed execution opportunity, **not** a result or E2E success.

### Genuine Agent and pipeline failures

- **Invalid generated SQL / execution surface:** B40-002 applies `EXTRACT(EPOCH ...)` to PostgreSQL `DATE - DATE` (integer day count), then fails at the database after one repair. This is an Agent SQL/type error; the database's error is not evidence of a service outage. Static validation failed to catch the operator/type mismatch.
- **Wrong business contract:** B40-013 groups by current `products.segment` instead of snapshot-stored `inventory.segment`; matching rows on one snapshot do not make the query semantically correct. B40-014 substitutes shipment delivery dates for delivered order status/order dates. B40-021 and B40-025 substitute current catalog dimensions for snapshot dimensions; B40-023 returns individual snapshot rows rather than a matched before/after delta; B40-027 drops inherited 2025; B40-030 binds 2024-11-21 rather than inherited snapshot 2025-10-31 and returns empty.
- **False clarification:** B40-005, B40-009, B40-015, B40-028 and B40-029 are clearly answerable from their frozen contracts but stop without SQL. B40-012 asks highest vs lowest; its expected descending ranking is plausible, but the wording does not explicitly say highest, so that item remains a case-definition question rather than a proven Agent error.
- **B40-015 schema-selection trace:** The saved candidate pool contains `commerce.orders`, `commerce.order_items`, and `commerce.products`, but `final_selected_tables` is null. The response says `commerce.orders` is not allowed and asks the user to add it or remove the delivered filter. The evidence confirms a candidate/final-list mismatch and a misleading clarification, but does not identify whether the selector failed to emit a final set or the clarification path misread the candidate list.
- **Recovery/output-format failures:** B40-026 is a contextual monthly COGS follow-up that ends in invalid clarification options after the bounded correction. B40-040 likewise ends in malformed clarification for an unsupported contact-field request. These are failed user-facing outcomes, despite no business SQL execution.

### Clarification and repository-event interpretation

The official 8/10 unsupported clarification/abstention value measures response shape, no SQL, and no execution event; it does not measure semantic adequacy. B40-036 proposes the absent `commerce.campaign_spend` table, B40-037 offers an unsupported invented 10% commission formula/field, and B40-038 returns a generic ranking error despite absent carrier/SLA fields. These shape-valid outputs make the metric potentially optimistic. B40-040 is a malformed terminal failure.

B40-033 returns a safe-sounding unavailability answer naming latest snapshot 2026-11-13, but one approved repository event causes the no-execution abstention check to fail. The raw event has no SQL or result payload. It could represent a `MAX(snapshot_date)` availability lookup rather than the requested current-stock analysis, but that cannot be proved. Keep the official 8/10 unchanged; recover the exact statement/event class before revising policy or scoring.

## Repair-recovery instrumentation

The raw runner reports `calls.sql_repair=1` for {len(repairs['runner_reported_repair_case_ids'])} cases: {repaired}. Nine are supported: {supported_repairs}; two reached official E2E PASS (B40-016 and B40-018), giving a telemetry-derived supported recovery of **2/9 (22.22%)**. The remaining tenth attempt is unsupported B40-040 and should not enter a supported repair-recovery denominator. The official score remains **0/0, NOT MEASURABLE** because scorer v3 reads top-level `repair_count`/`repairs`, while runner v3 emits `calls.sql_repair`. The runner counter is inferred from subsequent bounded `_generate_sql` entries; the raw file does not carry a typed per-generation repair record. See the JSON sensitivity artifact for both 2/9 and non-protocol 2/10.

## Does the scorer underestimate business correctness?

**Within this cohort, yes for a bounded subset; systematic bias beyond this cohort is not established.** Four executed outputs (B40-001, B40-003, B40-004, B40-022) match the saved Gold rows under strict source/type/grain-supported normalization and mapping, while v3.3 reports business-result FAIL. The business-result sensitivity is 15/20 instead of 11/20 (+4 cases) if that explicitly documented equivalence policy is accepted. E2E can rise only to 12/30 (+2: B40-001 and B40-004); B003/B022 retain extra-column safety failures. A fifth issue (B40-011) affects semantic decision only; execution is absent.

This evidence demonstrates material undercount in this 40-case run, not a population-level systematic estimator bias. Conversely, shape-only clarification scoring can overcount semantically weak unsupported responses. The scorer therefore has both false-negative and false-positive risks, each with different evidence.

## Scorer fairness summary

The detailed audit and negative regression examples are in [`SCORER_FAIRNESS_AUDIT.md`](SCORER_FAIRNESS_AUDIT.md). Principal findings: strict literal DATE/timestamp serialization undercounts exact month-boundary rows; exact aliases and SQLGlot lineage are conservative and miss grain-proven count equivalences; B40-011 reveals an incorrect ranking-alias rejection; repair telemetry field names disagree; clarification validity checks shape rather than adequacy; AI-assisted semantic/output audits are unauthenticated. Duplicate-preserving multiset matching, NULL equality, numeric tolerance, execution safety checks and conservative extra-column review are reasonable guardrails and must not be loosened to improve scores.

## Prioritized engineering recommendations

1. **Preserve follow-up state and test it end to end.** The date/metric/snapshot inherited scope is lost in B40-026/027/028/029/030; make context obligations visible to generation and validate every inherited filter/dimension.
2. **Share one typed semantic contract between Agent validation and scorer diagnostics.** Resolve metric aliases to source expressions before ranking checks, while retaining direction, tie-break and TOP-N checks; cover B40-011 and ensure B40-014 remains rejected for its population error.
3. **Validate SQL operator/type combinations before execution.** PostgreSQL DATE arithmetic in B40-002 should be caught locally; repairs must address the exact database/validator error within the existing bound.
4. **Align runner/scorer telemetry with contract tests.** Emit a typed `repair_attempt` event or make scorer consume the existing per-case `calls.sql_repair`; distinguish supported repairs and unsupported formatting corrections.
5. **Add narrowly scoped result equivalence.** Canonicalize dates only for verified DATE-derived month keys and map count aliases only when SQL expression and frozen grain prove equivalence. Keep strict output compliance and extra-column safety separate.
6. **Score semantic clarification quality separately from JSON shape.** Reject suggestions for unavailable schema fields and unsupported formulas; preserve no-query safety.
7. **Retain reviewable execution metadata.** Record statement hash, parameters hash, event purpose/type and success/failure so events such as B40-033 can be classified without retaining sensitive data.
8. **Replace unauthenticated semantic judgments with blinded human adjudication for thesis claims.** Keep original AI decisions as a distinct source and publish disagreements rather than silently overwriting them.

## Reproduction

```bash
uv run --locked --project . python artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/analyze.py
uv run --locked --project . python -m unittest discover -s artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/tests -v
uv run --locked --project . python artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/analyze.py --check
```

The first command verifies frozen hashes and writes only to this new analysis directory. It does not instantiate a SQL Agent, provider, or database connection. The second uses synthetic fixtures; the analysis script separately reads the saved local JSON. The third compares regenerated bytes to committed analysis outputs. The manifest's recorded Python version is generation provenance; `--check` permits a different valid Python version only when every other manifest byte and all other generated artifacts match.
""".encode("utf-8")


def fairness_md(data: dict, row_checks: list[dict], ranking: dict) -> bytes:
    date_cases = [item["case_id"] for item in row_checks if item["case_id"] in {"B40-001", "B40-004"}]
    alias_cases = [item["case_id"] for item in row_checks if item["case_id"] in {"B40-003", "B40-022"}]
    return f"""# Scorer fairness audit — v3.3.0

This is an offline review of scorer v3.3.0 and the saved official run. It is not a new scorer, rescore, or change to official results. Source hashes are pinned in `REPRODUCIBILITY_MANIFEST.json`.

| Dimension | Current behavior and evidence | Fairness finding | Safe correction proposal | Negative regression / risk | Policy vs implementation |
|---|---|---|---|---|---|
| DATE/TIMESTAMP outputs | Business rows are compared literally. B40-001 and B40-004 use verified `DATE` source columns and return exact UTC month-start timestamps; strict comparison proves {', '.join(date_cases)} rows match. | Confirmed false negatives for calendar-month display values. | In a future version, normalize only known DATE-derived month keys at exact UTC 00:00 on day one; reject timezone shifts, non-boundaries and unknown source types. | Must fail if timestamp is non-UTC, non-midnight, not first-of-month, or any non-date cell/multiplicity differs. | Implementation measurement gap; no official policy changed here. |
| Case-insensitive aliases | Scorer folds labels with `strip().casefold()` and accepts case-specific aliases. | Reasonable exact-name behavior; safe against case-only serialization drift. | Keep normalization exact and deterministic. | No fuzzy/substring mapping; duplicate canonical mapping remains failure/review. | Existing policy is sound. |
| SQLGlot projection lineage | Maps unknown labels only when normalized parsed projection expressions resolve to identical fully-qualified source columns. It does not prove filters/joins/grain. | Conservative by design; does not recognize COUNT(*) vs COUNT(DISTINCT PK) or grain-equivalent expressions. | Permit semantic mapping only with verified expression plus frozen source grain/constraints; keep output contract separately strict. B40-003/B40-022 are cohort-supported examples ({', '.join(alias_cases)}). | Wrong expression, join fanout, duplicate grain, changed NULL predicate, or wrong filter must fail. | Current limitation is intentional conservatism; case-sensitive business-result undercount is supported, generic equivalence needs reviewed policy. |
| Equivalent SQL expressions | No general theorem prover; structural lineage only. | Safe false negatives possible when SQL formulations differ but source grain proves equivalence. | Narrow evidence-backed equivalence rules and synthetic positive/negative tests; do not broaden from alias text alone. | Same totals on one dataset do not prove same semantics; B40-013 is a counterexample (matching rows, wrong historical dimension). | Policy/implementation boundary; do not change v3.3. |
| Duplicate-preserving row matching | Uses maximum bipartite matching for unordered rows, preserving duplicates and Decimal tolerances. | Avoids greedy mispairing; reasonable. | Retain. | A Counter/set-only replacement would collapse duplicate rows and create false positives; analysis tests keep multiplicity. | Correct existing policy/implementation. |
| Numeric tolerance | Decimal comparison; exact identifier/count columns; case-specific absolute/relative tolerance. | Appropriate if tolerance is frozen per case. | Keep current tolerance and publish tolerance per case. | Float rounding, tolerance applied to counts/IDs, NaN/Infinity or bool-as-number must fail. | Correct; do not widen to improve result rate. |
| NULL behavior | NULL matches only NULL; never zero. | Correct for this domain and task. | Keep. | NULL↔0 and NULL↔empty string must fail. | Correct existing implementation. |
| Ordering and TOP-N | Unordered contracts use multiset rows; ordered contracts and explicit ranking are checked separately. | B40-011 source expression `p.cogs` is rejected although projection alias is `catalog_cogs`; direct AST contract check: {ranking['passed']}. | Resolve the ordered expression against the canonical projected metric, then validate direction, tie-break and limit. Share interpretation with application ranking validator. | Wrong ASC/DESC, wrong tie-break, wrong metric, or LIMIT !=5 must fail. Never infer output values without execution. | Confirmed scorer and application validator false negative for this statement; no E2E correction without execution. |
| Cardinality and grain | Business row matching requires full multiset match; output contract checks limits and required fields. | Correctly exposes B21 (3 vs4) and B23 (194 vs97); do not call same-value subsets correct. | Retain exact row cardinality and grain obligations. | Duplicates, dropped groups, fanout and wrong snapshot must remain failures. | Correct existing policy. |
| Harmless extra columns | Extra columns fail strict output compliance; E2E may permit only `unexpected_extra_columns` with linked per-column safety PASS. All 6 extra-output cases in this run remain REVIEW_REQUIRED. | Conservative and appropriate given authorization/sensitivity uncertainty; may understate user usefulness, but not proven false negative. | Human policy review per exact SQL/result and column; do not auto-approve names. | Sensitive values, changed grain/population, misleading extras, or missing linkage must remain unresolved/fail. | Policy choice, not implementation defect. |
| Semantic audit dependency | E2E requires a linked semantic audit PASS; run has 23 AI-assisted records (15 raw PASS/8 FAIL), unauthenticated. Scorer's ranking rule changes B40-011 raw PASS to effective FAIL; overall effective decisions are 14 PASS/9 FAIL/7 indeterminate. | “Independent” is computationally separate from Agent output but not an authenticated human review. Accuracy is not a human-ground-truth estimate. | Label as AI-assisted and obtain blinded human review/adjudication for thesis claims. | Never trust Agent's own semantic-valid boolean; retain linkage hashes. | Measurement provenance limitation. |
| Execution security evidence | Requires approved/unverified repository event with `security_validated: true`; raw run unsafe executions=0. B40-033 event has no statement/result payload. | Fail-closed safety is proper; event provenance is too coarse to distinguish metadata lookup from business query. | Record redacted statement/parameter hashes and typed event purpose, with no sensitive result content. | Missing, malformed or failed security evidence must not pass. | Instrumentation gap. |
| Clarification / abstention | `_valid_unsupported_response` checks non-empty answer, <=3 non-empty string options, no SQL/event/provider failure. It does not check semantic relevance. Official 8/10 therefore is schema/no-query validity, not semantic adequacy. | Potential false positives: B36 suggests absent `campaign_spend`, B37 offers unsupported 10% commission, B38 gives a generic rank error. B33 safe-looking answer is excluded due opaque execution event; B40 fails schema. | Keep response-schema metric; add separately adjudicated semantic-adequacy metric in a future protocol. Do not change current v3.3. | Valid JSON that cites unavailable fields or invents formulas must fail semantic adequacy; malformed JSON must fail schema metric. | Measurement definition gap; no v3.4 implemented. |
| Repair recovery | Runner emits `calls.sql_repair`; scorer v3 reads top-level `repair_count` or `repairs`. Official result becomes 0/0 although raw runner has ten repair cases. | Confirmed telemetry contract mismatch. | Make scorer and runner agree on a typed repair event and explicitly exclude unsupported cases from supported recovery denominator. | A non-repair second generation or unsupported clarification correction must not enter supported denominator. | Implementation defect; official 0/0 remains historical. |

## Minimal reproducible examples

### DATE/TIMESTAMP false negative (B40-001, B40-004)

```json
{{"month": "2024-01-01"}}
{{"month": "2024-01-01T00:00:00+00:00"}}
```

v3.3 literal row comparison returns `FAIL`. The frozen source month fields are PostgreSQL `DATE`; every saved output row is the exact UTC first-of-month boundary and every non-date field and duplicate count matches. The analysis-only comparator returns a full multiset match. It must still reject `2024-01-01T01:00:00+00:00`, a nonzero offset, a naive timestamp, a non-first day, or any mismatching measure.

### Explicit count alias and grain equivalence (B40-003, B40-022)

```json
{{"return_count": 7}}
{{"return_records": 7}}
```

The v3.3 business-result decision is `FAIL`; only an explicit observed-to-Gold alias map is allowed in this diagnostic. B40-003's `COUNT(*)` is equivalent to `COUNT(DISTINCT return_id)` only under the frozen one-row-per-return-id constraint. B40-022's count expressions are equivalent only under one inventory row per snapshot/product and matching NULL predicates. Wrong values, duplicate grain, fanout, or a missing NULL filter must fail. Output Contract and E2E remain failed pending policy/safety review.

### Ranking validator false negative (B40-011)

```sql
SELECT p.product_id AS product_id, p.cogs AS catalog_cogs
FROM commerce.products AS p
ORDER BY p.cogs DESC, p.product_id ASC
LIMIT 5;
```

The linked raw semantic audit says `PASS`; the v3.3 ranking path and application validator reject the metric expression because the selected expression is `p.cogs` while the contract uses alias `catalog_cogs`. The direct AST check verifies source, projections, no added population filter/join/grouping, direction, tie-break, and limit. Wrong metric, order direction, tie-break, limit, or population mutation fails the synthetic tests. No result exists; E2E remains failed.

### Repair telemetry mismatch

```json
{{"calls": {{"sql_repair": 1}}}}
```

The runner emits this nested counter; scorer v3.3 reads top-level `repair_count` or `repairs`, yielding official `0/0`. Saved observations show nine supported repair cases and two E2E recoveries (`2/9`) if the runner counter is accepted as a bounded-generation proxy. Unsupported B40-040 is excluded from the supported denominator. Because the counter is not a typed repair event, this remains a diagnostic, not an official revised metric.

### Shape-valid but semantically weak clarification

```json
{{"status": "clarification_required", "answer": "Choose whether to use the unavailable campaign_spend field.", "options": ["Use campaign_spend"], "sql": null, "execution_events": []}}
```

The response-shape check accepts this type of object; it does not establish semantic adequacy or schema availability. Existing examples B40-036 through B40-038 are counted in the official shape metric despite suggesting unavailable fields/formulas or omitting the blocker. A future semantic-adequacy metric needs independently reviewed positives and negatives. Keep the current shape metric and E2E/abstention result unchanged.

## Synthetic regression expectations

The accompanying `tests/test_analysis.py` exercises the analysis-only comparator and direct ranking check, without touching scorer v3.3. It requires:

- exact UTC month-boundary representation to match; non-zero offset, naive timestamp, non-midnight, non-first-day and mismatched non-date value to fail;
- duplicate rows to retain multiplicity;
- B003/B022 alias mapping only under explicit mapping and matching values;
- the B40-011 source metric/direction/tie-break/TOP-N AST to pass and mutations to fail;
- a shape-valid but semantically unsupported clarification to remain a scorer shape pass while being flagged for human adequacy review.

No scorer code, Gold, official score, or Agent logic is changed.
""".encode("utf-8")


def human_queue_md(data: dict) -> bytes:
    annotations = {item["id"]: item for item in data["annotations"]["cases"]}
    cases = []
    for case_id in sorted(annotations):
        note = annotations[case_id]
        if note["human"] != "YES":
            continue
        case = data["cases"][case_id]
        row = data["observations"][case_id]
        if case_id in {"B40-001", "B40-004"}:
            question = "Confirm the DATE→UTC month-boundary equivalence and SQL semantics independently; do not use non-UTC or non-boundary normalization."
        elif case_id in {"B40-003", "B40-022"}:
            question = "Confirm expression/grain equivalence for business rows, then separately decide whether each undeclared extra alias is safe under policy."
        elif case_id == "B40-011":
            question = "Confirm source metric, DESC, product_id ASC and TOP 5; record that no execution/result exists."
        elif case_id == "B40-012":
            question = "Does 'xếp hạng ... theo số đơn hàng' unambiguously mean highest-first, or should this be a clarification case?"
        elif case_id == "B40-033":
            question = "Recover the exact statement behind the approved repository event. Was it only a latest-snapshot availability lookup?"
        elif case_id in {"B40-036", "B40-037", "B40-038"}:
            question = "Is this response semantically safe and useful, given absent fields/formulas? The v3.3 score checks shape only."
        elif case_id == "B40-013":
            question = "Does use of current products.segment violate the snapshot-stored segment contract despite equal returned values?"
        elif case_id in {"B40-021", "B40-023", "B40-025"}:
            question = "Confirm wrong source/grain and review each additional output column for safety; matching or partial values do not repair semantics."
        elif case_id == "B40-002":
            question = "Confirm the PostgreSQL DATE subtraction/type failure and whether the bounded repair remained invalid; do not infer an infrastructure outage."
        elif case_id == "B40-014":
            question = "Confirm that shipment delivery_date is not a substitute for delivered order_status/order_date; no result was executed."
        elif case_id == "B40-015":
            question = "The candidate pool includes commerce.orders/order_items/products but final_selected_tables is null. Which component failed to select a final set, and why did the clarification claim orders was absent?"
        elif case_id == "B40-026":
            question = "Review inherited COGS/year context and the malformed bounded clarification response."
        elif case_id == "B40-030":
            question = "Confirm inherited 2025-10-31 snapshot versus observed 2024-11-21 parameter; classify executed_empty as wrong-scope execution."
        elif case_id in {"B40-032", "B40-034", "B40-035"}:
            question = "Is the clarification semantically complete and schema-grounded, or does it omit a material ambiguity/unavailable dimension?"
        elif case_id == "B40-040":
            question = "Confirm malformed clarification is a failed user-facing abstention, not a valid abstain, despite no SQL execution."
        elif case_id.startswith("B40-02") and case_id != "B40-026":
            question = "Independently verify the linked SQL semantic audit against the frozen metric/population/grain and retain the result audit separately."
        elif row.get("sql"):
            question = "Independently verify the saved AI-assisted SQL semantic decision against the frozen case contract; the audit is unauthenticated."
        else:
            question = "Review whether the saved clarification/refusal resolves the expected ambiguity without suggesting unavailable data or metrics."
        cases.append((case_id, case["question"], note["confidence"], note["evidence"], question))

    lines = [
        "# Human review queue",
        "",
        "This queue is not evidence that review has happened. Existing semantic/output decisions are AI-assisted and unauthenticated. The case-review provenance in the freeze is owner-reported; original clicks/signatures are unavailable.",
        "",
        "## Priority 1 — scorer false negatives and validator decisions",
        "",
        "| Case | Question | Confidence of current analysis | Evidence to review | Reviewer question |",
        "|---|---|---|---|---|",
    ]
    high = {"B40-001", "B40-002", "B40-003", "B40-004", "B40-011", "B40-012", "B40-013", "B40-021", "B40-022", "B40-023", "B40-025", "B40-033"}
    for row in cases:
        if row[0] in high:
            lines.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in row) + " |")
    lines.extend(["", "## Priority 2 — Agent SQL/clarification and context failures", "",
                  "| Case | Question | Confidence of current analysis | Evidence to review | Reviewer question |",
                  "|---|---|---|---|---|"])
    for row in cases:
        if row[0] not in high:
            lines.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in row) + " |")
    lines.extend([
        "", "## Review rules", "",
        "- Keep the saved SQL, raw output and v3.3 decision visible; do not overwrite the original audit files.",
        "- Review SQL semantics independently from row-result equality, strict output schema, extra-column safety, and execution success.",
        "- Do not promote B40-011 to E2E PASS without an authorized execution and result comparison.",
        "- Do not normalize ambiguous timestamp zones or approve aliases by name alone.",
        "- Record reviewer identity/provenance according to the project process; this report fabricates no identities, timestamps, or decisions.",
        "",
    ])
    return ("\n".join(lines)).encode("utf-8")


def reproducibility_manifest(data: dict, checks: list[dict], output_payloads: dict[str, bytes], ranking: dict,
                            row_checks: list[dict], repairs: dict) -> bytes:
    input_paths = [
        MANIFEST_PATH, BENCH_DIR / "ADJUDICATION_V3_1_CONSENSUS_20261122.json",
        CASE_PATH, GOLD_SQL_PATH, GOLD_PATH, SCORER_PATH, PROTOCOL_PATH,
        RUN_DATA_PATH, SCORES_PATH, RUN_DIR / "report.md", AUDIT_NOTES_PATH,
        SEMANTIC_AUDITS_PATH, OUTPUT_AUDITS_PATH,
        RUN_DIR / "semantic_audit_decisions.json", RUN_DIR / "output_safety_decisions.json",
    ]
    source_hashes = {path.relative_to(REPO_ROOT).as_posix(): sha256_file(path) for path in input_paths}
    analysis_hashes = {
        "artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/analyze.py": sha256_file(ANALYSIS_DIR / "analyze.py"),
        "artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/case_annotations.json": sha256_file(ANNOTATION_PATH),
        "artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/tests/test_analysis.py": sha256_file(ANALYSIS_DIR / "tests/test_analysis.py"),
    }
    result = {
        "format_version": "sql-post-benchmark-reproducibility-manifest.v1",
        "analysis_id": "post-benchmark-analysis-v1",
        "official_run_id": data["run_doc"]["manifest"]["experiment_id"],
        "official_scorer_version": data["scores"]["scorer_version"],
        "repository_base_revision": data["run_doc"]["manifest"]["application_revision"],
        "analysis_branch_base_revision": "a2f57e67e45b965cda4e901d3e2647861655e4c5",
        "official_files_modified": False,
        "database_connection_made": False,
        "sql_queries_executed_by_analysis": 0,
        "sql_agent_or_llm_invocations": 0,
        "network_calls": 0,
        "python_version": platform.python_version(),
        "reproduction_commands": [
            "uv run --locked --project . python artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/analyze.py",
            "uv run --locked --project . python -m unittest discover -s artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/tests -v",
            "uv run --locked --project . python artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/analyze.py --check",
        ],
        "evidence_checks": checks,
        "source_sha256": source_hashes,
        "analysis_source_sha256": analysis_hashes,
        "generated_analysis_sha256": {name: sha256_bytes(value) for name, value in sorted(output_payloads.items())},
        "diagnostic_findings": {
            "date_alias_result_checks": row_checks,
            "b40_011_direct_ranking_ast_check": ranking,
            "repair_recovery": repairs,
        },
        "hash_scope_note": "The manifest does not hash itself. Generated-analysis hashes cover the five deliverables; source hashes pin all inputs and scripts/tests.",
    }
    return (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def build_outputs() -> dict[str, bytes]:
    data = load_evidence()
    checks = validate_evidence(data)
    row_checks = date_and_alias_checks(data)
    b011 = data["observations"]["B40-011"].get("sql") or ""
    ranking = verify_b011_ranking_sql(b011)
    repairs = repair_analysis(data)
    unsupported_shape_count = sum(
        _valid_unsupported_shape(data["cases"][case_id], observation)
        for case_id, observation in data["observations"].items()
    )
    if unsupported_shape_count != data["scores"]["metrics"]["valid_clarification_abstention"]["numerator"]:
        raise ValueError("Local no-query/response-shape reproduction differs from official unsupported numerator")
    raw_passes = sum(record["decision"] == "PASS" for record in data["semantic_audits"]["records"])
    if len(data["semantic_audits"]["records"]) != 23 or raw_passes != 15:
        raise ValueError("Unexpected semantic audit counts; inspect before analysis")
    payloads = {
        "ERROR_ANALYSIS_REPORT.md": report_md(data, checks, row_checks, ranking, repairs),
        "CASE_ERROR_MATRIX.csv": case_matrix_csv(data, row_checks),
        "SCORER_FAIRNESS_AUDIT.md": fairness_md(data, row_checks, ranking),
        "SENSITIVITY_ANALYSIS.json": (json.dumps(
            sensitivity(data, row_checks, ranking, repairs), ensure_ascii=False, sort_keys=True, indent=2,
        ) + "\n").encode("utf-8"),
        "HUMAN_REVIEW_QUEUE.md": human_queue_md(data),
    }
    manifest = reproducibility_manifest(data, checks, payloads, ranking, row_checks, repairs)
    payloads["REPRODUCIBILITY_MANIFEST.json"] = manifest
    return payloads


def matches_generated_artifact(name: str, committed: bytes, generated: bytes) -> bool:
    """Allow runtime-version provenance to differ, never analytical output or hashes."""
    if committed == generated:
        return True
    if name != "REPRODUCIBILITY_MANIFEST.json":
        return False
    try:
        recorded = json.loads(committed)
        current = json.loads(generated)
        version = recorded["python_version"]
        if not isinstance(version, str):
            return False
        parts = version.split(".")
        if len(parts) != 3 or not all(part.isascii() and part.isdecimal() for part in parts):
            return False
        current["python_version"] = version
        canonical = (json.dumps(current, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        return committed == canonical
    except (ValueError, TypeError, KeyError, UnicodeError):
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify inputs and compare outputs without writing")
    args = parser.parse_args(argv)
    outputs = build_outputs()
    failures = []
    for name, payload in outputs.items():
        target = ANALYSIS_DIR / name
        if args.check:
            if not target.is_file() or not matches_generated_artifact(name, target.read_bytes(), payload):
                failures.append(name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    if failures:
        print("FAIL: generated artifacts differ: " + ", ".join(failures), file=sys.stderr)
        return 1
    print(f"PASS: evidence verified; {'checked' if args.check else 'wrote'} {len(outputs)} analysis artifacts; no live SQL/LLM/DB calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
