"""AST checks that generated SQL covers the supported parts of a typed request."""
from __future__ import annotations

import re
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


def _relation_nodes(select):
    """Return FROM/JOIN relations for one SELECT without entering predicate subqueries."""
    stack = [select.args.get('from_'), *(select.args.get('joins') or ())]
    tables, nested_selects = [], []
    while stack:
        node = stack.pop()
        if node is None:
            continue
        if isinstance(node, exp.Table):
            tables.append(node)
        elif isinstance(node, exp.Select):
            nested_selects.append(node)
        elif isinstance(node, exp.Subquery):
            child = node.this
            if isinstance(child, exp.Select):
                nested_selects.append(child)
            else:
                stack.extend(child.iter_expressions())
        else:
            stack.extend(node.iter_expressions())
    return tables, nested_selects


def _result_select(tree):
    if isinstance(tree, exp.Select):
        return tree
    if isinstance(tree, exp.Subquery) and isinstance(tree.this, exp.Select):
        return tree.this
    return None


def _active_selects(tree):
    """Follow only result-producing FROM/JOIN and referenced CTE scopes."""
    root = _result_select(tree)
    if root is None:
        return []
    queue = [(root, {})]
    active = []
    visited = set()
    while queue:
        select, inherited_ctes = queue.pop(0)
        if id(select) in visited:
            continue
        visited.add(id(select))
        active.append(select)
        local_ctes = dict(inherited_ctes)
        with_clause = select.args.get('with_')
        if with_clause:
            local_ctes.update({cte.alias_or_name.casefold(): cte.this
                               for cte in with_clause.expressions
                               if isinstance(cte.this, exp.Select)})
        tables, nested = _relation_nodes(select)
        queue.extend((child, local_ctes) for child in nested)
        for table in tables:
            name = table.name.casefold()
            if not table.db and name in local_ctes:
                query = local_ctes[name]
                if isinstance(query, exp.Subquery):
                    query = query.this
                if isinstance(query, exp.Select):
                    queue.append((query, local_ctes))
    return active


def _sources(select):
    result = {}
    tables, _ = _relation_nodes(select)
    for table in tables:
        if table.db and table.name:
            result[table.alias_or_name.casefold()] = f'{table.db}.{table.name}'.casefold()
            result[table.name.casefold()] = f'{table.db}.{table.name}'.casefold()
    return result


def _actual_sources(selects):
    return {f'{table.db}.{table.name}'.casefold()
            for select in selects for table in _relation_nodes(select)[0]
            if table.db and table.name}


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


def _direct_nodes(node):
    """Walk one expression without crossing into another query scope."""
    stack = [node] if node is not None else []
    while stack:
        current = stack.pop()
        if isinstance(current, (exp.Select, exp.Subquery)):
            continue
        yield current
        stack.extend(current.iter_expressions())


def _where_predicates(select):
    where = select.args.get('where')
    stack = [where.this] if where is not None else []
    while stack:
        node = stack.pop()
        if isinstance(node, (exp.Select, exp.Subquery)):
            continue
        if isinstance(node, exp.And):
            stack.extend((node.this, node.expression))
        else:
            yield node


def _filtered_columns(selects, schema_sources):
    for select in selects:
        aliases = _sources(select)
        for clause in (select.args.get('where'), select.args.get('having')):
            for node in _direct_nodes(clause):
                if isinstance(node, exp.Column):
                    yield _column_key(node, aliases, schema_sources)


def _field_matches(column, field, aliases, schema_sources):
    source, name = _column_key(column, aliases, schema_sources)
    expected = field.casefold().split('.')
    if len(expected) == 3:
        return source == '.'.join(expected[:2]) and name == expected[2]
    if len(expected) == 2 and expected[0] == 'commerce':
        return source == field.casefold() and name == expected[1]
    return name == expected[-1]


def _field_column_matches(column, field, select, schema_sources):
    aliases = _sources(select)
    if _field_matches(column, field, aliases, schema_sources):
        return True
    expected = field.casefold().split('.')
    if len(expected) != 3 or column.name.casefold() != expected[-1] or not column.table:
        return False
    relations, _ = _relation_nodes(select)
    known_short_names = {table.rsplit('.', 1)[-1] for table in schema_sources}
    cte_aliases = {table.alias_or_name.casefold() for table in relations
                   if not table.db and table.name.casefold() not in known_short_names}
    return column.table.casefold() in cte_aliases


def _filter_present(item, selects, schema_sources, parameters):
    node_type = {
        'eq': exp.EQ, 'ne': exp.NEQ, 'lt': exp.LT, 'lte': exp.LTE,
        'gt': exp.GT, 'gte': exp.GTE,
    }.get(item.operator)
    for select in selects:
        aliases = _sources(select)
        for node in _where_predicates(select):
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


