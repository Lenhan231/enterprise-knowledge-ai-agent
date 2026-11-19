"""AST checks that generated SQL covers the supported parts of a typed request."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlglot import exp, parse_one

from core.analytics.metric_ontology import get_metric_definition
from core.analytics.metric_validation import MetricDefinitionError, validate_metric_definitions
from core.analytics.sql_validation import APPROVED_DATE_COLUMNS, SQLValidationError
from core.agents.sql.query_intent import QueryIntent


@dataclass(frozen=True)
class QueryContractResult:
    status: str
    issues: tuple[str, ...] = ()


class QueryContractError(SQLValidationError):
    """Generated SQL is safe to parse but does not satisfy the user's intent."""


def _sources(tree):
    result = {}
    for table in tree.find_all(exp.Table):
        if table.db and table.name:
            result[table.alias_or_name.casefold()] = f'{table.db}.{table.name}'.casefold()
            result[table.name.casefold()] = f'{table.db}.{table.name}'.casefold()
    return result


def _column_key(column, aliases, schema_sources):
    name = column.name.casefold()
    table = column.table.casefold() if column.table else ''
    source = aliases.get(table) if table else None
    if source:
        return source, name
    if table and table in schema_sources:
        return table, name
    candidates = [source for source, columns in schema_sources.items() if name in columns]
    return (candidates[0], name) if len(candidates) == 1 else (None, name)


def _parameter_value(node, parameters):
    if isinstance(node, exp.Parameter):
        index = node.this.this if isinstance(node.this, exp.Literal) else None
        try:
            return parameters[int(index) - 1]
        except (TypeError, ValueError, IndexError):
            return _MISSING
    if isinstance(node, exp.Placeholder):
        return _MISSING
    if isinstance(node, exp.Literal):
        return node.this if node.is_string else float(node.this) if '.' in node.this else int(node.this)
    if isinstance(node, exp.Boolean):
        return node.this
    if isinstance(node, exp.Null):
        return None
    return _MISSING


_MISSING = object()


def _same_value(left, right):
    if isinstance(right, date):
        try:
            return date.fromisoformat(str(left)[:10]) == right
        except ValueError:
            return False
    return str(left).casefold() == str(right).casefold()


def _where_predicates(tree):
    for where in tree.find_all(exp.Where):
        stack = [where.this]
        while stack:
            node = stack.pop()
            if isinstance(node, exp.And):
                stack.extend((node.this, node.expression))
            else:
                yield node


def _filtered_columns(tree, aliases, schema_sources):
    for predicate in (*tree.find_all(exp.Where), *tree.find_all(exp.Having)):
        for column in predicate.find_all(exp.Column):
            yield _column_key(column, aliases, schema_sources)


def _field_matches(column, field, aliases, schema_sources):
    source, name = _column_key(column, aliases, schema_sources)
    expected = field.casefold().split('.')
    if len(expected) == 3:
        return source == '.'.join(expected[:2]) and name == expected[2]
    if len(expected) == 2 and expected[0] == 'commerce':
        return source == field.casefold() and name == expected[1]
    return name == expected[-1]


def _filter_present(item, tree, aliases, schema_sources, parameters):
    node_type = {
        'eq': exp.EQ, 'ne': exp.NEQ, 'lt': exp.LT, 'lte': exp.LTE,
        'gt': exp.GT, 'gte': exp.GTE,
    }.get(item.operator)
    for node in _where_predicates(tree):
        if item.operator in {'is_null', 'is_not_null'}:
            if not isinstance(node, (exp.Is, exp.Not)):
                continue
            column = node.this if isinstance(node, exp.Is) else node.this.this if isinstance(node.this, exp.Is) else None
            if isinstance(column, exp.Column) and _field_matches(column, item.field, aliases, schema_sources):
                return (item.operator == 'is_null') == isinstance(node, exp.Is)
            continue
        if item.operator == 'in':
            if not isinstance(node, exp.In) or not isinstance(node.this, exp.Column):
                continue
            if not _field_matches(node.this, item.field, aliases, schema_sources):
                continue
            values = [_parameter_value(value, parameters) for value in node.expressions]
            if all(value is not _MISSING for value in values):
                expected = item.value if isinstance(item.value, list) else [item.value]
                return len(values) == len(expected) and all(any(_same_value(a, b) for b in expected) for a in values)
        if node_type and isinstance(node, node_type) and isinstance(node.this, exp.Column):
            if not _field_matches(node.this, item.field, aliases, schema_sources):
                continue
            actual = _parameter_value(node.expression, parameters)
            if actual is not _MISSING and _same_value(actual, item.value):
                return True
    return False


