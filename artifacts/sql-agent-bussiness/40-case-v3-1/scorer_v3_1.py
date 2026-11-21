"""Versioned v3.2 scorer requiring linked independent semantic audits."""

from __future__ import annotations

import copy
import importlib.util
from decimal import Decimal, InvalidOperation
import math
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

SCORER_VERSION = "3.2.0"
PROTOCOL_VERSION = "3.2.0"


def _rate(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
        "status": "MEASURABLE" if denominator else "NOT MEASURABLE",
    }


def _fold(value: str) -> str:
    return value.strip().casefold()


def _decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (int, float, str)):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return number if number.is_finite() else None
    return None


def _value_matches(column, expected, actual, *, tolerance, exact=False):
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if expected is None or actual is None:
        return expected is None and actual is None
    if column in tolerance["exact_columns"] and (
        isinstance(expected, str) or isinstance(actual, str)
    ):
        return type(expected) is type(actual) and expected == actual
    expected_number, actual_number = _decimal(expected), _decimal(actual)
    if expected_number is None or actual_number is None:
        return type(expected) is type(actual) and expected == actual
    if exact:
        return expected_number == actual_number
    if column in tolerance["exact_columns"]:
        return expected_number == actual_number
    allowed = max(
        tolerance["absolute"],
        abs(expected_number) * tolerance["relative"],
    )
    return abs(expected_number - actual_number) <= allowed


def _numeric_tolerance(case):
    config = case.get("numeric_tolerance") or {}
    if not isinstance(config, dict):
        return None
    try:
        absolute_value = config.get("absolute", 0)
        relative_value = config.get("relative", 0)
        if isinstance(absolute_value, bool) or isinstance(relative_value, bool):
            return None
        absolute = Decimal(str(absolute_value))
        relative = Decimal(str(relative_value))
    except (InvalidOperation, ValueError):
        return None
    if not absolute.is_finite() or not relative.is_finite() or absolute < 0 or relative < 0:
        return None
    keys = case.get("business_key_columns", [])
    if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
        return None
    exact_columns = set(keys)
    for column in case.get("output_contract", {}).get("columns", []):
        name = _fold(column)
        if name.endswith("_id") or name == "id" or name.endswith("_count"):
            exact_columns.add(column)
    return {"absolute": absolute, "relative": relative, "exact_columns": exact_columns}


def _normalise_row(row):
    if not isinstance(row, dict):
        return None
    result = {}
    for key, value in row.items():
        if not isinstance(key, str):
            return None
        folded = _fold(key)
        if folded in result:
            return None
        result[folded] = value
    return result


def _multiset_row_matches(expected_rows, actual_rows, row_matches):
    """Maximum bipartite matching preserves duplicate rows and tolerances."""
    candidates = [
        [index for index, actual in enumerate(actual_rows) if row_matches(expected, actual)]
        for expected in expected_rows
    ]
    order = sorted(range(len(expected_rows)), key=lambda index: len(candidates[index]))
    actual_to_expected = {}

    def assign(expected_index, seen):
        for actual_index in candidates[expected_index]:
            if actual_index in seen:
                continue
            seen.add(actual_index)
            previous = actual_to_expected.get(actual_index)
            if previous is None or assign(previous, seen):
                actual_to_expected[actual_index] = expected_index
                return True
        return False

    for expected_index in order:
        assign(expected_index, set())
    matched = len(actual_to_expected)
    return matched, actual_to_expected