def _projection_and_groups(root, selects, field, schema_sources):
    projected = any(isinstance(node, exp.Column)
                    and _field_column_matches(node, field, root, schema_sources)
                    for node in root.expressions)
    grouped = False
    for select in selects:
        group = select.args.get('group')
        if not group:
            continue
        for expression in group.expressions:
            if isinstance(expression, exp.Literal) and expression.is_int:
                index = int(expression.this) - 1
                expression = select.expressions[index] if 0 <= index < len(select.expressions) else expression
            elif isinstance(expression, exp.Column) and not expression.table:
                projections = [projection for projection in select.expressions
                               if projection.alias_or_name.casefold() == expression.name.casefold()]
                if len(projections) == 1:
                    expression = projections[0].this if isinstance(projections[0], exp.Alias) else projections[0]
            elif isinstance(expression, exp.Alias):
                expression = expression.this
            if isinstance(expression, exp.Column) and _field_column_matches(
                    expression, field, select, schema_sources):
                grouped = True
                break
    return projected, grouped


def _time_grain_in_select(select, grain, intent, schema_sources):
    aliases = _sources(select)
    date_columns = set().union(*(columns for _, columns in _date_column_groups(intent)))

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

    selected_indexes = {index for index, expression in enumerate(select.expressions)
                        if is_requested_truncation(expression)}
    if not selected_indexes:
        return False, set()
    group = select.args.get('group')
    grouped_indexes = set()
    if group:
        for expression in group.expressions:
            if isinstance(expression, exp.Literal) and expression.is_int:
                index = int(expression.this) - 1
                if 0 <= index < len(select.expressions):
                    grouped_indexes.add(index)
            elif isinstance(expression, exp.Column) and not expression.table:
                grouped_indexes.update(index for index, projection in enumerate(select.expressions)
                                       if projection.alias_or_name.casefold() == expression.name.casefold())
            elif is_requested_truncation(expression):
                grouped_indexes.update(index for index in selected_indexes
                                       if (select.expressions[index].this
                                           if isinstance(select.expressions[index], exp.Alias)
                                           else select.expressions[index]) == expression)
    return bool(selected_indexes & grouped_indexes), selected_indexes


def _time_grain_present(root, selects, grain, intent, schema_sources):
    for select in selects:
        grouped, indexes = _time_grain_in_select(select, grain, intent, schema_sources)
        if not grouped:
            continue
        grain_names = {select.expressions[index].alias_or_name.casefold()
                       for index in indexes
                       if select.expressions[index].alias_or_name}
        if select is root:
            return True
        with_clause = root.args.get('with_')
        cte_names = {cte.alias_or_name.casefold() for cte in (with_clause.expressions if with_clause else ())
                     if cte.this is select}
        root_relations, _ = _relation_nodes(root)
        cte_aliases = {table.alias_or_name.casefold() for table in root_relations
                       if table.name.casefold() in cte_names}
        root_grain_indexes = {index for index, expression in enumerate(root.expressions)
                              if isinstance(expression, exp.Column)
                              and expression.name.casefold() in grain_names}
        root_projects_grain = bool(root_grain_indexes)
        root_projects_cte_grain = {index for index, expression in enumerate(root.expressions)
                                   if isinstance(expression, exp.Column)
                                   and expression.name.casefold() in grain_names
                                   and (expression.table.casefold() in cte_aliases
                                        or (not expression.table and len(cte_aliases) == 1))}
        root_aggregates = any(isinstance(node, exp.AggFunc)
                              for expression in root.expressions
                              for node in _direct_nodes(expression))
        root_groups_grain = False
        group = root.args.get('group')
        if group:
            for expression in group.expressions:
                if isinstance(expression, exp.Literal) and expression.is_int:
                    if int(expression.this) - 1 in root_projects_cte_grain:
                        root_groups_grain = True
                elif (isinstance(expression, exp.Column) and not expression.table
                      and expression.name.casefold() in grain_names):
                    root_groups_grain = True
                elif (isinstance(expression, exp.Column)
                      and expression.table.casefold() in cte_aliases
                      and expression.name.casefold() in grain_names):
                    root_groups_grain = True
        if root_projects_cte_grain:
            return not root_aggregates or root_groups_grain
        if root_projects_grain:
            return None
    return False


