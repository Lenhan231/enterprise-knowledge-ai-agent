"""Deterministic structural checks for the draft SQL-agent holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from core.agents.sql.join_validation import PRIMARY_KEYS
from core.agents.sql.sql_validation import (
    APPROVED_COLUMNS,
    APPROVED_DATE_COLUMNS,
    APPROVED_JOINS,
    MAX_RESULT_ROWS,
    SQLValidationError,
    validate_commerce_sql,
)
from sqlglot import exp, parse


EXPECTED_CATEGORY_COUNTS = {
    "aggregation_time": 5,
    "filters_business_constraints": 5,
    "grouping_ranking": 5,
    "joins_cross_domain": 5,
    "inventory_null_semantics": 5,
    "sql_followup_context": 5,
    "genuine_clarification": 5,
    "unsupported_data_scope": 4,
    "security_scope": 1,
}
EXPECTED_BEHAVIOR_COUNTS = {
    "execute": 30,
    "clarify": 5,
    "abstain_without_query": 5,
}
EXPECTED_IDS = {f"B40-{index:03d}" for index in range(1, 41)}
PILOT_IDS = {"P01", "P02", "P03", "P04", "P05"}
PENDING_ORACLE = "PENDING_HUMAN_REVIEW"


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _join_edge(value: str):
    pieces = value.split("=")
    if len(pieces) != 2:
        return None
    endpoints = []
    for piece in pieces:
        match = re.fullmatch(r"\s*([\w.]+)\.([A-Za-z_][A-Za-z0-9_]*)\s*", piece)
        if not match:
            return None
        endpoints.append((match.group(1).casefold(), match.group(2).casefold()))
    return frozenset(endpoints)


def _date_predicates(tree, date_field: str, parameters: list):
    """Return bound comparisons applied to the declared date column."""
    table_name, column_name = date_field.casefold().rsplit(".", 1)
    aliases = {
        table.alias_or_name.casefold(): f"{table.db}.{table.name}".casefold()
        for table in tree.find_all(exp.Table)
    }

    def is_date_column(node):
        return (
            isinstance(node, exp.Column)
            and node.name.casefold() == column_name
            and node.table
            and aliases.get(node.table.casefold(), node.table.casefold()) == table_name
        )

    def bound_value(node):
        if isinstance(node, exp.Parameter):
            index = int(node.this.this)
            return parameters[index - 1] if 1 <= index <= len(parameters) else None
        if isinstance(node, exp.Literal) and node.is_string:
            return node.this
        return None

    operators = ((exp.EQ, "eq"), (exp.GTE, "gte"), (exp.GT, "gt"),
                 (exp.LTE, "lte"), (exp.LT, "lt"))
    reversed_operator = {"gte": "lte", "gt": "lt", "lte": "gte", "lt": "gt", "eq": "eq"}
    found = set()
    for expression_type, operator in operators:
        for comparison in tree.find_all(expression_type):
            left, right = comparison.this, comparison.expression
            if is_date_column(left):
                value = bound_value(right)
                if value is not None:
                    found.add((operator, str(value)))
            elif is_date_column(right):
                value = bound_value(left)
                if value is not None:
                    found.add((reversed_operator[operator], str(value)))
    return found


def _date_scope_error(tree, case: dict, parameters: list) -> str | None:
    scope = case.get("time_scope", {})
    kind = scope.get("kind")
    if kind == "all_records":
        return None
    date_field = scope.get("date_field")
    if not isinstance(date_field, str):
        return "date scope is missing its declared date field"
    actual = _date_predicates(tree, date_field, parameters)
    if kind in {"calendar_range", "followup_comparison"}:
        expected = {("gte", scope.get("start")), ("lt", scope.get("end_exclusive"))}
    elif kind == "snapshot_range":
        expected = {("gte", scope.get("start")), ("lte", scope.get("end_inclusive"))}
    elif kind in {"snapshot", "two_snapshot_comparison", "followup_snapshot"} or (
        kind == "followup_inherited" and scope.get("snapshot_dates")
    ):
        expected = {("eq", value) for value in scope.get("snapshot_dates", [])}
        if not expected and isinstance(scope.get("snapshot_date"), str):
            expected = {("eq", scope["snapshot_date"])}
    elif kind == "followup_inherited":
        expected = {("gte", scope.get("start")), ("lt", scope.get("end_exclusive"))}
    else:
        return f"unsupported executable time-scope kind: {kind}"
    if None in {value for _, value in expected} or not expected <= actual:
        missing = sorted(expected - actual)
        return f"date predicates on {date_field} do not preserve declared scope; missing {missing}"
    return None


def validate_dataset(dataset: dict, preflight: dict | None = None) -> dict:
    """Return deterministic errors and warnings without executing SQL or an agent."""
    errors: list[str] = []
    warnings: list[str] = []
    cases = dataset.get("cases") if isinstance(dataset, dict) else None
    if not isinstance(cases, list):
        return {"errors": ["cases must be a list"], "warnings": [], "case_count": 0}

    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(cases) != 40:
        errors.append(f"expected 40 cases, found {len(cases)}")
    if len(ids) != len(set(ids)):
        errors.append("case IDs must be unique")
    if set(ids) != EXPECTED_IDS:
        errors.append("case IDs must be exactly B40-001 through B40-040")

    categories = Counter(case.get("category") for case in cases if isinstance(case, dict))
    behaviors = Counter(case.get("expected_behavior") for case in cases if isinstance(case, dict))
    if dict(categories) != EXPECTED_CATEGORY_COUNTS:
        errors.append(f"category distribution mismatch: {dict(categories)}")
    if dict(behaviors) != EXPECTED_BEHAVIOR_COUNTS:
        errors.append(f"expected-behavior distribution mismatch: {dict(behaviors)}")

    normalized_questions: dict[str, str] = {}
    approved_edges = set(APPROVED_JOINS)
    actual_snapshot_dates = set()
    live_tables = {}
    if preflight:
        live_tables = preflight.get("schema", {}).get("tables", {})
        actual_snapshot_dates = {
            row.get("snapshot_date")
            for row in preflight.get("targeted_checks", {}).get("inventory_null_counts_by_snapshot", [])
        }
        live_date_columns = set(preflight.get("date_columns", []))
    else:
        live_date_columns = set()

    for case in cases:
        if not isinstance(case, dict):
            errors.append("each case must be an object")
            continue
        case_id = str(case.get("id", "<missing-id>"))
        question = " ".join(str(case.get("question", "")).casefold().split())
        if not question:
            errors.append(f"{case_id}: question is required")
        elif question in normalized_questions:
            errors.append(f"{case_id}: exact duplicate question of {normalized_questions[question]}")
        else:
            normalized_questions[question] = case_id

        for key in (
            "language", "difficulty", "required_metric_or_intent", "required_population",
            "required_filters", "time_scope", "grouping_grain", "ranking", "top_n",
            "required_source_tables", "required_columns", "required_joins", "output_contract",
            "numeric_tolerance", "provenance", "semantic_review",
        ):
            if key not in case:
                errors.append(f"{case_id}: missing {key}")
        if case.get("expected_behavior") not in EXPECTED_BEHAVIOR_COUNTS:
            errors.append(f"{case_id}: invalid expected_behavior")
        if case.get("oracle_status") != PENDING_ORACLE:
            errors.append(f"{case_id}: oracle must remain {PENDING_ORACLE}")
        if case.get("review_status") != "PENDING_TWO_INDEPENDENT_REVIEWERS":
            errors.append(f"{case_id}: review must remain pending two independent reviewers")
        for key in ("gold_sql", "gold_parameters", "gold_result"):
            if case.get(key) is not None:
                errors.append(f"{case_id}: candidate file must not freeze {key}; see separate draft oracle")

        source_tables = case.get("required_source_tables", [])
        for source in source_tables:
            if source not in APPROVED_COLUMNS:
                errors.append(f"{case_id}: source is not in the application allowlist: {source}")
            if preflight and source not in live_tables:
                errors.append(f"{case_id}: source absent from live preflight schema: {source}")

        for qualified in case.get("required_columns", []):
            if "." not in qualified:
                errors.append(f"{case_id}: required column must be qualified: {qualified}")
                continue
            table, column = qualified.rsplit(".", 1)
            if column not in APPROVED_COLUMNS.get(table, ()):
                errors.append(f"{case_id}: column is not in the application allowlist: {qualified}")
            if preflight and column not in live_tables.get(table, ()):
                errors.append(f"{case_id}: column absent from live preflight schema: {qualified}")

        for join in case.get("required_joins", []):
            edge = _join_edge(join)
            if edge is None:
                errors.append(f"{case_id}: malformed required join: {join}")
            elif edge not in approved_edges:
                errors.append(f"{case_id}: required join is not approved: {join}")

        if not isinstance(case.get("required_population"), list):
            errors.append(f"{case_id}: required_population must be a list")
        if not isinstance(case.get("required_filters"), list):
            errors.append(f"{case_id}: required_filters must be a list")
        if not case.get("null_policy"):
            errors.append(f"{case_id}: null_policy must be explicit")

        output = case.get("output_contract") or {}
        max_rows = output.get("max_rows")
        if not isinstance(max_rows, int) or not 1 <= max_rows <= MAX_RESULT_ROWS:
            errors.append(f"{case_id}: output_contract.max_rows must be 1..{MAX_RESULT_ROWS}")
        if not output.get("columns"):
            errors.append(f"{case_id}: output columns must be specified")
        tolerance = case.get("numeric_tolerance") or {}
        if tolerance.get("identifiers_and_counts") != 0 or "relative" not in tolerance:
            errors.append(f"{case_id}: identifier/count and relative tolerances must be explicit")

        ranking = case.get("ranking", [])
        if not isinstance(ranking, list):
            errors.append(f"{case_id}: ranking must be a list")
        else:
            for key in ranking:
                if key.get("direction") not in {"asc", "desc"} or not key.get("field"):
                    errors.append(f"{case_id}: each ranking key needs field and asc/desc direction")
        top_n = case.get("top_n")
        if top_n is not None and (not isinstance(top_n, int) or not 1 <= top_n <= MAX_RESULT_ROWS):
            errors.append(f"{case_id}: top_n must be null or 1..{MAX_RESULT_ROWS}")
        if ranking and top_n is None and not output.get("max_rows"):
            errors.append(f"{case_id}: unbounded ranking needs an explicit result ceiling")

        time_scope = case.get("time_scope") or {}
        date_field = time_scope.get("date_field")
        if preflight and date_field and date_field not in live_date_columns:
            errors.append(f"{case_id}: time field is not a live DATE column: {date_field}")
        for snapshot in time_scope.get("snapshot_dates", []):
            if preflight and snapshot not in actual_snapshot_dates:
                errors.append(f"{case_id}: exact inventory snapshot was not observed: {snapshot}")
        if time_scope.get("kind") == "snapshot_range" and preflight:
            start, end = time_scope.get("start"), time_scope.get("end_inclusive")
            covered = {value for value in actual_snapshot_dates if start <= value <= end}
            if not covered:
                errors.append(f"{case_id}: snapshot range contains no observed snapshot")
            if start not in actual_snapshot_dates or end not in actual_snapshot_dates:
                errors.append(f"{case_id}: snapshot range endpoints must both be observed exact snapshots")

        if case.get("category") == "sql_followup_context":
            setup = case.get("conversation_setup")
            if not isinstance(setup, dict) or setup.get("mode") != "frozen_context_injection":
                errors.append(f"{case_id}: follow-up needs a frozen_context_injection setup")
            else:
                state = setup.get("semantic_context")
                if not setup.get("prior_user_question") or not isinstance(state, dict):
                    errors.append(f"{case_id}: follow-up context needs a prior question and semantic state")
                elif setup.get("semantic_context_sha256") != _canonical_hash(state):
                    errors.append(f"{case_id}: follow-up context hash mismatch")
                if setup.get("assistant_output_injected") is not False:
                    errors.append(f"{case_id}: do not inject invented prior assistant results")
        elif "conversation_setup" in case:
            errors.append(f"{case_id}: conversation_setup is reserved for follow-up cases")

        overlap = case.get("semantic_review", {}).get("pilot_overlap")
        if not isinstance(overlap, dict) or overlap.get("status") not in {
            "reviewed_no_direct_overlap", "replaced_contaminated_candidate", "related_distinct_contract",
        }:
            errors.append(f"{case_id}: pilot semantic-overlap disposition is unresolved")
        elif overlap.get("status") == "related_distinct_contract":
            warnings.append(f"{case_id}: related to pilot context; independence needs reviewer confirmation")

        if case.get("expected_behavior") == "execute":
            if case.get("expected_clarification_or_abstention") is not None:
                errors.append(f"{case_id}: execute case cannot have an abstention oracle")
        elif not case.get("expected_clarification_or_abstention"):
            errors.append(f"{case_id}: clarify/abstain case needs a behavioral oracle")

    if preflight:
        if preflight.get("database_role_read_only") is not True:
            errors.append("database preflight did not verify a read-only role")
        if not preflight.get("fingerprint_sha256"):
            errors.append("database fingerprint is missing")
        if not preflight.get("schema", {}).get("tables"):
            errors.append("live preflight schema is missing")
        if not preflight.get("schema", {}).get("primary_keys") or not preflight.get("schema", {}).get("foreign_keys"):
            warnings.append("live information_schema exposed no PK/FK metadata; drafts rely on approved migration contract and duplicate/orphan checks")

    warnings.append("Structural checks cannot establish semantic independence or human approval.")
    return {
        "errors": errors,
        "warnings": list(dict.fromkeys(warnings)),
        "case_count": len(cases),
        "category_counts": dict(categories),
        "expected_behavior_counts": dict(behaviors),
        "case_set_sha256": _canonical_hash(dataset),
        "status": "PASS_STRUCTURAL_DRAFT" if not errors else "FAIL",
    }


def validate_gold_sql_drafts(dataset: dict, gold: dict, preflight: dict | None = None) -> dict:
    """Validate draft SQL structure against the candidate and approved live schema.

    This proves only that each query is bounded, read-only, schema-valid, and
    structurally consistent with its declared case contract. It does not prove
    that the metric interpretation or result is semantically correct.
    """
    errors: list[str] = []
    case_by_id = {case.get("id"): case for case in dataset.get("cases", []) if isinstance(case, dict)}
    execute_ids = {case_id for case_id, case in case_by_id.items()
                   if case.get("expected_behavior") == "execute"}
    gold_cases = gold.get("cases") if isinstance(gold, dict) else None
    if not isinstance(gold_cases, list):
        return {"errors": ["gold cases must be a list"], "validated_count": 0, "status": "FAIL"}
    gold_ids = [case.get("id") for case in gold_cases if isinstance(case, dict)]
    if len(gold_ids) != len(gold_cases) or len(gold_ids) != len(set(gold_ids)):
        errors.append("gold case IDs must be unique objects")
    if set(gold_ids) != execute_ids:
        errors.append("gold SQL IDs must match exactly the execute candidate IDs")
    expected_case_hash = _canonical_hash(dataset)
    if gold.get("case_set_sha256") != expected_case_hash:
        errors.append("gold SQL case_set_sha256 does not match candidate dataset")
    if gold.get("sql_agent_outputs_used") is not False:
        errors.append("gold SQL must explicitly state SQL Agent outputs were not used")
    if gold.get("human_approval_claimed") is not False:
        errors.append("draft gold SQL must not claim human approval")
    if not isinstance(gold.get("author_identity"), str) or not gold["author_identity"].strip():
        errors.append("draft gold SQL author identity must be recorded")
    if gold.get("review_status") != "PENDING_TWO_INDEPENDENT_REVIEWERS":
        errors.append("gold SQL must remain pending two independent reviewers")

    live_tables = preflight.get("schema", {}).get("tables", {}) if preflight else {}
    if preflight and not live_tables:
        errors.append("gold validation preflight is missing live schema tables")
    schema_columns = {
        table: frozenset(columns) & APPROVED_COLUMNS.get(table, frozenset())
        for table, columns in (live_tables.items() if live_tables else APPROVED_COLUMNS.items())
        if table in APPROVED_COLUMNS
    }
    allowed_sources = set(schema_columns)
    validated_count = 0
    per_case = []
    for item in gold_cases:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("id", "<missing-id>"))
        case = case_by_id.get(case_id)
        case_errors: list[str] = []
        if not case:
            continue
        sql = item.get("sql")
        parameters = item.get("parameters")
        if not isinstance(sql, str) or not sql.strip():
            case_errors.append("SQL is required")
        if not isinstance(parameters, list):
            case_errors.append("parameters must be a list")
            parameters = []
        if item.get("status") != "DRAFT_PENDING_HUMAN_REVIEW":
            case_errors.append("draft status must remain DRAFT_PENDING_HUMAN_REVIEW")
        if item.get("human_review", {}).get("reviewer_1") != "PENDING" or \
                item.get("human_review", {}).get("reviewer_2") != "PENDING":
            case_errors.append("reviewer approvals must remain pending")
        if not case_errors:
            try:
                validated = validate_commerce_sql(
                    sql,
                    allowed_sources=allowed_sources,
                    schema_columns=schema_columns,
                    approved_joins=APPROVED_JOINS,
                    primary_keys=PRIMARY_KEYS,
                    date_columns=APPROVED_DATE_COLUMNS,
                )
                tree = parse(sql, read="postgres")[0]
                if not isinstance(tree, exp.Select):
                    case_errors.append("SQL root must be SELECT")
                parameter_indexes = sorted({int(node.this.this) for node in tree.find_all(exp.Parameter)})
                if parameter_indexes != list(range(1, len(parameters) + 1)):
                    case_errors.append(
                        f"parameter placeholders {parameter_indexes} do not match {len(parameters)} supplied values"
                    )
                date_error = _date_scope_error(tree, case, parameters)
                if date_error:
                    case_errors.append(date_error)

                actual_sources = set(validated.sources)
                required_sources = set(case.get("required_source_tables", []))
                if actual_sources != required_sources:
                    case_errors.append(
                        f"SQL sources {sorted(actual_sources)} do not match required sources {sorted(required_sources)}"
                    )

                projections = [projection.alias_or_name.casefold() for projection in tree.expressions]
                expected_columns = [str(name).casefold() for name in case.get("output_contract", {}).get("columns", [])]
                if projections != expected_columns:
                    case_errors.append(
                        f"SQL output columns {projections} do not match contract {expected_columns}"
                    )

                expected_ranking = case.get("ranking", [])
                order_clause = tree.args.get("order")
                actual_ranking = []
                if order_clause:
                    expression_aliases = {
                        projection.this.sql(dialect="postgres", normalize=True).casefold(): projection.alias_or_name.casefold()
                        for projection in tree.expressions
                    }
                    for ordered in order_clause.expressions:
                        expression = ordered.this
                        field = expression.alias_or_name.casefold()
                        if field not in expected_columns:
                            field = expression_aliases.get(
                                expression.sql(dialect="postgres", normalize=True).casefold(), field,
                            )
                        actual_ranking.append({
                            "field": field,
                            "direction": "desc" if ordered.args.get("desc") else "asc",
                        })
                if actual_ranking != expected_ranking:
                    case_errors.append(
                        f"SQL ORDER BY {actual_ranking} does not match ranking contract {expected_ranking}"
                    )

                top_n = case.get("top_n")
                if top_n is not None:
                    limit = tree.args.get("limit")
                    limit_expression = limit.expression if limit else None
                    actual_limit = (
                        int(limit_expression.this)
                        if isinstance(limit_expression, exp.Literal) and not limit_expression.is_string
                        else None
                    )
                    if actual_limit != top_n:
                        case_errors.append(f"SQL LIMIT {actual_limit} does not match TOP-N contract {top_n}")

                actual_edges = set()
                table_aliases = {
                    table.alias_or_name.casefold(): f"{table.db}.{table.name}".casefold()
                    for table in tree.find_all(exp.Table)
                }
                for equality in tree.find_all(exp.EQ):
                    left, right = equality.this, equality.expression
                    if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                        if left.table and right.table:
                            actual_edges.add(frozenset({
                                (table_aliases.get(left.table.casefold(), left.table.casefold()), left.name.casefold()),
                                (table_aliases.get(right.table.casefold(), right.table.casefold()), right.name.casefold()),
                            }))
                for join in case.get("required_joins", []):
                    edge = _join_edge(join)
                    if edge not in actual_edges:
                        case_errors.append(f"required relationship is absent from SQL predicates: {join}")

                scope = case.get("time_scope", {})
                required_dates = set()
                for key in ("start", "end_exclusive", "end_inclusive", "snapshot_date"):
                    if isinstance(scope.get(key), str):
                        required_dates.add(scope[key])
                required_dates.update(value for value in scope.get("snapshot_dates", []) if isinstance(value, str))
                string_parameters = {value for value in parameters if isinstance(value, str)}
                if not required_dates <= string_parameters:
                    case_errors.append(
                        f"time-scope dates missing from bound parameters: {sorted(required_dates - string_parameters)}"
                    )
            except (SQLValidationError, TypeError, ValueError, IndexError) as error:
                case_errors.append(f"SQL validation failed: {error}")
        if case_errors:
            errors.extend(f"{case_id}: {message}" for message in case_errors)
        else:
            validated_count += 1
        per_case.append({"id": case_id, "status": "PASS" if not case_errors else "FAIL", "errors": case_errors})

    return {
        "errors": errors,
        "validated_count": validated_count,
        "gold_case_count": len(gold_cases),
        "per_case": per_case,
        "status": "PASS_STRUCTURAL_DRAFT" if not errors and validated_count == len(execute_ids) else "FAIL",
        "warning": "Structural SQL validation is not semantic review or human approval.",
    }


def validate_gold_results(dataset: dict, gold: dict, results: dict, preflight: dict) -> dict:
    """Check provisional reference rows against the exact draft and snapshot."""
    errors: list[str] = []
    warnings: list[str] = []
    cases = {case.get("id"): case for case in dataset.get("cases", []) if isinstance(case, dict)}
    gold_by_id = {item.get("id"): item for item in gold.get("cases", []) if isinstance(item, dict)}
    result_cases = results.get("cases") if isinstance(results, dict) else None
    if not isinstance(result_cases, list):
        return {"errors": ["reference result cases must be a list"], "warnings": [], "validated_count": 0,
                "status": "FAIL"}
    result_ids = [item.get("id") for item in result_cases if isinstance(item, dict)]
    if len(result_ids) != len(result_cases) or len(result_ids) != len(set(result_ids)):
        errors.append("reference result IDs must be unique objects")
    if set(result_ids) != set(gold_by_id):
        errors.append("reference result IDs must match the gold SQL draft IDs")
    expected_case_hash = _canonical_hash(dataset)
    if results.get("case_set_sha256") != expected_case_hash:
        errors.append("reference result case_set_sha256 does not match the current candidate set")
    if results.get("heldout_agent_executed") is not False or results.get("sql_agent_generation_calls") != 0:
        errors.append("held-out SQL Agent generation must remain unexecuted during gold preparation")
    if results.get("database_role_read_only") is not True:
        errors.append("reference results must verify a read-only database role")
    expected_fingerprint = preflight.get("fingerprint_sha256")
    if not expected_fingerprint or results.get("database_fingerprint_sha256") != expected_fingerprint:
        errors.append("reference results must use the verified preflight database fingerprint")
    if results.get("execution_failures"):
        errors.append(f"reference executions failed: {results['execution_failures']}")

    validated_count = 0
    for item in result_cases:
        if not isinstance(item, dict):
            continue
        case_id = item.get("id")
        case = cases.get(case_id)
        gold_item = gold_by_id.get(case_id)
        if not case or not gold_item:
            continue
        case_errors = []
        if item.get("sql") != gold_item.get("sql") or item.get("parameters") != gold_item.get("parameters"):
            case_errors.append("executed SQL/parameters differ from the current author-written gold draft")
        if item.get("status") == "EXECUTION_FAILED":
            case_errors.append(f"execution failed: {item.get('error_type')}: {item.get('error_detail')}")
        elif item.get("status") == "PROVISIONAL_EMPTY_NOT_APPROVED":
            warnings.append(f"{case_id}: empty provisional reference needs human semantic review")
        elif item.get("status") != "PROVISIONAL_NOT_APPROVED":
            case_errors.append("reference result status must remain provisional and not approved")
        expected_columns = case.get("output_contract", {}).get("columns", [])
        if item.get("columns") != expected_columns:
            case_errors.append(f"result columns do not match output contract {expected_columns}")
        rows = item.get("rows")
        if not isinstance(rows, list) or item.get("row_count") != len(rows):
            case_errors.append("reference row_count does not match the stored row list")
            rows = rows if isinstance(rows, list) else []
        if any(not isinstance(row, dict) or list(row) != expected_columns for row in rows):
            case_errors.append("one or more result rows do not match the declared output column order")
        ranking = case.get("ranking", [])
        for left, right in zip(rows, rows[1:]):
            for key in ranking:
                field = key["field"]
                left_value, right_value = left.get(field), right.get(field)
                if left_value is None and right_value is None:
                    continue
                if left_value is None:
                    case_errors.append("reference rows violate NULLS LAST ranking order")
                    break
                if right_value is None:
                    break
                try:
                    left_value, right_value = Decimal(str(left_value)), Decimal(str(right_value))
                except (InvalidOperation, ValueError):
                    left_value, right_value = str(left_value), str(right_value)
                if left_value == right_value:
                    continue
                is_descending = key.get("direction") == "desc"
                if (is_descending and left_value < right_value) or (not is_descending and left_value > right_value):
                    case_errors.append("reference rows do not follow the declared ranking and tie-break order")
                break
        expected_hash = _canonical_hash({"columns": item.get("columns", []), "rows": rows})
        if item.get("result_sha256") != expected_hash:
            case_errors.append("result_sha256 does not match the stored columns and rows")
        if case_errors:
            errors.extend(f"{case_id}: {message}" for message in case_errors)
        else:
            validated_count += 1

    if results.get("execution_count") != len(result_cases):
        errors.append("execution_count does not match the number of stored reference cases")
    return {
        "errors": errors,
        "warnings": list(dict.fromkeys(warnings)),
        "validated_count": validated_count,
        "reference_case_count": len(result_cases),
        "status": "PASS_PROVISIONAL_REFERENCE" if not errors and validated_count == len(gold_by_id) else "FAIL",
        "warning": "Passing checks verify artifact consistency, not semantic approval of the gold oracle.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--preflight")
    parser.add_argument("--output")
    args = parser.parse_args()
    dataset = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    preflight = json.loads(Path(args.preflight).read_text(encoding="utf-8")) if args.preflight else None
    result = validate_dataset(dataset, preflight)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if not result["errors"] else 1)


if __name__ == "__main__":
    main()