def _projection_and_groups(tree, field, aliases, schema_sources):
    projected = any(isinstance(node, exp.Column)
                    and _field_matches(node, field, aliases, schema_sources)
                    for select in tree.find_all(exp.Select) for node in select.expressions)
    grouped = any(isinstance(node, exp.Column)
                  and _field_matches(node, field, aliases, schema_sources)
                  for group in tree.find_all(exp.Group) for node in group.expressions)
    return projected, grouped


def _time_grain_present(tree, grain, intent, aliases, schema_sources):
    date_columns = _date_columns(intent)

    def is_requested_truncation(node):
        if isinstance(node, exp.Alias):
            node = node.this
        if not isinstance(node, exp.TimestampTrunc):
            return False
        unit = node.args.get('unit')
        column = node.this
        if (not isinstance(unit, exp.Var) or unit.this.casefold() != grain
                or not isinstance(column, exp.Column)):
            return False
        return _column_key(column, aliases, schema_sources) in date_columns

    selected = any(is_requested_truncation(expression)
                   for expression in tree.selects)
    group = tree.args.get('group')
    grouped = False
    if group:
        for expression in group.expressions:
            if isinstance(expression, exp.Literal) and expression.is_int:
                index = int(expression.this) - 1
                if 0 <= index < len(tree.selects):
                    expression = tree.selects[index]
            if is_requested_truncation(expression):
                grouped = True
                break
    return selected, grouped


def _date_columns(intent):
    columns = set()
    for metric in intent.metrics:
        dimensions = set(get_metric_definition(metric).get('dimensions', ()))
        columns.update(pair for pair in APPROVED_DATE_COLUMNS if pair[1] in dimensions)
    if not columns:
        columns.update(APPROVED_DATE_COLUMNS)
    return columns


def _date_bound_present(tree, columns, aliases, schema_sources, parameters, operator, expected):
    kind = {'gte': exp.GTE, 'lt': exp.LT}.get(operator)
    for node in _where_predicates(tree):
        if not isinstance(node, kind) or not isinstance(node.this, exp.Column):
            continue
        if _column_key(node.this, aliases, schema_sources) not in columns:
            continue
        value = _parameter_value(node.expression, parameters)
        if value is not _MISSING and _same_value(value, expected):
            return True
    return False


def _join_present(tree, left, right, aliases, schema_sources):
    for join in tree.find_all(exp.Join):
        on = join.args.get('on')
        if not on:
            continue
        for node in on.find_all(exp.EQ):
            if not isinstance(node.this, exp.Column) or not isinstance(node.expression, exp.Column):
                continue
            pair = {_column_key(node.this, aliases, schema_sources),
                    _column_key(node.expression, aliases, schema_sources)}
            if pair == {left, right}:
                return True
    return False