def _date_column_groups(intent):
    groups = []
    for metric in intent.metrics:
        definition = get_metric_definition(metric)
        dimensions = set(definition.get('dimensions', ()))
        candidates = {pair for pair in APPROVED_DATE_COLUMNS if pair[1] in dimensions}
        if not candidates:
            continue
        source_text = re.sub(r'\([^)]*\)', '', str(definition.get('source', '')))
        metric_sources = set(re.findall(r'commerce\.[a-z][a-z0-9_]*', source_text))
        source_candidates = {pair for pair in candidates if pair[0] in metric_sources}
        groups.append((metric, source_candidates or candidates))
    return groups or [(None, set(APPROVED_DATE_COLUMNS))]


def _date_bound_present(selects, columns, schema_sources, parameters, operator, expected):
    kind = {'gte': exp.GTE, 'lt': exp.LT}.get(operator)
    for select in selects:
        aliases = _sources(select)
        for node in _where_predicates(select):
            if not isinstance(node, kind) or not isinstance(node.this, exp.Column):
                continue
            if _column_key(node.this, aliases, schema_sources) not in columns:
                continue
            value = _parameter_value(node.expression, parameters)
            if value is not _MISSING and _same_value(value, expected):
                return True
    return False


def _join_present(selects, left, right, schema_sources):
    for select in selects:
        aliases = _sources(select)
        for join in select.args.get('joins') or ():
            on = join.args.get('on')
            if not on:
                continue
            for node in _direct_nodes(on):
                if not isinstance(node, exp.EQ):
                    continue
                if not isinstance(node.this, exp.Column) or not isinstance(node.expression, exp.Column):
                    continue
                pair = {_column_key(node.this, aliases, schema_sources),
                        _column_key(node.expression, aliases, schema_sources)}
                if pair == {left, right}:
                    return True
    return False


def _customer_quantity_rank_status(root, selects, schema_sources):
    """Verify the one legacy custom ranking grammar supported by intent fallback."""
    if len(selects) != 1 or root.args.get('with_'):
        return None
    if root.args.get('where') or root.args.get('having'):
        return False
    sources = _actual_sources(selects)
    required = {'commerce.orders', 'commerce.order_items'}
    if not required <= sources:
        return False
    if not _join_present(selects, ('commerce.orders', 'order_id'),
                         ('commerce.order_items', 'order_id'), schema_sources):
        return False
    customer_indexes = [index for index, expression in enumerate(root.expressions)
                        if isinstance(expression.this if isinstance(expression, exp.Alias) else expression, exp.Column)
                        and _field_column_matches(
                            expression.this if isinstance(expression, exp.Alias) else expression,
                            'commerce.orders.customer_id', root, schema_sources)]
    if len(customer_indexes) != 1:
        return False
    group = root.args.get('group')
    if not group or len(group.expressions) != 1:
        return False

    group_expression = group.expressions[0]
    if isinstance(group_expression, exp.Literal) and group_expression.is_int:
        index = int(group_expression.this) - 1
        group_expression = root.expressions[index] if 0 <= index < len(root.expressions) else group_expression
    elif isinstance(group_expression, exp.Column) and not group_expression.table:
        matches = [projection for projection in root.expressions
                   if projection.alias_or_name.casefold() == group_expression.name.casefold()]
        group_expression = matches[0] if len(matches) == 1 else group_expression
    group_expression = group_expression.this if isinstance(group_expression, exp.Alias) else group_expression
    if not (isinstance(group_expression, exp.Column)
            and _field_column_matches(group_expression, 'commerce.orders.customer_id', root, schema_sources)):
        return False

    quantity_indexes = []
    for index, projection in enumerate(root.expressions):
        expression = projection.this if isinstance(projection, exp.Alias) else projection
        if (isinstance(expression, exp.Sum) and isinstance(expression.this, exp.Column)
                and _field_column_matches(expression.this, 'commerce.order_items.quantity', root, schema_sources)):
            quantity_indexes.append(index)
    if len(quantity_indexes) != 1 or len(root.expressions) != 2:
        return False

    order = root.args.get('order')
    if not order or not order.expressions:
        return False
    first = order.expressions[0]
    if not first.args.get('desc'):
        return False
    ranking = first.this
    if isinstance(ranking, exp.Literal) and ranking.is_int:
        index = int(ranking.this) - 1
        ranking = root.expressions[index] if 0 <= index < len(root.expressions) else ranking
    elif isinstance(ranking, exp.Column) and not ranking.table:
        matches = [projection for projection in root.expressions
                   if projection.alias_or_name.casefold() == ranking.name.casefold()]
        ranking = matches[0] if len(matches) == 1 else ranking
    ranking = ranking.this if isinstance(ranking, exp.Alias) else ranking
    if not (isinstance(ranking, exp.Sum) and isinstance(ranking.this, exp.Column)
            and _field_column_matches(ranking.this, 'commerce.order_items.quantity', root, schema_sources)):
        return False
    limit = root.args.get('limit')
    try:
        return int(limit.expression.this) == 1
    except (AttributeError, TypeError, ValueError):
        return False


