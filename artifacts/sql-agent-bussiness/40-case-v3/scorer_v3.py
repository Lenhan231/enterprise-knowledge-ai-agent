"""Versioned SQL-agent business scorer for the v3 case contract."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import math
from typing import Any


SCORER_VERSION = "3.1.0"
PROTOCOL_VERSION = "3.1.0"
NOT_RUN = {"NOT RUN", "NOT_RUN", "PENDING", "NOT_STARTED"}
EXECUTED = {"executed", "executed_empty"}
CLARIFY_OR_ABSTAIN = {
    "clarification_required",
    "clarified",
    "unsupported",
    "abstained",
    "rejected",
}
VALIDATION_ERRORS = {
    "SQLValidationError",
    "SQLSecurityError",
    "SQLSchemaMismatchError",
    "MetricDefinitionError",
    "SQLJoinValidationError",
}
PROVIDER_ERRORS = {
    "ProviderError",
    "ProviderUnavailable",
    "ProviderTimeout",
    "NetworkError",
    "TimeoutError",
    "ConnectionError",
}


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    return None


def _is_exact_column(column: str, expected: Any, actual: Any) -> bool:
    name = column.casefold()
    if "id" in name or "count" in name:
        return True
    return isinstance(expected, int) and not isinstance(expected, bool) and isinstance(actual, int)


def _value_matches(column: str, expected: Any, actual: Any, *, tolerance: dict, strict: bool) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if expected == actual:
        return True
    expected_num = _decimal(expected)
    actual_num = _decimal(actual)
    if expected_num is None or actual_num is None:
        return False
    if strict or _is_exact_column(column, expected, actual):
        return expected_num == actual_num
    absolute = Decimal(str(tolerance.get("absolute", 0)))
    relative = Decimal(str(tolerance.get("relative", 0)))
    allowed = max(absolute, abs(expected_num) * relative)
    return abs(actual_num - expected_num) <= allowed


def _row_multiset(rows: list[tuple]) -> Counter:
    def normalize(value):
        if isinstance(value, dict):
            return tuple(sorted((key, normalize(child)) for key, child in value.items()))
        if isinstance(value, list):
            return tuple(normalize(child) for child in value)
        if isinstance(value, Decimal):
            return ("decimal", str(value.normalize()))
        return (type(value).__name__, value)
    return Counter(normalize(row) for row in rows)


def compare_business_results(case: dict, reference_rows: list[dict], observation: dict) -> dict:
    """Compare required business fields, tolerances, NULLs, order and allowed extras."""
    expected_columns = list(case.get("output_contract", {}).get("columns", []))
    observed_rows = observation.get("rows")
    observed_rows = observed_rows if isinstance(observed_rows, list) else []
    actual_columns = observation.get("columns")
    if not isinstance(actual_columns, list):
        actual_columns = list(observed_rows[0]) if observed_rows else []
    aliases = case.get("column_aliases", {})
    provenance = case.get("allowed_provenance_columns", {})
    alias_to_canonical = {}
    for canonical in expected_columns:
        alias_to_canonical[canonical.casefold()] = canonical
        for alias in aliases.get(canonical, []):
            alias_to_canonical[str(alias).casefold()] = canonical
    actual_to_canonical = {
        str(column).casefold(): alias_to_canonical.get(str(column).casefold(), str(column))
        for column in actual_columns
    }
    mapped_columns = list(actual_to_canonical.values())
    missing = [column for column in expected_columns if column not in mapped_columns]
    duplicate_required = [
        column for column in expected_columns if mapped_columns.count(column) > 1
    ]
    extras = [column for column in actual_columns if actual_to_canonical[str(column).casefold()] not in expected_columns]
    unexpected_extras = [column for column in extras if column not in provenance]
    provenance_mismatches = []
    for row_index, row in enumerate(observed_rows):
        for column in extras:
            if column in provenance and row.get(column) != provenance[column]:
                provenance_mismatches.append({"row": row_index, "column": column})
    schema_match = not missing and not duplicate_required and not unexpected_extras and not provenance_mismatches

    def canonical_rows(rows):
        result = []
        for row in rows:
            canonical = {}
            for actual, value in row.items():
                key = actual_to_canonical.get(str(actual).casefold(), str(actual))
                if key in expected_columns:
                    canonical[key] = value
            result.append(tuple(canonical.get(column) for column in expected_columns))
        return result

    expected = canonical_rows(reference_rows)
    actual = canonical_rows(observed_rows)
    tolerance = case.get("numeric_tolerance", {})
    ordered = bool(case.get("output_contract", {}).get("ordered"))
    pair_rows = zip(expected, actual) if ordered else zip(
        sorted(expected, key=repr), sorted(actual, key=repr)
    )
    values_match = len(expected) == len(actual) and all(
        all(_value_matches(column, left, right, tolerance=tolerance, strict=False)
            for column, left, right in zip(expected_columns, expected_row, actual_row))
        for expected_row, actual_row in pair_rows
    )
    business_match = schema_match and values_match

    strict_schema = actual_columns == expected_columns
    strict_expected = [tuple(row.get(column) for column in expected_columns) for row in reference_rows]
    strict_actual = [tuple(row.get(column) for column in expected_columns) for row in observed_rows]
    if not ordered:
        strict_expected.sort(key=repr)
        strict_actual.sort(key=repr)
    strict_rows = len(strict_expected) == len(strict_actual) and all(
        all(_value_matches(column, left, right, tolerance=tolerance, strict=True)
            for column, left, right in zip(expected_columns, expected_row, actual_row))
        for expected_row, actual_row in zip(strict_expected, strict_actual)
    )
    return {
        "business_rows_match": business_match,
        "business_schema_match": schema_match,
        "strict_schema_match": strict_schema,
        "strict_rows_match": strict_rows,
        "missing_columns": missing,
        "duplicate_required_columns": duplicate_required,
        "extra_columns": extras,
        "unexpected_extra_columns": unexpected_extras,
        "provenance_mismatches": provenance_mismatches,
        "ordered": ordered,
    }


def _attempted(observation: dict | None) -> bool:
    if not isinstance(observation, dict):
        return False
    status = str(observation.get("status", "")).upper()
    return bool(status) and status not in NOT_RUN


def _executed(observation: dict) -> bool:
    return str(observation.get("status", "")).casefold() in EXECUTED or observation.get("executed") is True


def _semantic_valid(observation: dict) -> bool:
    return observation.get("sql_semantic_valid") is True


def _valid_unsupported_response(observation: dict) -> bool:
    answer = observation.get("answer")
    metadata = observation.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        return False
    metadata = metadata or {}
    options = metadata.get("clarification_options", observation.get("clarification_options", []))
    if options is None:
        options = []
    events = observation.get("execution_events")
    no_execution_events = events is None or (isinstance(events, list) and not events)
    return (
        isinstance(answer, str)
        and bool(answer.strip())
        and isinstance(options, list)
        and len(options) <= 3
        and all(isinstance(option, str) and bool(option.strip()) for option in options)
        and not _executed(observation)
        and not observation.get("sql")
        and no_execution_events
        and not _provider_failure(observation)
    )


def _validation_blocked(observation: dict) -> bool:
    if observation.get("validation_blocked") is True:
        return True
    if observation.get("error_type") in VALIDATION_ERRORS:
        return True
    return str(observation.get("failure_class", "")).casefold() in {
        "validation", "security_validation", "schema_validation", "semantic_validation",
    }


def _provider_failure(observation: dict) -> bool:
    return observation.get("error_type") in PROVIDER_ERRORS or str(
        observation.get("failure_class", "")
    ).casefold() in {"provider", "network", "timeout"}


def _percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _sum_calls(observations: list[dict]) -> dict[str, int]:
    keys = {key for item in observations for key in (item.get("calls") or {})}
    return {key: sum(int((item.get("calls") or {}).get(key, 0) or 0) for item in observations)
            for key in sorted(keys)}


def _provider_call_summary(observations: list[dict]) -> dict[str, int]:
    calls = _sum_calls(observations)
    sql_generation = calls.get("general_sql_generation", 0)
    metric_interpretation = calls.get("metric_interpretation", 0)
    selector_requests = calls.get("schema_selector_attempts", calls.get("jev_attempts", 0))
    local_codex = calls.get("local_codex_fallback_calls", 0)
    return {
        "sql_generation_provider_submissions": sql_generation,
        "metric_interpretation_provider_submissions": metric_interpretation,
        "schema_selection_provider_requests": selector_requests,
        "local_codex_fallback_calls": local_codex,
        "total_model_calls": sql_generation + metric_interpretation + selector_requests + local_codex,
        "secondary_sql_provider_fallback_submissions": calls.get("provider_fallback_calls", 0),
    }


def _schema_selector_recall(cases: dict, observations: dict) -> dict[str, Any]:
    numerator = denominator = applicable = 0
    for case_id, observation in observations.items():
        case = cases.get(case_id, {})
        required = set(case.get("required_source_tables", []))
        selection = observation.get("schema_selection") or {}
        status = str(selection.get("schema_selector_status", selection.get("jev_status", ""))).casefold()
        method = str(selection.get("method", "")).casefold()
        successful = status in {"available", "success", "succeeded"} or (
            not status and method in {"decision_model_top_five", "jev_top_five"}
        )
        candidates = selection.get("raw_top5_candidates", selection.get("candidate_tables"))
        if not successful or not required or not isinstance(candidates, list):
            continue
        applicable += 1
        top_five = set(candidates[:5])
        numerator += len(required & top_five)
        denominator += len(required)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
        "applicable_cases": applicable,
        "status": "MEASURABLE" if applicable else "NOT MEASURABLE",
    }


def score(cases_doc: dict, reference_doc: dict, experiment_doc: dict) -> dict:
    cases = {case["id"]: case for case in cases_doc.get("cases", [])}
    references = {case["id"]: case for case in reference_doc.get("cases", [])}
    observations = {case["id"]: case for case in experiment_doc.get("cases", [])}
    supported = {
        case_id for case_id, case in cases.items() if case.get("expected_behavior") == "execute"
    }
    unsupported = set(cases) - supported
    attempted = {case_id for case_id, item in observations.items() if _attempted(item)}
    supported_attempted = supported & attempted
    unsupported_attempted = unsupported & attempted

    comparisons = {}
    for case_id in supported_attempted:
        reference = references.get(case_id, {})
        comparisons[case_id] = compare_business_results(
            cases[case_id], reference.get("rows", []), observations[case_id]
        )

    successful_semantic = {
        case_id for case_id in supported_attempted
        if _executed(observations[case_id]) and _semantic_valid(observations[case_id])
    }
    end_to_end = {
        case_id for case_id in successful_semantic
        if comparisons[case_id]["business_rows_match"]
    }
    executed_supported = {case_id for case_id in supported_attempted if _executed(observations[case_id])}
    valid_unsupported = {
        case_id for case_id in unsupported_attempted
        if str(observations[case_id].get("status", "")).casefold() in CLARIFY_OR_ABSTAIN
        and _valid_unsupported_response(observations[case_id])
    }
    false_clarification = {
        case_id for case_id in supported_attempted
        if str(observations[case_id].get("status", "")).casefold() in CLARIFY_OR_ABSTAIN
        and not _executed(observations[case_id])
    }
    validation_blocked = {
        case_id for case_id in supported_attempted if _validation_blocked(observations[case_id])
    }
    repaired = {
        case_id for case_id in supported_attempted
        if int(observations[case_id].get("repair_count", 0) or 0) > 0
        or bool(observations[case_id].get("repairs"))
    }
    repaired_success = end_to_end & repaired
    unsafe_execution_count = sum(
        int(observations[case_id].get("unsafe_execution_count", 0) or 0)
        for case_id in attempted
    )
    provider_failure_count = sum(
        1 for case_id in attempted if _provider_failure(observations[case_id])
    )
    attempted_observations = [observations[case_id] for case_id in sorted(attempted)]
    latency_values = [
        float(item["latency_ms"])
        for item in attempted_observations
        if isinstance(item.get("latency_ms"), (int, float))
        and not isinstance(item.get("latency_ms"), bool)
        and item["latency_ms"] >= 0
    ]

    strict_exact = {
        case_id for case_id in executed_supported
        if comparisons[case_id]["strict_schema_match"] and comparisons[case_id]["strict_rows_match"]
        and _semantic_valid(observations[case_id])
    }
    business_result_correct = {
        case_id for case_id in executed_supported if comparisons[case_id]["business_rows_match"]
    }
    overall_success = len(end_to_end) + len(valid_unsupported)
    overall_denominator = len(supported_attempted) + len(unsupported_attempted)
    return {
        "format_version": "sql-agent-business-scores.v3",
        "protocol_version": PROTOCOL_VERSION,
        "scorer_version": SCORER_VERSION,
        "heldout_agent_executed_by_scorer": False,
        "attempted_case_ids": sorted(attempted),
        "not_run_case_ids": sorted(set(cases) - attempted),
        "metrics": {
            "supported_business_end_to_end_accuracy": _rate(len(end_to_end), len(supported_attempted)),
            "sql_semantic_accuracy": _rate(
                sum(_semantic_valid(observations[cid]) for cid in supported_attempted),
                len(supported_attempted),
            ),
            "business_result_accuracy": _rate(len(business_result_correct), len(executed_supported)),
            "supported_execution_success": _rate(len(executed_supported), len(supported_attempted)),
            "valid_clarification_abstention": _rate(len(valid_unsupported), len(unsupported_attempted)),
            "false_clarification_abstention": _rate(
                len(false_clarification), len(supported_attempted)
            ),
            "supported_noncompletion": _rate(
                len(supported_attempted - successful_semantic), len(supported_attempted)
            ),
            "validation_blocked_supported": _rate(
                len(validation_blocked), len(supported_attempted)
            ),
            "repair_recovery": _rate(len(repaired_success), len(repaired)),
            "overall_task_success_rate": _rate(overall_success, overall_denominator),
            "strict_result_exact_match_optional": _rate(len(strict_exact), len(supported_attempted)),
            "unsafe_execution_count": {
                "count": unsafe_execution_count,
                "target": 0,
                "passed": unsafe_execution_count == 0,
            },
            "provider_network_failure_count": {
                "count": provider_failure_count,
                "interpret_as_semantic_refusal": False,
            },
            "schema_selector_raw_recall_at_5": _schema_selector_recall(cases, observations),
            "latency_ms": {
                "p50_nearest_rank": _percentile_nearest_rank(latency_values, 0.50),
                "p95_nearest_rank": _percentile_nearest_rank(latency_values, 0.95),
                "sample_count": len(latency_values),
                "denominator": len(attempted_observations),
            },
            "provider_calls": _provider_call_summary(attempted_observations),
            "pipeline_calls": _sum_calls(attempted_observations),
        },
        "applicability": {
            "supported_attempts": len(supported_attempted),
            "unsupported_attempts": len(unsupported_attempted),
            "executed_supported": len(executed_supported),
            "repaired_supported": len(repaired),
        },
        "case_comparisons": comparisons,
    }