def verify_query_contract(intent: QueryIntent, sql: str, parameters, schema: dict[str, set[str]]) -> QueryContractResult:
    """Verify obligations represented in QueryIntent; unknown checks fail inconclusive."""
    try:
        tree = parse_one(sql, read='postgres')
    except Exception as error:
        return QueryContractResult('inconclusive', (f'SQL AST could not be checked: {type(error).__name__}',))
    aliases = _sources(tree)
    schema_sources = {table.casefold(): {column.casefold() for column in columns}
                      for table, columns in schema.items()}
    actual_sources = set(aliases.values())
    issues = []
    if intent.metrics:
        try:
            validate_metric_definitions(sql, set(intent.metrics), parameters, schema,
                                        question=intent.original_question)
        except MetricDefinitionError as error:
            issues.append('Canonical metric validation failed: ' + str(error))
    for source in intent.requested_sources:
        if source.provenance == 'ontology_required' and source.name.casefold() not in actual_sources:
            issues.append(f"Required source missing: {source.name}")
    if intent.explicit_source_restriction:
        allowed = {source.name.casefold() for source in intent.requested_sources}
        excess = actual_sources - allowed
        if excess:
            issues.append('SQL broadens the explicit source restriction: ' + ', '.join(sorted(excess)))

    for dimension in intent.dimensions:
        projected, grouped = _projection_and_groups(tree, dimension, aliases, schema_sources)
        if not projected or (intent.operation != 'list' and not grouped):
            issues.append(f'Requested dimension is not selected and grouped: {dimension}')

    for item in intent.filters:
        if not _filter_present(item, tree, aliases, schema_sources, parameters):
            issues.append(f'Requested filter is missing or changed: {item.field} {item.operator}')

    if intent.time_scope and intent.time_scope.mode == 'range':
        columns = _date_columns(intent)
        for interval in intent.time_scope.ranges:
            if (not _date_bound_present(tree, columns, aliases, schema_sources, parameters, 'gte', interval.start)
                    or not _date_bound_present(tree, columns, aliases, schema_sources, parameters,
                                               'lt', interval.end_exclusive)):
                issues.append(f'Requested half-open date range is missing: {interval.start}/{interval.end_exclusive}')
    elif intent.time_scope and intent.time_scope.mode == 'all':
        filtered_columns = set(_filtered_columns(tree, aliases, schema_sources))
        if filtered_columns & APPROVED_DATE_COLUMNS:
            issues.append('An unrestricted time scope must not add a date predicate')
    elif intent.time_scope and intent.time_scope.mode not in {'all', 'unknown'}:
        return QueryContractResult('inconclusive', (f"Time mode {intent.time_scope.mode} is not verifiable here.",))

    if intent.time_grain:
        selected, grouped = _time_grain_present(tree, intent.time_grain, intent, aliases, schema_sources)
        if not selected or not grouped:
            issues.append(f'Requested {intent.time_grain} time grain is not projected and grouped.')

    if intent.ranking:
        order = tree.args.get('order')
        if not order or not order.expressions:
            issues.append('Requested ranking order is missing')
        else:
            first = order.expressions[0]
            expected_desc = intent.ranking.direction == 'desc'
            if bool(first.args.get('desc')) != expected_desc:
                issues.append('Requested ranking direction changed')
            ranking_expression = first.this
            if isinstance(ranking_expression, exp.Column) and not ranking_expression.table:
                projections = [projection for projection in tree.selects
                               if projection.alias_or_name.casefold() == ranking_expression.name.casefold()]
                if len(projections) == 1:
                    ranking_expression = projections[0].this if isinstance(projections[0], exp.Alias) else projections[0]
            elif isinstance(ranking_expression, exp.Literal) and ranking_expression.is_int:
                index = int(ranking_expression.this) - 1
                if 0 <= index < len(tree.selects):
                    projection = tree.selects[index]
                    ranking_expression = projection.this if isinstance(projection, exp.Alias) else projection
            ranking_query = tree.copy()
            if isinstance(ranking_query, exp.Select):
                ranking_query.set('expressions', [ranking_expression.copy().as_(intent.ranking.metric)])
                try:
                    validate_metric_definitions(
                        ranking_query.sql(dialect='postgres'), {intent.ranking.metric}, parameters,
                        schema, question=intent.original_question)
                except MetricDefinitionError as error:
                    issues.append('Ranking metric validation failed: ' + str(error))
            else:
                issues.append('Ranking metric could not be resolved in the output query')
            if intent.ranking.limit is not None:
                limit = tree.args.get('limit')
                try:
                    actual_limit = int(limit.expression.this)
                except (AttributeError, TypeError, ValueError):
                    actual_limit = None
                if actual_limit != intent.ranking.limit:
                    issues.append('Requested ranking limit changed')

    if intent.geographic_coverage == 'all':
        if any(name == 'region' for _, name in _filtered_columns(tree, aliases, schema_sources)):
            issues.append('All-region coverage must not add a region predicate')

    if intent.geographic_basis in {'order_destination', 'customer_profile'}:
        address = ('commerce.orders', 'zip') if intent.geographic_basis == 'order_destination' else ('commerce.customers', 'zip')
        if not _join_present(tree, address, ('commerce.geography', 'zip'), aliases, schema_sources):
            issues.append('Geographic ZIP join does not match the selected attribution basis')

    return QueryContractResult('incomplete' if issues else 'verified', tuple(issues))


def require_query_contract(intent: QueryIntent, sql: str, parameters, schema: dict[str, set[str]]) -> None:
    result = verify_query_contract(intent, sql, parameters, schema)
    if result.status != 'verified':
        raise QueryContractError('Semantic contract ' + result.status + ': ' + '; '.join(result.issues))