def verify_query_contract(intent: QueryIntent, sql: str, parameters, schema: dict[str, set[str]]) -> QueryContractResult:
    """Verify obligations represented in QueryIntent; unknown checks fail inconclusive."""
    try:
        tree = parse_one(sql, read='postgres')
    except Exception as error:
        return QueryContractResult('inconclusive', (f'SQL AST could not be checked: {type(error).__name__}',))
    root = _result_select(tree)
    if root is None:
        return QueryContractResult('inconclusive', ('SQL result shape is not a SELECT.',))
    selects = _active_selects(tree)
    schema_sources = {table.casefold(): {column.casefold() for column in columns}
                      for table, columns in schema.items()}
    actual_sources = _actual_sources(selects)
    issues = []
    if intent.metrics:
        try:
            validate_metric_definitions(sql, set(intent.metrics), parameters, schema,
                                        question=intent.original_question)
        except MetricDefinitionError as error:
            issues.append('Canonical metric validation failed: ' + str(error))
    if intent.unverified_metric_request == 'sum of purchased item quantity by customer':
        quantity_rank = _customer_quantity_rank_status(root, selects, schema_sources)
        if quantity_rank is None:
            return QueryContractResult('inconclusive',
                                       ('Customer quantity ranking uses an unsupported SQL result shape.',))
        if not quantity_rank:
            issues.append('Customer quantity ranking must group customers and rank SUM(order_items.quantity) descending with LIMIT 1.')
    for source in intent.requested_sources:
        if source.provenance == 'ontology_required' and source.name.casefold() not in actual_sources:
            issues.append(f"Required source missing: {source.name}")
    if intent.explicit_source_restriction:
        allowed = {source.name.casefold() for source in intent.requested_sources}
        excess = actual_sources - allowed
        if excess:
            issues.append('SQL broadens the explicit source restriction: ' + ', '.join(sorted(excess)))

    for dimension in intent.dimensions:
        projected, grouped = _projection_and_groups(root, selects, dimension, schema_sources)
        if not projected or (intent.operation != 'list' and not grouped):
            issues.append(f'Requested dimension is not selected and grouped: {dimension}')

    for item in intent.filters:
        if not _filter_present(item, selects, schema_sources, parameters):
            issues.append(f'Requested filter is missing or changed: {item.field} {item.operator}')

    if intent.time_scope and intent.time_scope.mode == 'range':
        for interval in intent.time_scope.ranges:
            for metric, columns in _date_column_groups(intent):
                if (not _date_bound_present(selects, columns, schema_sources, parameters, 'gte', interval.start)
                        or not _date_bound_present(selects, columns, schema_sources, parameters,
                                                   'lt', interval.end_exclusive)):
                    metric_label = f' for metric {metric}' if metric else ''
                    issues.append(f'Requested half-open date range is missing{metric_label}: '
                                  f'{interval.start}/{interval.end_exclusive}')
    elif intent.time_scope and intent.time_scope.mode == 'all':
        filtered_columns = set(_filtered_columns(selects, schema_sources))
        if filtered_columns & APPROVED_DATE_COLUMNS:
            issues.append('An unrestricted time scope must not add a date predicate')
    elif intent.time_scope and intent.time_scope.mode not in {'all', 'unknown'}:
        return QueryContractResult('inconclusive', (f"Time mode {intent.time_scope.mode} is not verifiable here.",))

    if intent.time_grain:
        grain_result = _time_grain_present(root, selects, intent.time_grain, intent, schema_sources)
        if grain_result is None:
            return QueryContractResult('inconclusive', ('Time-grain lineage through this query shape could not be established.',))
        if not grain_result:
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
        if any(name == 'region' for _, name in _filtered_columns(selects, schema_sources)):
            issues.append('All-region coverage must not add a region predicate')

    if intent.geographic_basis in {'order_destination', 'customer_profile'}:
        address = ('commerce.orders', 'zip') if intent.geographic_basis == 'order_destination' else ('commerce.customers', 'zip')
        if not _join_present(selects, address, ('commerce.geography', 'zip'), schema_sources):
            issues.append('Geographic ZIP join does not match the selected attribution basis')

    return QueryContractResult('incomplete' if issues else 'verified', tuple(issues))


def require_query_contract(intent: QueryIntent, sql: str, parameters, schema: dict[str, set[str]]) -> None:
    result = verify_query_contract(intent, sql, parameters, schema)
    if result.status != 'verified':
        raise QueryContractError('Semantic contract ' + result.status + ': ' + '; '.join(result.issues))
