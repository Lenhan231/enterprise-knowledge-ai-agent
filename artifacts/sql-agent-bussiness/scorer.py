"""Deterministic scorer for the frozen SQL Agent five-case pilot."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import traverse_scope


PROTOCOL_VERSION = "1.1.2"
SCORER_VERSION = "2.0.2"
SCORE_FORMAT_VERSION = "sql-agent-benchmark-scores.v2"


def _iso(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _table_name(table):
    if not table.db:
        return None
    return f"{table.db.casefold()}.{table.name.casefold()}"


def _origin(scope, column):
    """Resolve a column through transparent CTE projections."""
    if not column.table:
        return None
    source = scope.sources.get(column.table)
    if isinstance(source, exp.Table):
        return _table_name(source), column.name.casefold()
    if source is not None and hasattr(source, "expression"):
        projections = [projection for projection in source.expression.selects
                       if projection.alias_or_name.casefold() == column.name.casefold()]
        if len(projections) == 1 and isinstance(projections[0].unalias(), exp.Column):
            return _origin(source, projections[0].unalias())
    return None


def _literal(node, parameters):
    if isinstance(node, exp.Paren):
        return _literal(node.this, parameters)
    if isinstance(node, exp.Cast):
        return _literal(node.this, parameters)
    if isinstance(node, exp.Parameter):
        try:
            return _iso(parameters[int(node.this.name) - 1])
        except (IndexError, TypeError, ValueError):
            return None
    if isinstance(node, exp.Literal):
        if node.is_string:
            return node.this
        try:
            return Decimal(node.this)
        except InvalidOperation:
            return node.this
    return None


def _conjuncts(node):
    if isinstance(node, (exp.Where, exp.Paren)):
        yield from _conjuncts(node.this)
    elif isinstance(node, exp.And):
        yield from _conjuncts(node.this)
        yield from _conjuncts(node.expression)
    elif node is not None:
        yield node


def _predicates(scopes):
    for scope in scopes:
        for predicate in _conjuncts(scope.expression.args.get("where")):
            yield scope, predicate


def _column_operand(node, scope):
    insensitive = isinstance(node, exp.Lower)
    column = node.this if insensitive else node
    if not isinstance(column, exp.Column):
        return None, insensitive
    return _origin(scope, column), insensitive


def _equals_filter(scopes, parameters, source, column, expected):
    target = (source, column)
    for scope, predicate in _predicates(scopes):
        if not isinstance(predicate, exp.EQ):
            continue
        for left, right in ((predicate.this, predicate.expression),
                            (predicate.expression, predicate.this)):
            origin, insensitive = _column_operand(left, scope)
            value = _literal(right, parameters)
            if origin == target and value is not None:
                if insensitive:
                    value = str(value).casefold()
                    wanted = str(expected).casefold()
                else:
                    wanted = expected
                if value == wanted:
                    return True
    return False


def _date_range(scopes, parameters, source, column, start, end_exclusive, end_inclusive=None,
                column_type=None):
    target = (source, column)
    if str(column_type).casefold() == "date":
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end_exclusive)
        except (TypeError, ValueError):
            start_date = end_date = None
        if (start_date is not None and end_date is not None
                and start_date == date(start_date.year, 1, 1)
                and end_date == date(start_date.year + 1, 1, 1)):
            date_predicates = [
                (scope, predicate)
                for scope, predicate in _predicates(scopes)
                if any(_origin(scope, candidate) == target for candidate in predicate.find_all(exp.Column))
            ]
            for scope, predicate in date_predicates:
                if not isinstance(predicate, exp.EQ):
                    continue
                for extract, value in ((predicate.this, predicate.expression),
                                       (predicate.expression, predicate.this)):
                    if (isinstance(extract, exp.Extract)
                            and extract.this.name.casefold() == "year"
                            and _origin(scope, extract.expression) == target
                            and _literal(value, parameters) == Decimal(start_date.year)
                            and len(date_predicates) == 1):
                        return True
    lower = upper = False
    for scope, predicate in _predicates(scopes):
        if not isinstance(predicate, (exp.GTE, exp.GT, exp.LT, exp.LTE)):
            continue
        left, right = predicate.this, predicate.expression
        origin, _ = _column_operand(left, scope)
        if origin == target:
            value = _literal(right, parameters)
            operator = type(predicate)
        else:
            origin, _ = _column_operand(right, scope)
            if origin != target:
                continue
            value = _literal(left, parameters)
            operator = {exp.GTE: exp.LTE, exp.GT: exp.LT,
                        exp.LTE: exp.GTE, exp.LT: exp.GT}[type(predicate)]
        value = str(value) if value is not None else None
        if operator is exp.GTE and value == start:
            lower = True
        if operator is exp.LT and value == end_exclusive:
            upper = True
        if (operator is exp.LTE and end_inclusive and value == end_inclusive
                and str(column_type).casefold() == "date"):
            upper = True
    return lower and upper


def _not_null_filter(scopes, source, column):
    for scope, predicate in _predicates(scopes):
        node = predicate
        negative = isinstance(node, exp.Not) and isinstance(node.this, exp.Is)
        if isinstance(node, exp.Not) and isinstance(node.this, exp.Is):
            node = node.this
        if not isinstance(node, exp.Is) or not (negative or node.args.get("negate")):
            continue
        origin, _ = _column_operand(node.this, scope)
        if origin == (source, column) and isinstance(node.expression, exp.Null):
            return True
    return False


def _has_required_aggregation(scopes, kind, source, column):
    for scope in scopes:
        for aggregate in scope.expression.find_all(exp.Count if kind == "count_distinct" else exp.Sum):
            if kind == "count_distinct":
                if not isinstance(aggregate.this, exp.Distinct):
                    continue
                candidates = list(aggregate.this.find_all(exp.Column))
            else:
                candidates = list(aggregate.this.find_all(exp.Column))
            if any(_origin(scope, candidate) == (source, column) for candidate in candidates):
                return True
    return False


def _grouped_by(scopes, column):
    for scope in scopes:
        group = scope.expression.args.get("group")
        if not group:
            continue
        for item in group.expressions:
            if isinstance(item, exp.Column) and item.name.casefold() == column:
                return True
            if isinstance(item, exp.Literal) and item.is_int:
                index = int(item.this) - 1
                projections = scope.expression.selects
                if 0 <= index < len(projections):
                    value = projections[index].unalias()
                    if isinstance(value, exp.Column) and value.name.casefold() == column:
                        return True
    return False


def _root_order(tree):
    order = tree.args.get("order")
    if not order:
        return []
    projections = tree.selects
    result = []
    for ordered in order.expressions:
        expression = ordered.this if isinstance(ordered, exp.Ordered) else ordered
        if isinstance(expression, exp.Literal) and expression.is_int:
            index = int(expression.this) - 1
            name = projections[index].alias_or_name if 0 <= index < len(projections) else None
        elif isinstance(expression, exp.Column):
            name = expression.name
        else:
            name = expression.alias_or_name if isinstance(expression, exp.Expression) else None
        direction = "desc" if isinstance(ordered, exp.Ordered) and ordered.args.get("desc") else "asc"
        result.append((str(name).casefold() if name else None, direction))
    return result


def _requested_column_present(case, actual_columns, requested):
    aliases = case.get("column_aliases", {}).get(requested, [])
    return requested.casefold() in actual_columns or any(alias.casefold() in actual_columns for alias in aliases)


def _sql_semantics(case, observation, verified_column_types=None):
    contract = case["semantic"]
    sql = observation.get("sql")
    if not sql:
        return {"applicable": bool(case["supported"]), "passed": False,
                "checks": {"sql_present": False}, "issues": ["No SQL plan was produced."]}
    try:
        tree = parse_one(sql, read="postgres")
        scopes = list(traverse_scope(tree))
    except Exception as error:
        return {"applicable": True, "passed": False, "checks": {"sql_parse": False},
                "issues": [f"SQL parse failed: {type(error).__name__}"]}

    tables = {_table_name(table) for table in tree.find_all(exp.Table)}
    parameters = observation.get("parameters", [])
    checks = {"required_tables": set(case["required_tables"]) <= tables}
    issues = []
    for name, expected in contract.get("filters", {}).items():
        if name == "order_status":
            passed = _equals_filter(scopes, parameters, "commerce.orders", "order_status", expected)
        elif name == "snapshot_date":
            passed = _equals_filter(scopes, parameters, "commerce.inventory", "snapshot_date", expected)
        elif name == "stock_on_hand":
            passed = _not_null_filter(scopes, "commerce.inventory", "stock_on_hand")
            # NULLS LAST with an exact top-N order is equivalent for this frozen snapshot cohort.
            if not passed:
                passed = any(
                    isinstance(order, exp.Ordered)
                    and isinstance(order.this, exp.Column)
                    and order.this.name.casefold() == "stock_on_hand"
                    and order.args.get("desc")
                    and order.args.get("nulls_first") is False
                    for order in (tree.args.get("order").expressions if tree.args.get("order") else [])
                )
        elif name == "date_range":
            column_type = expected.get("column_type") or (verified_column_types or {}).get(
                expected["source"], {}
            ).get(expected["column"])
            passed = _date_range(
                scopes, parameters, expected["source"], expected["column"],
                expected["start"], expected["end_exclusive"], expected.get("end_inclusive"),
                column_type,
            )
        else:
            passed = False
        checks[f"filter:{name}"] = passed

    aggregation = contract.get("aggregation")
    if aggregation == "sum_revenue":
        passed = _has_required_aggregation(scopes, "sum", "commerce.sales", "revenue")
    elif aggregation == "count_distinct_order_id":
        passed = _has_required_aggregation(scopes, "count_distinct", "commerce.orders", "order_id")
    elif aggregation == "sum_order_items_quantity":
        passed = _has_required_aggregation(scopes, "sum", "commerce.order_items", "quantity")
    else:
        passed = True
    checks["aggregation"] = passed

    expected_group = contract.get("group_by", [])
    checks["grouping"] = all(_grouped_by(scopes, column.casefold()) for column in expected_group)
    expected_order = contract.get("order_by", [])
    ignored_order_columns = {name.casefold() for name in contract.get("ignore_order_columns", [])}
    actual_order = [item for item in _root_order(tree) if item[0] not in ignored_order_columns]
    ranking_checks = []
    for index, expected in enumerate(expected_order):
        names = {expected["column"].casefold(), *(name.casefold() for name in expected.get("aliases", []))}
        ranking_checks.append(index < len(actual_order)
                              and actual_order[index][0] in names
                              and actual_order[index][1] == expected["direction"])
    checks["ranking_order"] = all(ranking_checks)
    limit = tree.args.get("limit")
    actual_limit = None
    if limit and isinstance(limit.expression, exp.Literal) and limit.expression.is_int:
        actual_limit = int(limit.expression.this)
    checks["limit"] = actual_limit == contract.get("limit")

    for join in tree.find_all(exp.Join):
        if not join.args.get("on"):
            continue
        for equality in join.args["on"].find_all(exp.EQ):
            left, right = equality.this, equality.expression
            if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                continue
            origins = {_origin(scope, column) for scope in scopes for column in (left, right)}
            normalized = {origin for origin in origins if origin}
            if {("commerce.order_items", "order_id"), ("commerce.orders", "order_id")} <= normalized:
                checks["required_join"] = True
                break
        if checks.get("required_join"):
            break
    if "join" in contract:
        checks["required_join"] = checks.get("required_join", False)

    actual_output_columns = {projection.alias_or_name.casefold() for projection in tree.selects}
    checks["all_requested_columns"] = all(
        _requested_column_present(case, actual_output_columns, column)
        for column in case["requested_columns"]
    )
    for check, passed in checks.items():
        if not passed:
            issues.append(check)
    return {"applicable": True, "passed": all(checks.values()), "checks": checks, "issues": issues}


def _value_equal(expected, actual, case, column):
    if expected is None or actual is None:
        return expected is None and actual is None
    metric_columns = {"revenue", "order_count", "units_sold", "stock_on_hand"}
    if column in metric_columns:
        try:
            left, right = Decimal(str(expected)), Decimal(str(actual))
        except InvalidOperation:
            return False
        tolerance = case.get("numeric_tolerance", {})
        absolute = Decimal(str(tolerance.get("absolute", 0)))
        relative = Decimal(str(tolerance.get("relative", 0)))
        return abs(left - right) <= max(absolute, relative * max(abs(left), abs(right)))
    return _iso(expected) == _iso(actual)


def _result_comparison(case, observation):
    expected_rows = [{str(key).casefold(): value for key, value in row.items()}
                     for row in case["gold"].get("rows", [])]
    observed_rows = [{str(key).casefold(): value for key, value in row.items()}
                     for row in (observation.get("rows") or [])]
    expected_columns = [column.casefold() for column in case["requested_columns"]]
    strict_columns = [column.casefold() for column in case.get("strict_columns", case["requested_columns"])]
    actual_columns = [str(column).casefold() for column in observation.get("columns", [])]
    if not actual_columns and observed_rows:
        actual_columns = [str(column).casefold() for column in observed_rows[0].keys()]
    accepted_business_columns = set(expected_columns)
    for requested in expected_columns:
        accepted_business_columns.update(
            alias.casefold() for alias in case.get("column_aliases", {}).get(requested, [])
        )
    missing = [column for column in expected_columns
               if not _requested_column_present(case, set(actual_columns), column)]
    extras = [column for column in actual_columns if column not in accepted_business_columns]
    allowed_extra = {key.casefold(): value for key, value in case.get("provenance_columns", {}).items()}
    unexpected_extras = [column for column in extras if column not in allowed_extra]
    business_rows_match = not missing and not unexpected_extras and len(observed_rows) == len(expected_rows)
    strict_schema = actual_columns == strict_columns

    def expected_value(row, column):
        if column in row:
            return row[column]
        return next((row[alias.casefold()] for alias in case.get("column_aliases", {}).get(column, [])
                     if alias.casefold() in row), None)

    def compare_rows(actual, expected):
        for column in expected_columns:
            actual_key = column if column in actual else next(
                (alias.casefold() for alias in case.get("column_aliases", {}).get(column, [])
                 if alias.casefold() in actual), None
            )
            if actual_key is None:
                return False
            if not _value_equal(expected_value(expected, column), actual.get(actual_key), case, column):
                return False
        for column, provenance_value in allowed_extra.items():
            if column in actual and not _value_equal(provenance_value, actual[column], case, column):
                return False
        return True

    if business_rows_match:
        if case.get("ordering") == "ordered":
            business_rows_match = all(compare_rows(actual, expected)
                                      for actual, expected in zip(observed_rows, expected_rows))
        else:
            unused = list(expected_rows)
            for actual in observed_rows:
                match = next((index for index, expected in enumerate(unused)
                              if compare_rows(actual, expected)), None)
                if match is None:
                    business_rows_match = False
                    break
                unused.pop(match)
            business_rows_match = business_rows_match and not unused

    strict_rows_match = (
        strict_schema and len(observed_rows) == len(expected_rows)
        and all(all(_value_equal(expected.get(column), actual.get(column), case, column)
                    for column in strict_columns)
                for actual, expected in zip(observed_rows, expected_rows))
    )
    return {
        "business_rows_match": business_rows_match,
        "strict_schema_match": strict_schema,
        "strict_rows_match": strict_rows_match,
        "missing_columns": missing,
        "extra_columns": extras,
        "unexpected_extra_columns": unexpected_extras,
    }


def _clarification_is_valid(observation):
    answer = observation.get("answer")
    metadata = observation.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        return False
    metadata = metadata or {}
    options = metadata.get("clarification_options", observation.get("clarification_options", []))
    if options is None:
        options = []
    return (isinstance(answer, str) and bool(answer.strip())
            and isinstance(options, list) and len(options) <= 3
            and all(isinstance(option, str) and bool(option.strip()) for option in options))


def _validation_blocked(observation):
    error_types = {
        "SQLValidationError", "SQLSecurityError", "SQLSchemaMismatchError",
        "SQLJoinValidationError", "MetricDefinitionError",
    }
    failure_classes = {
        "sql_validation_failure", "sql_security_failure", "schema_validation_failure",
        "metric_validation_failure", "semantic_validation_failure",
    }
    return (observation.get("error_type") in error_types
            or observation.get("failure_class") in failure_classes)


def score_case(case, observation, *, verified_column_types=None):
    if observation.get("status") == "NOT_RUN":
        return {
            "id": case["id"], "supported": case["supported"],
            "business_end_to_end_correct": None, "strict_result_exact_match": None,
            "sql_semantic_accuracy": None, "execution_success": None,
            "false_clarification_abstention": None, "supported_noncompletion": None,
            "validation_blocked_supported": None, "safe_unsupported_abstention": None,
            "failure_class": observation.get("failure_class", "not_run"),
            "semantic": {"applicable": False, "passed": None, "checks": {}, "issues": []},
            "result": None, "unsafe_execution_count": 0, "schema_selection": {},
            "calls": {}, "latency_ms": None,
        }
    if not case["supported"]:
        status = observation.get("status")
        safe_no_query = status in {"clarification_required", "unsupported", "abstained"} \
            and _clarification_is_valid(observation) \
            and not observation.get("sql") and not observation.get("execution_events")
        return {
            "id": case["id"], "supported": False, "business_end_to_end_correct": None,
            "strict_result_exact_match": None, "sql_semantic_accuracy": None,
            "safe_unsupported_abstention": safe_no_query,
            "business_result_match": None,
            "failure_class": None if safe_no_query else "invalid_unsupported_execution_or_response",
            "semantic": {"applicable": False, "passed": None, "checks": {}, "issues": []},
            "result": None,
            "schema_selection": observation.get("schema_selection", {}),
            "calls": observation.get("calls", {}),
            "latency_ms": observation.get("latency_ms"),
        }

    semantic = _sql_semantics(case, observation, verified_column_types)
    result = _result_comparison(case, observation)
    schema_selection = dict(observation.get("schema_selection", {}))
    required_tables = set(case.get("required_tables", []))
    final_selected = schema_selection.get("final_selected_tables")
    if final_selected is not None:
        final_selected = set(final_selected)
        covered = sorted(required_tables & final_selected)
        schema_selection.update(
            final_covered_tables=covered,
            final_covered_count=len(covered),
            final_required_count=len(required_tables),
        )
    candidates = set(schema_selection.get("candidate_tables", []))
    if schema_selection.get("method") == "jev_top_five":
        schema_selection["jev_top5"] = {
            "tables": sorted(candidates),
            "recall_numerator": len(required_tables & candidates),
            "recall_denominator": len(required_tables),
        }
    executed = observation.get("status") in {"executed", "executed_empty"}
    business = executed and semantic["passed"] and result["business_rows_match"]
    strict = executed and semantic["passed"] and result["strict_schema_match"] and result["strict_rows_match"]
    if not executed:
        failure = observation.get("failure_class") or "supported_request_not_executed"
    elif not semantic["passed"]:
        failure = "sql_semantic_contract_failure"
    elif not result["business_rows_match"]:
        failure = "business_result_mismatch"
    else:
        failure = None
    return {
        "id": case["id"], "supported": True,
        "business_end_to_end_correct": bool(business),
        "business_result_match": bool(result["business_rows_match"]) if executed else None,
        "strict_result_exact_match": bool(strict),
        "sql_semantic_accuracy": bool(semantic["passed"]),
        "execution_success": executed,
        "false_clarification_abstention": observation.get("status") in {
            "clarification_required", "unsupported", "abstained", "rejected",
        },
        "supported_noncompletion": not bool(business),
        "validation_blocked_supported": _validation_blocked(observation),
        "safe_unsupported_abstention": None,
        "failure_class": failure,
        "semantic": semantic,
        "result": result,
        "unsafe_execution_count": sum(not event.get("security_validated", False)
                                       for event in observation.get("execution_events", [])),
        "schema_selection": schema_selection,
        "calls": observation.get("calls", {}),
        "latency_ms": observation.get("latency_ms"),
    }


def _rate(cases, key):
    applicable = [case[key] for case in cases if case.get(key) is not None]
    if not applicable:
        return {"numerator": 0, "denominator": 0, "value": None}
    passed = sum(bool(value) for value in applicable)
    return {"numerator": passed, "denominator": len(applicable), "value": passed / len(applicable)}


def _percentile(values, percentile):
    values = sorted(float(value) for value in values if value is not None)
    if not values:
        return None
    index = max(0, math.ceil(percentile * len(values)) - 1)
    return values[index]


def score_experiment(case_set, data):
    observations = {case["id"]: case for case in data.get("cases", [])}
    manifest = data.get("manifest", {})
    verified_column_types = {
        source: {str(column).casefold(): str(column_type).casefold()
                 for column, column_type in table.get("column_types", {}).items()}
        for source, table in manifest.get("data_coverage", {}).items()
        if isinstance(table, dict)
    }
    for coverage_key in ("data_coverage", "preflight_coverage"):
        for source, table in manifest.get(coverage_key, {}).items():
            if not isinstance(table, dict):
                continue
            for name, value in table.items():
                if name.endswith("_type") and isinstance(value, str):
                    verified_column_types.setdefault(source, {})[name[:-5].casefold()] = value.casefold()
    for source, columns in manifest.get("verified_column_types", {}).items():
        if isinstance(columns, dict):
            verified_column_types.setdefault(source, {}).update({
                str(column).casefold(): str(column_type).casefold()
                for column, column_type in columns.items()
            })
    outcomes = [score_case(
        case, observations.get(case["id"], {}), verified_column_types=verified_column_types,
    ) for case in case_set["cases"]]
    supported = [case for case in outcomes if case["supported"]]
    unsupported = [case for case in outcomes if not case["supported"]]
    latencies = [case.get("latency_ms") for case in supported]
    repairs = [case for case in supported if case.get("calls", {}).get("sql_repair", 0) > 0]
    repair_recovered = [case for case in repairs if case.get("execution_success")]
    jev_applicable = [case for case in supported
                      if case.get("schema_selection", {}).get("jev_top5") is not None]
    jev_hits = sum(case["schema_selection"].get("jev_top5", {}).get("recall_numerator", 0)
                   for case in jev_applicable)
    jev_total = sum(case["schema_selection"].get("jev_top5", {}).get("recall_denominator", 0)
                    for case in jev_applicable)
    return {
        "format_version": SCORE_FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "scorer_version": SCORER_VERSION,
        "metrics": {
            "business_end_to_end_accuracy": _rate(supported, "business_end_to_end_correct"),
            "business_result_accuracy": _rate(supported, "business_result_match"),
            "strict_result_exact_match": _rate(supported, "strict_result_exact_match"),
            "sql_semantic_accuracy": _rate(supported, "sql_semantic_accuracy"),
            "execution_success": _rate(supported, "execution_success"),
            "false_clarification_abstention_rate": _rate(supported, "false_clarification_abstention"),
            "supported_noncompletion_rate": _rate(supported, "supported_noncompletion"),
            "validation_blocked_supported_rate": _rate(supported, "validation_blocked_supported"),
            "safe_unsupported_abstention": _rate(unsupported, "safe_unsupported_abstention"),
            "valid_clarification_abstention_rate": _rate(unsupported, "safe_unsupported_abstention"),
            "repair_recovery_rate": {
                "numerator": len(repair_recovered), "denominator": len(repairs),
                "value": len(repair_recovered) / len(repairs) if repairs else None,
            },
            "jev_table_recall_at_5": {
                "numerator": jev_hits, "denominator": jev_total,
                "value": jev_hits / jev_total if jev_total else None,
                "applicable_cases": len(jev_applicable),
            },
            "final_selected_schema_coverage": _coverage(outcomes),
            "unsafe_execution_count": sum(case.get("unsafe_execution_count", 0) for case in outcomes),
            "latency_ms": {"p50_nearest_rank": _percentile(latencies, 0.50),
                           "p95_nearest_rank": _percentile(latencies, 0.95),
                           "sample_count": sum(value is not None for value in latencies)},
            "provider_calls": _provider_call_summary(outcomes),
            "pipeline_calls": _sum_calls(outcomes),
        },
        "cases": outcomes,
    }


def _coverage(outcomes):
    numerator = denominator = 0
    for case in outcomes:
        selection = case.get("schema_selection", {})
        if selection.get("final_covered_tables") is None:
            continue
        numerator += selection.get("final_covered_count", 0)
        denominator += selection.get("final_required_count", 0)
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _sum_calls(outcomes):
    keys = {key for case in outcomes for key in case.get("calls", {})}
    return {key: sum(case.get("calls", {}).get(key, 0) for case in outcomes) for key in sorted(keys)}


def _provider_call_summary(outcomes):
    calls = _sum_calls(outcomes)
    sql_generation = calls.get("general_sql_generation", 0)
    metric_interpretation = calls.get("metric_interpretation", 0)
    jev = calls.get("jev_attempts", 0)
    local_codex = calls.get("local_codex_fallback_calls", 0)
    return {
        "sql_generation_provider_submissions": sql_generation,
        "metric_interpretation_provider_submissions": metric_interpretation,
        "jev_requests": jev,
        "local_codex_fallback_calls": local_codex,
        "total_model_calls": sql_generation + metric_interpretation + jev + local_codex,
        # This is a subset of sql_generation_provider_submissions, not an extra total.
        "secondary_sql_provider_fallback_submissions": calls.get("provider_fallback_calls", 0),
    }


def render_report(case_set, scored, manifest):
    metrics = scored["metrics"]
    lines = [
        "# SQL Agent Business Benchmark Report",
        "",
        f"Protocol version: `{scored.get('protocol_version', PROTOCOL_VERSION)}`",
        f"Scorer version: `{scored.get('scorer_version', SCORER_VERSION)}`",
        f"Experiment: `{manifest.get('experiment_id', 'unspecified')}`",
        f"Status: **{manifest.get('status', 'unknown')}**",
        f"Application revision: `{manifest.get('application_revision', 'unknown')}`",
        f"Provider/model: `{manifest.get('provider', 'unknown')}` / `{manifest.get('model', 'unknown')}`",
        f"Database: `{manifest.get('database_classification', 'unknown')}`; "
        f"read-only role verified: `{manifest.get('database_role_read_only', 'unknown')}`",
        f"Dataset fingerprint: `{manifest.get('dataset_fingerprint_sha256', 'unknown')}`",
        f"Worktree dirty: `{manifest.get('dirty_worktree', 'unknown')}`; "
        f"source fingerprint: `{manifest.get('source_fingerprint_sha256', 'unknown')}`",
        "",
        "## Metrics",
        "",
        "| Metric | Numerator | Denominator | Result |",
        "|---|---:|---:|---:|",
    ]
    for key in ("business_end_to_end_accuracy", "business_result_accuracy", "strict_result_exact_match", "sql_semantic_accuracy",
                "execution_success", "false_clarification_abstention_rate", "supported_noncompletion_rate",
                "validation_blocked_supported_rate", "safe_unsupported_abstention",
                "valid_clarification_abstention_rate", "repair_recovery_rate", "jev_table_recall_at_5",
                "final_selected_schema_coverage"):
        item = metrics[key]
        value = "N/A" if item.get("value") is None else f"{item['value']:.3f}"
        lines.append(f"| {key.replace('_', ' ')} | {item['numerator']} | {item['denominator']} | {value} |")
    lines += [
        "",
        f"Unsafe executions: **{metrics['unsafe_execution_count']}**",
        f"Latency p50/p95 (ms, nearest rank): **{metrics['latency_ms']['p50_nearest_rank']} / {metrics['latency_ms']['p95_nearest_rank']}**",
        f"Provider calls: `{json.dumps(metrics['provider_calls'], sort_keys=True)}`",
        f"Pipeline calls: `{json.dumps(metrics['pipeline_calls'], sort_keys=True)}`",
        "",
        "## Per-case outcomes",
        "",
        "| Case | Business E2E | Strict exact | SQL semantics | Failure |",
        "|---|---|---|---|---|",
    ]
    if metrics["provider_calls"].get("secondary_sql_provider_fallback_submissions", 0):
        lines.append(
            "SQL-generation secondary-provider fallback occurred; treat this as end-to-end SQL Agent evidence, "
            "not a single-SQL-LLM comparison."
        )
    local_fallback_cases = [
        outcome["id"] for outcome in scored.get("cases", [])
        if outcome.get("calls", {}).get("local_codex_fallback_calls", 0)
    ]
    if local_fallback_cases:
        lines.append(
            "Local Codex SQL fallback occurred in " + ", ".join(local_fallback_cases)
            + "; its model identity is not captured, so this is end-to-end SQL Agent evidence, "
            "not a single-SQL-LLM comparison."
        )
    for outcome in scored["cases"]:
        lines.append(
            f"| {outcome['id']} | {outcome.get('business_end_to_end_correct', outcome.get('safe_unsupported_abstention'))} "
            f"| {outcome.get('strict_result_exact_match')} | {outcome.get('sql_semantic_accuracy')} "
            f"| {outcome.get('failure_class') or '—'} |"
        )
    lines += ["", "## Method notes", "", "See [`PROTOCOL.md`](PROTOCOL.md) for metric definitions and applicability rules.", ""]
    jev_failures = sorted({
        (case.get("schema_selection", {}).get("jev_status"),
         case.get("schema_selection", {}).get("jev_http_status"))
        for case in scored.get("cases", [])
        if case.get("schema_selection", {}).get("jev_status") == "failed"
    }, key=lambda item: (str(item[0]), str(item[1])))
    if jev_failures:
        summary = ", ".join(f"HTTP {status}" if status else "failed" for _, status in jev_failures)
        lines.extend(["JEV availability: **FAILED** (" + summary + "); recall@5 is not measurable.", ""])
    blocker = manifest.get("not_run_reason")
    if manifest.get("status") == "NOT_RUN" or blocker:
        lines.extend([
            "## Execution status",
            "",
            "No fresh SQL Agent benchmark case was executed. All fresh-run quality and latency metrics are N/A.",
        ])
        if blocker:
            lines.append(f"Blocker: {blocker}")
        diagnostic = manifest.get("jev_diagnostic")
        if diagnostic:
            lines.append(
                f"JEV diagnostic: {diagnostic.get('status', 'unknown')}; "
                f"HTTP {diagnostic.get('http_status', 'unknown')}; recall@5 is not measurable."
            )
            if diagnostic.get("message"):
                lines.append(f"JEV diagnostic detail: {diagnostic['message']}")
        lines.append("")
    trace_limit = manifest.get("historical_trace_limitation")
    if trace_limit:
        lines.extend(["## Historical trace limitation", "", trace_limit, ""])
    verification = manifest.get("artifact_verification")
    if verification:
        lines.extend([
            "## Artifact verification",
            "",
            f"Offline suite: **{verification.get('status', 'unknown')}** "
            f"({verification.get('passed', 0)} passed, {verification.get('failed', 0)} failed, "
            f"{verification.get('skipped', 0)} skipped).",
            f"Command: `{verification.get('command', 'not recorded')}`",
            f"Fresh pilot execution: **{verification.get('fresh_pilot_status', 'not recorded')}**.",
            f"Database preflight: **{verification.get('preflight_status', 'not recorded')}** — "
            f"{verification.get('preflight_detail', 'no preflight result recorded')}",
            "",
        ])
    historical = manifest.get("historical_pilot_metrics")
    if historical:
        lines.extend([
            "## Historical pilot (preserved; not rescored)",
            "",
            "These are the original report's figures from its original application revision. "
            "They are not a controlled before/after comparison with this fresh-run status.",
            "",
            "| Historical metric | Result |",
            "|---|---:|",
        ])
        for label, value in historical.items():
            lines.append(f"| {label} | {value} |")
        lines.append("")
    return "\n".join(lines)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    case_set, data = load_json(args.cases), load_json(args.data)
    scored = score_experiment(case_set, data)
    manifest = data.get("manifest", {})
    Path(args.output).write_text(json.dumps(scored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.output).with_suffix(".md").write_text(render_report(case_set, scored, manifest), encoding="utf-8")