def compare_business_results(case, reference_rows, observation, *, reference_sql=None):
    """Compare canonical business rows separately from output-contract shape.

    Column order is ignored. Only exact names, case-approved aliases, and
    SQLGlot-proven identical projection expressions can map to a required
    column. Business accuracy is order-independent; ordered cases are checked
    separately as part of output-contract compliance.
    """
    contract = case.get("output_contract") or {}
    expected_columns = contract.get("columns")
    if not isinstance(expected_columns, list) or not expected_columns or any(
        not isinstance(column, str) or not column.strip() for column in expected_columns
    ):
        return {
            "business_result_decision": "REVIEW_REQUIRED",
            "output_contract_decision": "REVIEW_REQUIRED",
            "business_result_reason_codes": ["invalid_case_output_contract"],
            "output_contract_reason_codes": ["invalid_case_output_contract"],
            "business_rows_match": False,
            "business_schema_match": False,
            "strict_schema_match": False,
            "strict_rows_match": False,
            "row_matching": {"mode": "unavailable"},
        }
    expected_by_fold = {_fold(column): column for column in expected_columns}
    if len(expected_by_fold) != len(expected_columns):
        return {
            "business_result_decision": "REVIEW_REQUIRED",
            "output_contract_decision": "REVIEW_REQUIRED",
            "business_result_reason_codes": ["case_columns_not_unique"],
            "output_contract_reason_codes": ["case_columns_not_unique"],
            "business_rows_match": False,
            "business_schema_match": False,
            "strict_schema_match": False,
            "strict_rows_match": False,
            "row_matching": {"mode": "unavailable"},
        }

    observed_rows = observation.get("rows")
    if not isinstance(observed_rows, list):
        observed_rows = None
    actual_columns = observation.get("columns")
    if not isinstance(actual_columns, list) and isinstance(observed_rows, list):
        actual_columns = list(observed_rows[0]) if observed_rows and isinstance(observed_rows[0], dict) else []
    if not isinstance(actual_columns, list) or not actual_columns or any(
        not isinstance(column, str) or not column.strip() for column in actual_columns
    ):
        return {
            "business_result_decision": "REVIEW_REQUIRED",
            "output_contract_decision": "REVIEW_REQUIRED",
            "business_result_reason_codes": ["observed_columns_missing_or_invalid"],
            "output_contract_reason_codes": ["observed_columns_missing_or_invalid"],
            "business_rows_match": False,
            "business_schema_match": False,
            "strict_schema_match": False,
            "strict_rows_match": False,
            "row_matching": {"mode": "unavailable"},
        }
    if observed_rows is None:
        return {
            "business_result_decision": "REVIEW_REQUIRED",
            "output_contract_decision": "REVIEW_REQUIRED",
            "business_result_reason_codes": ["observed_rows_missing_or_invalid"],
            "output_contract_reason_codes": ["observed_rows_missing_or_invalid"],
            "business_rows_match": False,
            "business_schema_match": False,
            "strict_schema_match": False,
            "strict_rows_match": False,
            "row_matching": {"mode": "unavailable"},
        }

    mapping_ambiguities = []
    row_ambiguities = []
    business_ambiguities = []
    output_ambiguities = []
    business_reason_codes = []
    output_reason_codes = []
    actual_folds = [_fold(column) for column in actual_columns]
    if len(set(actual_folds)) != len(actual_folds):
        mapping_ambiguities.append("duplicate_observed_column_name")

    alias_index = {}
    aliases = case.get("column_aliases", {})
    if not isinstance(aliases, dict):
        aliases = {}
        mapping_ambiguities.append("invalid_alias_contract")
    for canonical, values in aliases.items():
        if canonical not in expected_columns or not isinstance(values, list):
            mapping_ambiguities.append("invalid_alias_contract")
            continue
        for alias in values:
            if isinstance(alias, str) and alias.strip():
                folded = _fold(alias)
                if folded in expected_by_fold and expected_by_fold[folded] != canonical:
                    mapping_ambiguities.append("alias_collides_with_required_column")
                alias_index.setdefault(folded, set()).add(canonical)
            else:
                mapping_ambiguities.append("invalid_alias_contract")

    lineage_candidates = [set() for _ in actual_columns]
    actual_sql = observation.get("sql")
    if isinstance(reference_sql, str) and isinstance(actual_sql, str):
        expected_signatures = _audit.projection_signatures(reference_sql)
        actual_signatures = _audit.projection_signatures(actual_sql)
        if expected_signatures is not None and actual_signatures is not None and len(actual_signatures) == len(actual_columns):
            expected_by_signature = {}
            for alias, signature in expected_signatures:
                canonical = expected_by_fold.get(_fold(alias))
                if canonical is not None and signature is not None:
                    expected_by_signature.setdefault(signature, set()).add(canonical)
            for index, (_, signature) in enumerate(actual_signatures):
                if signature is not None:
                    lineage_candidates[index] = expected_by_signature.get(signature, set())

    actual_to_canonical = {}
    extras = []
    for index, (column, folded) in enumerate(zip(actual_columns, actual_folds)):
        if folded in expected_by_fold:
            actual_to_canonical[index] = expected_by_fold[folded]
            continue
        approved = alias_index.get(folded, set())
        if len(approved) == 1:
            actual_to_canonical[index] = next(iter(approved))
            continue
        if len(approved) > 1:
            mapping_ambiguities.append("ambiguous_approved_alias")
            continue
        lineage = lineage_candidates[index] if index < len(lineage_candidates) else set()
        if len(lineage) == 1:
            actual_to_canonical[index] = next(iter(lineage))
        elif len(lineage) > 1:
            mapping_ambiguities.append("ambiguous_sql_projection_lineage")
        else:
            extras.append(column)

    canonical_sources = {}
    for index, canonical in actual_to_canonical.items():
        canonical_sources.setdefault(canonical, []).append(index)
    duplicate_required = [column for column, indices in canonical_sources.items() if len(indices) > 1]
    if duplicate_required:
        mapping_ambiguities.append("duplicate_mapping_to_required_column")
    missing_columns = [column for column in expected_columns if column not in canonical_sources]

    actual_row_maps = [_normalise_row(row) for row in observed_rows]
    if any(row is None for row in actual_row_maps):
        row_ambiguities.append("malformed_observed_row")
    missing_declared_cells = []
    row_extra_names = {}
    actual_column_folds = set(actual_folds)
    for index, row in enumerate(actual_row_maps):
        if row is None:
            continue
        missing_declared_cells.extend(
            {"row": index, "column": actual_columns[column_index]}
            for column_index, folded in enumerate(actual_folds)
            if folded not in row
        )
        for key in row:
            if key not in actual_column_folds:
                row_extra_names.setdefault(key, key)
    if missing_declared_cells:
        row_ambiguities.append("row_missing_declared_column")

    if missing_columns:
        business_reason_codes.append("missing_required_columns")
        output_reason_codes.append("missing_required_columns")
    if duplicate_required:
        output_reason_codes.append("duplicate_required_columns")

    provenance = case.get("allowed_provenance_columns", {})
    if not isinstance(provenance, dict):
        provenance = {}
        output_ambiguities.append("invalid_provenance_policy")
    provenance_by_fold = {}
    for name, value in provenance.items():
        if not isinstance(name, str) or not name.strip():
            output_ambiguities.append("invalid_provenance_policy")
            continue
        folded = _fold(name)
        if folded in provenance_by_fold:
            output_ambiguities.append("duplicate_provenance_column")
        provenance_by_fold[folded] = (name, value)
    unexpected_extras = [column for column in extras if _fold(column) not in provenance_by_fold]
    unexpected_extras.extend(
        name for name in row_extra_names.values() if _fold(name) not in provenance_by_fold
    )
    provenance_mismatches = []
    for row_index, row in enumerate(actual_row_maps):
        if row is None:
            continue
        for column in extras:
            policy = provenance_by_fold.get(_fold(column))
            if policy is not None and row.get(_fold(column)) != policy[1]:
                provenance_mismatches.append({"row": row_index, "column": column})
        for folded, original in row_extra_names.items():
            policy = provenance_by_fold.get(folded)
            if policy is not None and row.get(folded) != policy[1]:
                provenance_mismatches.append({"row": row_index, "column": original})
    if unexpected_extras:
        output_reason_codes.append("unexpected_extra_columns")
    if provenance_mismatches:
        output_reason_codes.append("provenance_value_mismatch")

    tolerance = _numeric_tolerance(case)
    if tolerance is None:
        business_ambiguities.append("invalid_numeric_tolerance")

    canonical_actual = []
    if not mapping_ambiguities and not row_ambiguities and not missing_columns:
        for row in actual_row_maps:
            canonical_actual.append(tuple(
                row.get(actual_folds[canonical_sources[column][0]])
                for column in expected_columns
            ))
    canonical_expected = []
    reference_shape_invalid = not isinstance(reference_rows, list)
    for row in reference_rows if isinstance(reference_rows, list) else []:
        normal = _normalise_row(row)
        if normal is None or any(_fold(column) not in normal for column in expected_columns):
            reference_shape_invalid = True
            break
        canonical_expected.append(tuple(normal[_fold(column)] for column in expected_columns))
    if reference_shape_invalid:
        business_ambiguities.append("invalid_reference_row_shape")

    keys = case.get("business_key_columns") or []
    if not isinstance(keys, list) or any(key not in expected_columns for key in keys):
        business_ambiguities.append("invalid_business_key_contract")
        output_ambiguities.append("invalid_business_key_contract")
        keys = []
    row_matching = {
        "mode": "business_key" if keys else "multiset",
        "expected_rows": len(canonical_expected),
        "actual_rows": len(canonical_actual),
        "matched_rows": 0,
        "missing_rows": len(canonical_expected),
        "extra_rows": len(canonical_actual),
        "mismatched_row_indexes": [],
    }
    rows_match = False
    if (
        not mapping_ambiguities and not row_ambiguities and not business_ambiguities
        and not missing_columns and tolerance is not None
    ):
        def row_matches(left, right, *, exact=False):
            return all(
                _value_matches(column, expected, actual, tolerance=tolerance, exact=exact)
                for column, expected, actual in zip(expected_columns, left, right)
            )

        if keys:
            def key_token(row):
                values = tuple(row[expected_columns.index(column)] for column in keys)
                if any(value is None or isinstance(value, (dict, list)) for value in values):
                    return None
                return tuple((type(value).__name__, str(value)) for value in values)

            def keyed(rows):
                indexed = {}
                for row in rows:
                    key = key_token(row)
                    if key is None or key in indexed:
                        return None
                    indexed[key] = row
                return indexed

            expected_by_key = keyed(canonical_expected)
            actual_by_key = keyed(canonical_actual)
            if expected_by_key is None:
                business_ambiguities.append("reference_business_key_null_or_duplicate")
            elif actual_by_key is None:
                business_reason_codes.append("actual_business_key_null_or_duplicate")
                output_reason_codes.append("business_key_uniqueness_violation")
            else:
                common = set(expected_by_key) & set(actual_by_key)
                matched_keys = {
                    key for key in common if row_matches(expected_by_key[key], actual_by_key[key])
                }
                row_matching["matched_rows"] = len(matched_keys)
                row_matching["missing_rows"] = len(set(expected_by_key) - matched_keys)
                row_matching["extra_rows"] = len(set(actual_by_key) - matched_keys)
                rows_match = (
                    len(expected_by_key) == len(actual_by_key)
                    and len(matched_keys) == len(expected_by_key)
                )
        else:
            matched, _ = _multiset_row_matches(
                canonical_expected, canonical_actual, row_matches,
            )
            row_matching["matched_rows"] = matched
            row_matching["missing_rows"] = len(canonical_expected) - matched
            row_matching["extra_rows"] = len(canonical_actual) - matched
            rows_match = len(canonical_expected) == len(canonical_actual) == matched

        if not rows_match and "actual_business_key_null_or_duplicate" not in business_reason_codes:
            business_reason_codes.append("business_result_rows_mismatch")
        if row_matching["missing_rows"]:
            business_reason_codes.append("missing_or_mismatched_result_rows")
        if row_matching["extra_rows"]:
            business_reason_codes.append("extra_or_mismatched_result_rows")
        if len(canonical_expected) != len(canonical_actual):
            business_reason_codes.append("result_row_count_mismatch")

    business_reason_codes = list(dict.fromkeys(business_reason_codes))
    max_rows = contract.get("max_rows")
    if max_rows is not None and (
        isinstance(max_rows, bool) or not isinstance(max_rows, int) or max_rows < 0
    ):
        output_ambiguities.append("invalid_max_rows_contract")
    elif max_rows is not None and len(actual_row_maps) > max_rows:
        output_reason_codes.append("max_rows_exceeded")
    top_n = case.get("top_n")
    if isinstance(top_n, int) and not isinstance(top_n, bool) and top_n > 0 and len(actual_row_maps) > top_n:
        output_reason_codes.append("top_n_rows_exceeded")

    order_matches = None
    if contract.get("ordered"):
        if rows_match and not mapping_ambiguities and not row_ambiguities and not missing_columns:
            order_matches = (
                len(canonical_expected) == len(canonical_actual)
                and all(
                    _value_matches(column, expected, actual, tolerance=tolerance)
                    for expected_row, actual_row in zip(canonical_expected, canonical_actual)
                    for column, expected, actual in zip(expected_columns, expected_row, actual_row)
                )
            )
            if not order_matches:
                output_reason_codes.append("ordered_output_mismatch")
        else:
            output_ambiguities.append("ordered_output_unverifiable_due_to_business_result_mismatch")

    if mapping_ambiguities or row_ambiguities or business_ambiguities:
        business_decision = "REVIEW_REQUIRED"
    else:
        business_decision = "PASS" if rows_match and not missing_columns else "FAIL"
    if mapping_ambiguities or row_ambiguities or output_ambiguities:
        output_decision = "REVIEW_REQUIRED"
    else:
        output_decision = "FAIL" if output_reason_codes else "PASS"
    if contract.get("ordered") and order_matches is False:
        output_decision = "FAIL"

    strict_schema = actual_columns == expected_columns
    strict_rows = False
    if not mapping_ambiguities and not row_ambiguities and not business_ambiguities and not missing_columns and strict_schema:
        exact = {**tolerance, "absolute": Decimal(0), "relative": Decimal(0)} if tolerance else None
        strict_rows = bool(exact) and len(canonical_expected) == len(canonical_actual)
        if strict_rows:
            cmp = lambda left, right: row_matches(left, right, exact=True)
            if contract.get("ordered"):
                strict_rows = all(cmp(left, right) for left, right in zip(canonical_expected, canonical_actual))
            else:
                count, _ = _multiset_row_matches(canonical_expected, canonical_actual, cmp)
                strict_rows = count == len(canonical_expected)

    return {
        "business_result_decision": business_decision,
        "output_contract_decision": output_decision,
        "business_result_reason_codes": list(dict.fromkeys([
            *mapping_ambiguities, *row_ambiguities, *business_ambiguities,
            *business_reason_codes,
        ])),
        "output_contract_reason_codes": list(dict.fromkeys([
            *mapping_ambiguities, *row_ambiguities, *output_ambiguities,
            *output_reason_codes,
        ])),
        "business_rows_match": business_decision == "PASS",
        "business_schema_match": not missing_columns and not mapping_ambiguities,
        "strict_schema_match": strict_schema,
        "strict_rows_match": strict_rows,
        "missing_columns": missing_columns,
        "duplicate_required_columns": duplicate_required,
        "extra_columns": extras,
        "unexpected_extra_columns": unexpected_extras,
        "provenance_mismatches": provenance_mismatches,
        "canonical_column_mapping": {
            actual_columns[index]: canonical for index, canonical in actual_to_canonical.items()
        },
        "row_matching": row_matching,
        "ordered": bool(contract.get("ordered")),
        "ordered_rows_match": order_matches,
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
    unsupported_attempted = {
        case_id for case_id, observation in observations.items()
        if cases.get(case_id, {}).get("expected_behavior") != "execute"
        and _base._attempted(observation)
    }
    decisions = {
        case_id: audit_evaluations.get(case_id, {}).get("decision", "INDETERMINATE")
        for case_id in supported_attempted
    }
    passed = sum(decision == "PASS" for decision in decisions.values())
    failed = sum(decision == "FAIL" for decision in decisions.values())
    determinate = passed + failed
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
    references = {case["id"]: case for case in reference_doc.get("cases", [])}
    comparisons = {}
    for case_id in sorted(supported_attempted):
        reference = references.get(case_id)
        comparison = compare_business_results(
            cases[case_id],
            reference.get("rows") if reference is not None else None,
            observations[case_id],
            reference_sql=reference.get("sql") if reference is not None else None,
        )
        comparison["semantic_audit_decision"] = decisions.get(case_id, "INDETERMINATE")
        comparisons[case_id] = comparison

    executed_supported = {
        case_id for case_id in supported_attempted if _base._executed(observations[case_id])
    }
    business_pass = {
        case_id for case_id in executed_supported
        if comparisons[case_id]["business_result_decision"] == "PASS"
    }
    contract_pass = {
        case_id for case_id in executed_supported
        if comparisons[case_id]["output_contract_decision"] == "PASS"
    }
    end_to_end = {
        case_id for case_id in executed_supported
        if decisions.get(case_id) == "PASS"
        and comparisons[case_id]["business_result_decision"] == "PASS"
        and comparisons[case_id]["output_contract_decision"] == "PASS"
    }
    unsupported_successes = result["metrics"]["valid_clarification_abstention"]["numerator"]
    result["case_comparisons"] = comparisons
    result["metrics"]["business_result_accuracy"] = _rate(
        len(business_pass), len(executed_supported),
    )
    result["metrics"]["output_contract_compliance"] = _rate(
        len(contract_pass), len(executed_supported),
    )
    result["metrics"]["business_result_review_required"] = {
        "count": sum(
            comparisons[cid]["business_result_decision"] == "REVIEW_REQUIRED"
            for cid in executed_supported
        ),
        "denominator": len(executed_supported),
    }
    result["metrics"]["output_contract_review_required"] = {
        "count": sum(
            comparisons[cid]["output_contract_decision"] == "REVIEW_REQUIRED"
            for cid in executed_supported
        ),
        "denominator": len(executed_supported),
    }
    result["metrics"]["supported_business_end_to_end_accuracy"] = _rate(
        len(end_to_end), len(supported_attempted),
    )
    result["metrics"]["overall_task_success_rate"] = _rate(
        len(end_to_end) + unsupported_successes,
        len(supported_attempted) + len(unsupported_attempted),
    )
    result["format_version"] = "sql-agent-business-scores.v3.2"
    result["protocol_version"] = PROTOCOL_VERSION
    result["scorer_version"] = SCORER_VERSION
    result["result_comparison_policy"] = {
        "column_position_is_ignored": True,
        "approved_aliases_are_accepted": True,
        "projection_lineage_requires_identical_resolved_expression": True,
        "fuzzy_column_mapping": False,
        "extra_columns_affect_business_result_accuracy": False,
        "extra_columns_affect_output_contract_compliance": True,
        "unordered_rows_use_duplicate_preserving_multiset_matching": True,
        "ordered_rows_require_position_match": True,
        "business_end_to_end_requires_output_contract_compliance": True,
    }
    return result
