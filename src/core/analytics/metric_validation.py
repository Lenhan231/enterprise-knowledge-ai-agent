"""Conservative checks of ontology formulas before executing model-generated SQL."""
from __future__ import annotations

import re
import calendar
from datetime import date, timedelta

from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import Scope, traverse_scope

from core.analytics.metric_ontology import METRIC_ONTOLOGY, get_metric_definition, _normalize


class MetricDefinitionError(ValueError):
    """A query cannot be verified against a requested canonical metric."""

    def __init__(self, message, *, code="formula_violation", clarification=False):
        super().__init__(message)
        self.code, self.clarification = code, clarification


def _inventory_question(question):
    return re.sub(r'\b(\d{1,2})/(\d{1,2})/((?:19|20)\d{2})\b',
                  lambda match: f'{match[3]}-{int(match[2]):02}-{int(match[1]):02}', _normalize(question))


def inventory_explicit_dates(question):
    question = _inventory_question(question)
    dates = [date.fromisoformat(value) for value in re.findall(r'\b\d{4}-\d{2}-\d{2}\b', question)]
    years = set(re.findall(r'\b(?:19|20)\d{2}\b', question))
    months = {name.casefold():index for index,name in enumerate(calendar.month_name) if name}
    for month, day, year in re.findall(r'\b('+'|'.join(months)+r')\s+(\d{1,2})\b(?:,?\s+((?:19|20)\d{2})\b)?', question):
        year = year or (next(iter(years)) if len(years)==1 else None)
        if year:
            dates.append(date(int(year), months[month], int(day)))
    return sorted(set(dates))


def inventory_time_scope(question):
    """Resolve explicit historical periods; ranges retain separate snapshot observations."""
    question = _inventory_question(question)
    dates = inventory_explicit_dates(question)
    if dates:
        return ('snapshot', dates[0].isoformat(), None) if len(dates) == 1 else (
            'range', dates[0].isoformat(), dates[-1].isoformat())
    month = re.search(r'\b('+'|'.join(calendar.month_name[1:]).lower()+r')\s+((?:19|20)\d{2})\b', question)
    numeric = re.search(r'tháng\s+(\d{1,2})\s+(?:năm\s+)?((?:19|20)\d{2})\b', question)
    quarter = re.search(r'(?:\bq|quarter\s*|quý\s*)([1-4])\s+(?:of\s+|năm\s+)?((?:19|20)\d{2})\b', question)
    years = set(re.findall(r'\b(?:19|20)\d{2}\b', question))
    if len(years) != 1:
        return None
    year = int(next(iter(years)))
    if month or numeric:
        first = list(calendar.month_name).index(month[1].title()) if month else int(numeric[1])
        last = first
    elif quarter:
        first = (int(quarter[1])-1)*3+1
        last = first+2
    else:
        first, last = 1, 12
    return 'range', date(year, first, 1).isoformat(), date(year, last, calendar.monthrange(year, last)[1]).isoformat()


def inventory_comparison_dates(question):
    if re.search(r'\bchange\b|\bdelta\b|\bdifference\b|thay đổi|chênh lệch', _normalize(question)):
        dates = inventory_explicit_dates(question)
        if len(dates) == 2:
            return tuple(d.isoformat() for d in dates)
    return None


def _has_explicit_time_scope(question):
    text = _normalize(question or "")
    months = "january|february|march|april|may|june|july|august|september|october|november|december"
    return bool(re.search(
        r"\b(?:19|20)\d{2}\b|\b\d{4}-\d{2}-\d{2}\b|"
        r"\b(?:today|yesterday|tomorrow|ytd|mtd|qtd|latest|most recent|to date|currently)\b|"
        r"\b(?:this|last|past|previous|current)\s+(?:day|week|month|quarter|year)\b|"
        r"\b(?:" + months + r")\b|"
        r"\b(?:hôm nay|hôm qua|ngày mai|tuần này|tuần trước|tháng này|tháng trước|"
        r"năm nay|năm trước|quý này|quý trước|mới nhất|gần nhất|đến nay|hiện tại|đang hoạt động)\b|"
        r"\b(?:tháng|quý|năm)\s*(?:\d{1,2}|\d{4})\b",
        text,
    ))


def _unrequested_date_filter(tree, question):
    if not question or _has_explicit_time_scope(question):
        return False
    for scope in traverse_scope(tree):
        select = scope.expression
        predicates = list(_conjuncts(select.args.get("where")))
        predicates.extend(
            predicate
            for join in select.args.get("joins", [])
            for predicate in _conjuncts(join.args.get("on"))
        )
        for predicate in predicates:
            date_columns = [
                column for column in predicate.find_all(exp.Column)
                if re.fullmatch(r"(?:date|[a-z_]*_date)", column.name, re.I)
            ]
            has_bound = any(isinstance(node, (exp.Literal, exp.Parameter)) for node in predicate.walk())
            if date_columns and has_bound:
                return True
    return False


def validate_stock_comparison(sql, parameters, dates):
    """Verify a two-observation identity calculation, never a period stock aggregate."""
    tree = parse_one(sql, read='postgres')
    scopes = list(traverse_scope(tree))
    if len(scopes) != 1 or not isinstance(tree, exp.Select):
        raise MetricDefinitionError('Stock comparison requires one checked product-grain SELECT.')
    scope = scopes[0]
    canonical = lambda node: _canonical(node, scope, parameters, {})
    sources = [source for _, source in scope.selected_sources.values()]
    joins = tree.args.get('joins', [])
    if (len(sources) != 2 or any(not isinstance(s, exp.Table) for s in sources)
            or {s.db+'.'+s.name for s in sources} != {'commerce.inventory','commerce.products'}
            or len(joins) != 1 or joins[0].side or joins[0].kind not in {'','INNER'}):
        raise MetricDefinitionError('Stock comparison requires the approved inventory/products relationship.')
    expected_join = parse_one('commerce.inventory.product_id = commerce.products.product_id', read='postgres')
    if canonical(joins[0].args['on']) != expected_join:
        raise MetricDefinitionError('Stock comparison changed the product join.')
    snapshot = exp.column('snapshot_date', table='inventory', db='commerce')
    stock = exp.column('stock_on_hand', table='inventory', db='commerce')
    observations = [exp.Max(this=exp.Case(ifs=[exp.If(this=exp.EQ(this=snapshot.copy(), expression=exp.convert(d)),
                        true=stock.copy())])) for d in dates]
    expected = dict(before_date=exp.convert(dates[0]), after_date=exp.convert(dates[1]),
                    stock_before=observations[0], stock_after=observations[1],
                    stock_delta=exp.Sub(this=observations[1].copy(), expression=observations[0].copy()))
    projected = {p.alias_or_name: canonical(p) for p in tree.selects}
    if len(projected) != len(tree.selects) or any(projected.get(k) != v for k,v in expected.items()):
        raise MetricDefinitionError('Stock comparison changed dates, operands, subtraction direction or NULL semantics.')
    dimensions = {k:v for k,v in projected.items() if k not in expected}
    allowed = {'product_id','product_name','category','segment','size','color'}
    if 'product_id' not in dimensions or any(k not in allowed or v != exp.column(k,
            table='inventory' if k == 'product_id' else 'products', db='commerce') for k,v in dimensions.items()):
        raise MetricDefinitionError('Stock comparison must preserve product identity and canonical attributes.')
    group = tree.args.get('group')
    if not group or {canonical(g).sql() for g in group.expressions} != {v.sql() for v in dimensions.values()}:
        raise MetricDefinitionError('Stock comparison changed product grain.')
    required_dates = exp.In(this=snapshot, expressions=[exp.convert(d) for d in dates])
    filters = [canonical(p) for p in _conjuncts(tree.args.get('where'))]
    if required_dates not in filters:
        raise MetricDefinitionError('Stock comparison must restrict observations to both exact dates.')
    for predicate in filters:
        if predicate == required_dates:
            continue
        if (not isinstance(predicate, (exp.EQ,exp.LT,exp.LTE,exp.GT,exp.GTE,exp.In))
                or not isinstance(predicate.this, exp.Column) or predicate.this.name not in allowed
                or predicate.this.table != ('inventory' if predicate.this.name == 'product_id' else 'products')
                or any(not isinstance(v, (exp.Literal,exp.Boolean)) for v in
                       (predicate.expressions if isinstance(predicate,exp.In) else [predicate.expression]))):
            raise MetricDefinitionError('Comparison population filters must use explicit product attributes.')
    having = tree.args.get('having')
    intersection = exp.EQ(this=exp.Count(this=exp.Distinct(expressions=[snapshot.copy()]), big_int=True), expression=exp.Literal.number(2))
    if not having or canonical(having.this) != intersection:
        raise MetricDefinitionError('Stock comparison requires observations on both dates; missing rows are not zero.')
    if any(tree.args.get(k) for k in ('with_','distinct','qualify','offset')):
        raise MetricDefinitionError('Stock comparison added an unverified result restriction.')
    return {'stock_on_hand': {**get_metric_definition('stock_on_hand'), 'representation':'two_snapshot_comparison'}}


def validate_metric_request(question, metric_names):
    question = _inventory_question(question)
    inventory = [get_metric_definition(name) for name in metric_names
                 if get_metric_definition(name).get('domain') == 'inventory_management']
    if inventory and len(inventory) != len(metric_names):
        raise MetricDefinitionError('Inventory snapshots and unrelated metric grains require separate queries.',
                                    code='incompatible_grain', clarification=True)
    for definition in inventory:
        if definition['definition_status'] != 'executable':
            raise MetricDefinitionError(definition.get('clarification', 'No reviewed definition is available.'),
                                        code='metric_unresolved', clarification=True)
        if definition['approval_status'] not in {'team_accepted', 'business_approved'}:
            raise MetricDefinitionError('This inventory definition has not been accepted for use.',
                                        code='metric_unapproved', clarification=True)
    if inventory and re.search(r'latest|mới nhất|gần nhất', question, re.I) and re.search(r'\b(?:19|20)\d{2}\b', question):
        raise MetricDefinitionError('Do you want the latest dataset snapshot or a snapshot within the specified period?',
                                    code='ambiguous_snapshot', clarification=True)
    if inventory:
        for value in re.findall(r'\b\d{4}-\d{2}-\d{2}\b', question):
            try:
                date.fromisoformat(value)
            except ValueError as error:
                raise MetricDefinitionError('Use a valid snapshot date (YYYY-MM-DD).', code='invalid_date_scope', clarification=True) from error
        if not re.search(r'\b\d{4}-\d{2}-\d{2}\b', question) and re.search(
                r'quarter|quý|tháng\s+\d+|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+(?:19|20)\d{2}|last month|last year|tháng trước|năm ngoái', question):
            try:
                scope = inventory_time_scope(question)
            except ValueError:
                scope = None
            if scope is None:
                raise MetricDefinitionError('Specify an exact historical snapshot date or ISO date range for that period.', code='snapshot_required', clarification=True)
    if inventory and not re.search(r'\b(?:19|20)\d{2}\b|latest|histor|trend|snapshot_date|mới nhất|gần nhất|lịch sử|xu hướng', question, re.I):
        raise MetricDefinitionError('The available inventory records are historical. Which snapshot should I use?',
                                    code='snapshot_required', clarification=True)


def _formula(definition, table_columns):
    sources = re.findall(r"commerce\.\w+", definition["source"])
    expression = parse_one(definition["formula"].split(" within ")[0], read="postgres")

    def qualify(node):
        if not isinstance(node, exp.Column):
            return node
        candidates = [source for source in sources if node.name in table_columns[source]
                      and (not node.table or node.table == source.split(".")[1])]
        if not candidates:
            raise MetricDefinitionError(f"Ontology formula has no source for {node.name}")
        return exp.column(node.name, table=candidates[0].split(".")[1], db="commerce")

    return expression.transform(qualify)


def _canonical(node, scope, parameters, used_scopes, path=()):
    used_scopes[id(scope)] = scope
    if isinstance(node, (exp.Alias, exp.Paren)):
        return _canonical(node.this, scope, parameters, used_scopes, path)
    if isinstance(node, exp.Subquery):
        raise MetricDefinitionError("Metric expressions must use a canonical formula or a transparent CTE alias")
    if isinstance(node, exp.Parameter):
        value = parameters[int(node.this.name) - 1]
        return exp.convert(value.isoformat() if hasattr(value, "isoformat") else value)
    if isinstance(node, exp.Column):
        owner = scope
        while owner is not None and node.table.casefold() not in {name.casefold() for name in owner.sources}:
            owner = owner.parent
        source = {name.casefold(): value for name, value in owner.sources.items()}.get(node.table.casefold()) if owner else None
        if isinstance(source, exp.Table):
            return exp.column(node.name.casefold(), table=source.name.casefold(), db=source.db.casefold())
        key = (id(source), node.name.casefold())
        if isinstance(source, Scope) and key not in path:
            projections = [p for p in source.expression.selects if p.alias_or_name.casefold() == node.name.casefold()]
            if len(projections) == 1:
                return _canonical(projections[0], source, parameters, used_scopes, (*path, key))
        raise MetricDefinitionError(f"Cannot verify metric column lineage: {node.sql()}")
    result = node.copy()
    for key, value in node.args.items():
        if isinstance(value, exp.Expression):
            result.set(key, _canonical(value, scope, parameters, used_scopes, path))
        elif isinstance(value, list):
            result.set(key, [_canonical(item, scope, parameters, used_scopes, path)
                             if isinstance(item, exp.Expression) else item for item in value])
    if isinstance(result, exp.Cast) and result.to.this == exp.DataType.Type.DATE and isinstance(result.this, exp.Literal):
        try:
            return exp.convert(date.fromisoformat(result.this.this).isoformat())
        except (ValueError, TypeError):
            pass
    return result


def _conjuncts(node):
    if isinstance(node, (exp.Where, exp.Paren)):
        yield from _conjuncts(node.this)
    elif isinstance(node, exp.And):
        yield from _conjuncts(node.this)
        yield from _conjuncts(node.expression)
    elif node is not None:
        yield node


def _latest_snapshot(value):
    if not isinstance(value, exp.Subquery) or not isinstance(value.this, exp.Select):
        return False
    select = value.this
    source = select.args.get('from_')
    table = source.this if source else None
    if not isinstance(table, exp.Table) or table.db.casefold() != 'commerce' or table.name.casefold() != 'inventory':
        return False
    if any(select.args.get(key) for key in ('joins', 'where', 'group', 'having', 'qualify', 'limit', 'offset', 'distinct', 'with_')):
        return False
    expression = select.selects[0] if len(select.selects) == 1 else None
    if isinstance(expression, exp.Alias):
        expression = expression.this
    column = expression.this if isinstance(expression, exp.Max) else None
    return (isinstance(column, exp.Column) and column.name.casefold() == 'snapshot_date'
            and column.table.casefold() == table.alias_or_name.casefold() and not column.db)


def _snapshot_predicates(scopes, parameters):
    snapshot = exp.column('snapshot_date', table='inventory', db='commerce')
    for scope in scopes:
        for predicate in _conjuncts(scope.expression.args.get('where')):
            if not isinstance(predicate, (exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
                continue
            for column, value, reverse in ((predicate.this, predicate.expression, False),
                                           (predicate.expression, predicate.this, True)):
                if not isinstance(column, exp.Column):
                    continue
                try:
                    if _canonical(column, scope, parameters, {}) == snapshot:
                        yield predicate, value, reverse
                except MetricDefinitionError:
                    continue


def _single_snapshot(scopes, parameters):
    snapshot = exp.column("snapshot_date", table="inventory", db="commerce")
    for scope in scopes:
        group = scope.expression.args.get("group")
        for column in group.expressions if group else ():
            if isinstance(column, exp.Literal) and column.is_int:
                index = int(column.this) - 1
                if 0 <= index < len(scope.expression.selects):
                    column = scope.expression.selects[index]
            if _canonical(column, scope, parameters, {}) == snapshot:
                return True
    for predicate, value, _ in _snapshot_predicates(scopes, parameters):
        if isinstance(predicate, exp.EQ) and (isinstance(value, (exp.Parameter, exp.Literal)) or _latest_snapshot(value)):
            return True
    return False


def _validate_inventory_time(scopes, parameters, question):
    question = _inventory_question(question)
    predicates = list(_snapshot_predicates(scopes, parameters))
    latest = any(isinstance(p, exp.EQ) and _latest_snapshot(value) for p, value, _ in predicates)
    if re.search(r'latest|mới nhất|gần nhất', question, re.I):
        if not latest:
            raise MetricDefinitionError('Use MAX(snapshot_date) from commerce.inventory for the requested latest snapshot.', code='invalid_date_scope')
        return
    dates, lower, upper = [], [], []
    for predicate, value, reverse in predicates:
        try:
            resolved = _canonical(value, scopes[0], parameters, {})
            if not isinstance(resolved, exp.Literal):
                continue
            parsed = date.fromisoformat(str(resolved.this))
        except (ValueError, MetricDefinitionError):
            continue
        if isinstance(predicate, exp.EQ):
            dates.append(parsed)
        else:
            operator = type(predicate)
            if reverse:
                operator = {exp.GT: exp.LT, exp.GTE: exp.LTE, exp.LT: exp.GT, exp.LTE: exp.GTE}[operator]
            if operator in (exp.GTE, exp.GT):
                lower.append(parsed + timedelta(days=int(operator is exp.GT)))
            else:
                upper.append(parsed + timedelta(days=int(operator is exp.LTE)))
    requested = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', question)
    period = inventory_time_scope(question)
    if period and period[0] == 'range' and not requested:
        start, end = date.fromisoformat(period[1]), date.fromisoformat(period[2])
        if lower and upper and max(lower) == start and min(upper) == end + timedelta(days=1):
            return
        if start.month != 1 or start.day != 1 or end.month != 12 or end.day != 31:
            raise MetricDefinitionError('The generated inventory date scope does not match the requested period.', code='invalid_date_scope')
    if requested:
        try:
            expected = [date.fromisoformat(value) for value in requested]
        except ValueError as error:
            raise MetricDefinitionError('Use valid ISO snapshot dates (YYYY-MM-DD).', code='invalid_date_scope', clarification=True) from error
        if len(expected) == 1 and expected[0] in dates:
            return
        start, end = min(expected), max(expected)
    else:
        years = [int(value) for value in re.findall(r'\b(?:19|20)\d{2}\b', question)]
        if not years:
            return
        start, end = date(min(years), 1, 1), date(max(years), 12, 31)
        snapshot = exp.column('snapshot_date', table='inventory', db='commerce')
        for scope in scopes:
            for predicate in _conjuncts(scope.expression.args.get('where')):
                if not isinstance(predicate, exp.EQ):
                    continue
                for extract, value in ((predicate.this, predicate.expression), (predicate.expression, predicate.this)):
                    if not isinstance(extract, exp.Extract) or extract.this.name.upper() != 'YEAR':
                        continue
                    try:
                        year = _canonical(value, scope, parameters, {})
                        if (len(set(years)) == 1 and isinstance(year, exp.Literal) and str(year.this) == str(years[0])
                                and _canonical(extract.expression, scope, parameters, {}) == snapshot):
                            return
                    except MetricDefinitionError:
                        continue
    if not (lower and upper and max(lower) == start and min(upper) == end + timedelta(days=1)):
        raise MetricDefinitionError('The generated inventory date scope does not match the requested period.', code='invalid_date_scope')


def _validate_inventory_metrics(sql, metric_names, parameters, table_columns, question):
    definitions = {name: get_metric_definition(name) for name in metric_names}
    if any(definition.get('domain') != 'inventory_management' for definition in definitions.values()):
        raise MetricDefinitionError('Inventory snapshots and unrelated metric grains require separate queries.', code='incompatible_grain')
    for definition in definitions.values():
        if definition['definition_status'] != 'executable':
            raise MetricDefinitionError(definition.get('clarification', 'No reviewed inventory definition is available.'), code='metric_unresolved', clarification=True)
        if definition['approval_status'] not in {'team_accepted', 'business_approved'}:
            raise MetricDefinitionError('This inventory definition is not accepted for execution.', code='metric_unapproved', clarification=True)
    tree = parse_one(sql, read='postgres')
    if any(table.db and (table.db.casefold() != 'commerce' or table.name.casefold() not in {'inventory', 'products'}) for table in tree.find_all(exp.Table)):
        raise MetricDefinitionError('Inventory metrics support only inventory and canonical product attributes.', code='metric_source_mismatch')
    scopes = list(traverse_scope(tree))
    root = scopes[-1]
    active = {name: definition for name, definition in METRIC_ONTOLOGY.items()
              if definition.get('domain') == 'inventory_management' and definition.get('formula')
              and definition['definition_status'] == 'executable'
              and definition['approval_status'] in {'team_accepted', 'business_approved'}}
    formulas = {name: _formula(definition, table_columns) for name, definition in active.items()}
    scalar = {name: _formula({**definition, 'formula': definition['scalar_formula']}, table_columns)
              for name, definition in active.items() if definition.get('scalar_formula')}
    has_aggregates = any(projection.find(exp.AggFunc) for projection in root.expression.selects)
    scalar_count = (has_aggregates and not root.expression.args.get('group')
                    and all(d['aggregation'] == 'count_distinct' for d in definitions.values())
                    and _single_snapshot([root], parameters))
    if has_aggregates and any(definition['aggregation'] == 'value' for definition in definitions.values()):
        raise MetricDefinitionError('Stored product values and aggregate metrics have incompatible output grains. Request separate results or an explicit mean.', code='incompatible_grain', clarification=True)
    dimensions = set.intersection(*(set(definition['dimensions']) for definition in definitions.values()))
    dimension_sources = {exp.column(column, table=table.split('.')[1], db='commerce').sql()
                         for definition in definitions.values() for table, columns in definition['source_columns'].items()
                         for column in columns if column in dimensions}
    matched, used_scopes, representations = set(), {}, {}
    projected_snapshot = False
    for projection in root.expression.selects:
        if scalar_count and projection.alias_or_name.casefold() == 'snapshot_date' and _latest_snapshot(projection.this) and any(
                isinstance(predicate,exp.EQ) and _latest_snapshot(value)
                for predicate,value,_ in _snapshot_predicates([root],parameters)):
            projected_snapshot = True
            continue
        expression = _canonical(projection, root, parameters, used_scopes)
        if expression == exp.column('snapshot_date', table='inventory', db='commerce') and projection.alias_or_name.casefold() == 'snapshot_date':
            projected_snapshot = True
        if scalar_count and projection.alias_or_name.casefold() == 'snapshot_date' and any(
                isinstance(predicate,exp.EQ) and expression == _canonical(value,root,parameters,{})
                for predicate,value,_ in _snapshot_predicates([root],parameters)):
            projected_snapshot = True
            continue
        matches = {name for name, formula in formulas.items() if expression == formula}
        if not has_aggregates and not root.expression.args.get('group') and not root.expression.args.get('distinct'):
            matches |= {name for name, formula in scalar.items() if expression == formula}
        label = projection.alias.casefold()
        source_label = isinstance(expression, exp.Column) and expression.name == label
        if label in METRIC_ONTOLOGY and label not in matches and not source_label:
            raise MetricDefinitionError(f'Output label {label} conflicts with its canonical metric formula')
        if matches:
            if has_aggregates and any(active[name]['aggregation'] == 'value' for name in matches):
                raise MetricDefinitionError('Stored product values and aggregates require separate output grains.', code='incompatible_grain', clarification=True)
            matched.update(matches)
            for name in matches:
                representations[name] = 'aggregate' if expression.find(exp.AggFunc) else 'stored_value'
            continue
        if expression.find(exp.AggFunc):
            raise MetricDefinitionError('Inventory aggregate does not match an accepted catalog formula.')
        if any(column.name not in dimensions or column.sql() not in dimension_sources for column in expression.find_all(exp.Column)):
            raise MetricDefinitionError('This inventory metric does not support the requested output dimension.', code='unsupported_dimension', clarification=True)
    if has_aggregates and not _single_snapshot(list(used_scopes.values()), parameters):
        raise MetricDefinitionError('Inventory metrics require one snapshot or separate exact snapshot_date groups.', code='invalid_date_scope')
    if set(metric_names) - matched:
        raise MetricDefinitionError('Missing canonical inventory formula: ' + ', '.join(sorted(set(metric_names)-matched)))
    if question is not None:
        validate_metric_request(question, metric_names)
        _validate_inventory_time(list(used_scopes.values()), parameters, question)
        if not projected_snapshot:
            raise MetricDefinitionError('Select i.snapshot_date AS snapshot_date; for aggregates also GROUP BY i.snapshot_date. Include LIMIT 200. An aggregate-only row cannot identify its historical as-of date.', code='invalid_date_scope')
    return {name: {**active[name], 'representation': representations[name]} for name in sorted(matched)}


def inventory_observation_query(sql, parameters=()):
    """Recognize key/presence diagnostics without approving any business measure."""
    scopes = list(traverse_scope(parse_one(sql, read='postgres')))
    for scope in scopes:
        for column in scope.columns:
            try:
                value = _canonical(column, scope, parameters, {})
            except MetricDefinitionError:
                return False
            if any(c.db == 'commerce' and c.table == 'inventory' and c.name not in {'product_id','snapshot_date'}
                   for c in value.find_all(exp.Column)):
                return False
        for projection in scope.expression.selects:
            try:
                value = _canonical(projection, scope, parameters, {})
            except (MetricDefinitionError, IndexError):
                return False
            if any(c.db == 'commerce' and c.table == 'inventory' and c.name not in {'product_id','snapshot_date'}
                   for c in value.find_all(exp.Column)):
                return False
            for aggregate in value.find_all(exp.AggFunc):
                if isinstance(aggregate, exp.Count):
                    continue
                if isinstance(aggregate, (exp.Min, exp.Max)) and aggregate.this == exp.column(
                        'snapshot_date', table='inventory', db='commerce'):
                    continue
                # Duplicate-row diagnostics sum counts, never source measures or identifier values.
                if isinstance(aggregate, exp.Sum) and aggregate.find(exp.Count) and not list(value.find_all(exp.Column)):
                    continue
                return False
    return True


def _validate_source_period(scope, table, field, parameters, question):
    period = inventory_time_scope(question)
    if not period or len(set(re.findall(r'\b(?:19|20)\d{2}\b', question))) > 1:
        raise MetricDefinitionError('Specify one explicit historical period for this cross-domain calculation.', clarification=True)
    start = date.fromisoformat(period[1])
    end = date.fromisoformat(period[2] or period[1]) + timedelta(days=1)
    column = exp.column(field, table=table, db='commerce')
    lower, upper = [], []
    for predicate in _conjuncts(scope.expression.args.get('where')):
        if not any(c.name == field and isinstance(scope.sources.get(c.table), exp.Table)
                   and scope.sources[c.table].name == table for c in predicate.find_all(exp.Column)):
            continue
        value = _canonical(predicate, scope, parameters, {})
        if not isinstance(value, (exp.EQ, exp.GTE, exp.GT, exp.LT, exp.LTE)):
            continue
        if isinstance(value.this, exp.Extract) and value.this.expression == column and value.this.this.name == 'YEAR':
            if isinstance(value, exp.EQ) and start == date(start.year,1,1) and end == date(start.year+1,1,1) and str(value.expression.this) == str(start.year):
                return
        left, right = value.this, value.expression
        operator = type(value)
        if right == column:
            left, right = right, left
            operator = {exp.GTE:exp.LTE, exp.GT:exp.LT, exp.LT:exp.GT, exp.LTE:exp.GTE, exp.EQ:exp.EQ}[operator]
        if left != column or not isinstance(right, exp.Literal):
            continue
        try:
            bound = date.fromisoformat(str(right.this))
        except ValueError:
            continue
        if operator in {exp.EQ, exp.GTE, exp.GT}:
            lower.append(bound + timedelta(days=int(operator is exp.GT)))
        if operator in {exp.EQ, exp.LT, exp.LTE}:
            upper.append(bound + timedelta(days=int(operator in {exp.EQ,exp.LTE})))
    if not lower or not upper or max(lower) != start or min(upper) != end:
        raise MetricDefinitionError(f'{table}.{field} must independently cover the requested period.', code='invalid_date_scope')


def _validate_contract_population(scope, required_tables, date_column, parameters):
    """Narrow explicit-period contracts cannot acquire hidden source restrictions."""
    tables = [source.name for _,source in scope.selected_sources.values() if isinstance(source,exp.Table)]
    select = scope.expression
    if (not required_tables <= set(tables) or not set(tables) <= required_tables | {'products'}
            or len(tables) != len(set(tables)) or len(tables) != len(scope.selected_sources)
            or any(select.args.get(key) for key in ('limit','offset','having','qualify','distinct'))
            or any(join.side or join.kind not in {'','INNER'} for join in select.args.get('joins',[]))):
        raise MetricDefinitionError('Source population must be complete, independently aggregated and free of unrequested restrictions.')
    for predicate in _conjuncts(select.args.get('where')):
        columns = list(_canonical(predicate,scope,parameters,{}).find_all(exp.Column))
        if not columns or any(column != date_column for column in columns):
            fields=', '.join(sorted({column.sql() for column in columns if column != date_column})) or 'constant predicate'
            raise MetricDefinitionError('Remove the unrequested source filter on '+fields+'. '
                'This contract requests all observations in the period, including every order status. '
                'Do not exclude cancelled orders unless the user explicitly requests that population.')
    for join in select.args.get('joins',[]):
        if any(not isinstance(p,exp.EQ) or not isinstance(p.this,exp.Column) or not isinstance(p.expression,exp.Column)
               for p in _conjuncts(join.args.get('on'))):
            raise MetricDefinitionError('Join predicates cannot add unrequested source filters.')


def _validate_product_ranking(root, expected, parameters, question, identity_tables):
    from core.analytics.metric_mapping import MetricRanking, requested_ranking_limit
    select = root.expression
    ranking = MetricRanking(metric='requested_measure',direction='asc' if re.search(r'lowest|smallest|bottom',question,re.I) else 'desc',
                            limit=requested_ranking_limit(question))
    orders = select.args.get('order')
    def order_value(order):
        value=order.this
        if isinstance(value,exp.Literal) and value.is_int and 1 <= int(value.this) <= len(select.selects):
            value=select.selects[int(value.this)-1]
        return _canonical(value,root,parameters,{})
    if (not orders or order_value(orders.expressions[0]) != expected
            or bool(orders.expressions[0].args.get('desc')) != (ranking.direction == 'desc')
            or (isinstance(expected,exp.Div) and orders.expressions[0].args.get('nulls_first'))
            or not select.args.get('limit') or int(select.args['limit'].expression.this) != (ranking.limit or 200)):
        raise MetricDefinitionError('Ranking, NULL order or TOP-N differs from the requested contract.')
    identities = {exp.column('product_id',table=table,db='commerce').sql() for table in identity_tables}
    if not any(order_value(order).sql() in identities for order in orders.expressions[1:]):
        raise MetricDefinitionError('Product ranking requires a stable product_id tie-break.')


def _unit_ratio(scopes, parameters, question):
    root = scopes[-1]
    expected = parse_one('CAST(SUM(returns.return_quantity) AS NUMERIC) / NULLIF(SUM(order_items.quantity), 0)', read='postgres')
    for column in expected.find_all(exp.Column):
        column.set('db', exp.to_identifier('commerce'))
    values = [_canonical(p, root, parameters, {}) for p in root.expression.selects]
    if expected not in values:
        raise MetricDefinitionError('Unit ratio requires independently summed returned units / NULLIF(ordered units,0), cast to NUMERIC.')
    operands = [expected.this.this, expected.expression.this]
    if any(value not in values for value in operands):
        raise MetricDefinitionError('Project both independently aggregated unit operands alongside the ratio for traceability.')
    for table, field in [('returns','return_date'), ('orders','order_date')]:
        selected = [s for s in scopes if any(isinstance(source, exp.Table) and source.name == table
                    for _, source in s.selected_sources.values())]
        if len(selected) != 1 or selected[0].expression.args.get('limit'):
            raise MetricDefinitionError('Unit ratio operands require complete independent source aggregates.')
        _validate_contract_population(selected[0],{'returns'} if table == 'returns' else {'orders','order_items'},
            exp.column(field,table=table,db='commerce'),parameters)
        _validate_source_period(selected[0], table, field, parameters, question)
        group = selected[0].expression.args.get('group')
        groups = [_canonical(p,selected[0],parameters,{}) for p in group.expressions] if group else []
        if len(groups) != 1 or not isinstance(groups[0],exp.Column) or groups[0].name != 'product_id':
            raise MetricDefinitionError('Each unit ratio operand must be grouped at product grain only.')
    select = root.expression
    if (any(select.args.get(key) for key in ('where','having','group','distinct','offset','qualify'))
            or any(join.side or join.kind not in {'','INNER'} for join in select.args.get('joins',[]))):
        raise MetricDefinitionError('Unit ratios require both observed operands without extra output restrictions.')
    _validate_product_ranking(root,expected,parameters,question,('returns','order_items','products'))
    return {}


def _cross_domain_inventory(sql, metric_names, parameters, table_columns, question):
    """Two explicit contracts: recorded movement comparison, or stockout/order presence."""
    scopes = list(traverse_scope(parse_one(sql, read='postgres')))
    inventory_scopes = [s for s in scopes if any(isinstance(source, exp.Table)
        and source.db == 'commerce' and source.name == 'inventory' for _, source in s.selected_sources.values())]
    if len(inventory_scopes) != 1 or not question:
        raise MetricDefinitionError('Cross-domain inventory requires one independently validated inventory scope.')
    scope = inventory_scopes[0]
    if any(not isinstance(source, exp.Table) or source.db != 'commerce' or source.name not in {'inventory','products'}
           for _, source in scope.selected_sources.values()):
        raise MetricDefinitionError('Aggregate inventory independently; use EXISTS for order presence, not a raw fact join.')
    text = question.casefold().replace('_', ' ')
    order_scopes = [s for s in scopes if any(isinstance(source, exp.Table) and source.name == 'orders'
                    for _, source in s.selected_sources.values())]
    if len(order_scopes) != 1:
        raise MetricDefinitionError('Cross-domain orders require one independently filtered order scope.')
    _validate_source_period(order_scopes[0], 'orders', 'order_date', parameters, question)
    if metric_names == {'inventory_units_sold'} and re.search(r'compar|versus|\bvs\b|so sánh', text):
        validate_metric_request(question, metric_names)
        definition = get_metric_definition('inventory_units_sold')
        category = exp.column('category', table='products', db='commerce')
        formula = _formula(definition, table_columns)
        projections = [_canonical(p, scope, parameters, {}) for p in scope.expression.selects]
        group = scope.expression.args.get('group')
        groups = [_canonical(p, scope, parameters, {}) for p in group.expressions] if group else []
        if projections != [category, formula] or groups != [category] or scope.expression.args.get('limit'):
            raise MetricDefinitionError('Movement comparison requires complete category SUM(units_sold) before limiting detail.')
        _validate_inventory_time([scope], parameters, question)
        _validate_contract_population(scope,{'inventory','products'},
            exp.column('snapshot_date',table='inventory',db='commerce'),parameters)
        order_scope = order_scopes[0]
        _validate_contract_population(order_scope,{'orders','order_items','products'},
            exp.column('order_date',table='orders',db='commerce'),parameters)
        order_values = [_canonical(p, order_scope, parameters, {}) for p in order_scope.expression.selects]
        ordered_units = parse_one('SUM(commerce.order_items.quantity)', read='postgres')
        order_group = order_scope.expression.args.get('group')
        if order_values != [category, ordered_units] or not order_group or [
                _canonical(p, order_scope, parameters, {}) for p in order_group.expressions] != [category]:
            raise MetricDefinitionError('Order comparison requires an independent category SUM(order_items.quantity).')
        root = scopes[-1]
        output = [_canonical(p, root, parameters, {}) for p in root.expression.selects]
        joins = root.expression.args.get('joins', [])
        category_key = exp.Coalesce(this=category.copy(), expressions=[category.copy()])
        if (len(joins) != 1 or joins[0].side != 'FULL' or output != [category_key, formula, ordered_units]
                or any(root.expression.args.get(key) for key in ('where','having','group','distinct','offset','qualify'))):
            raise MetricDefinitionError('Compare both complete category aggregates with FULL JOIN and COALESCE of category keys; keep missing measures NULL.')
        return {'inventory_units_sold': {**definition, 'representation':'period_observation_sum',
            'limitations': [*definition.get('limitations', []),
                'Explicit sum of recorded movement observations in the requested period; not a closing stock balance or order-derived sales.'],
            'calculation_scope': inventory_time_scope(question)}}
    if metric_names == {'stockout_indicator'} and scope.expression.find(exp.Exists):
        isolated = scope.expression.copy()
        isolated.set('with_', None)
        predicates = list(_conjuncts(isolated.args.get('where')))
        exists = [p for p in predicates if isinstance(p, exp.Exists)]
        if len(exists) != 1:
            raise MetricDefinitionError('Order presence must be one conjunctive EXISTS, not a multiplying join.')
        isolated.set('where', exp.Where(this=exp.and_(*(p.copy() for p in predicates if not isinstance(p, exp.Exists)))))
        flag = exp.column('stockout_flag', table='inventory', db='commerce')
        canonical = [_canonical(p, scope, parameters, {}) for p in _conjuncts(scope.expression.args.get('where'))
                     if not isinstance(p, exp.Exists)]
        if re.search(r'stockout flag\s*=\s*true', text) and not any(
                isinstance(p, exp.EQ) and p.this == flag and p.expression == exp.true() for p in canonical):
            raise MetricDefinitionError('The requested stockout_flag=true predicate is missing.')
        inventory_alias = next(alias for alias, (_, source) in scope.selected_sources.items()
                               if source.name == 'inventory')
        isolated.select(exp.alias_(exp.column('stockout_flag', table=inventory_alias), 'stockout_indicator'), copy=False)
        return _validate_inventory_metrics(isolated.sql(dialect='postgres'), metric_names, parameters, table_columns, question)
    raise MetricDefinitionError('This cross-domain inventory calculation has no verified contract. '
                                'Use independent movement comparisons or stockout/order existence checks.',
                                code='incompatible_grain', clarification=True)


def validate_metric_definitions(sql, metric_names, parameters, table_columns, *, question=None):
    """Verify recognized metrics; generic queries retain the existing SQL safety path."""
    tree = parse_one(sql, read='postgres')
    if _unrequested_date_filter(tree, question) and not any(
            table.name.casefold() == 'inventory' for table in tree.find_all(exp.Table)):
        raise MetricDefinitionError(
            'Do not filter by date unless the question requests a time period; use all available records.',
            code='unrequested_time_filter',
        )
    if question and metric_names == {'stock_on_hand'}:
        dates = inventory_comparison_dates(question)
        if dates:
            validate_metric_request(question, metric_names)
            return validate_stock_comparison(sql, parameters, dates)
    tables = {t.name for t in tree.find_all(exp.Table) if t.db == 'commerce'}
    if question and 'inventory' not in tables:
        scopes = list(traverse_scope(tree))
        text = question.casefold().replace('_',' ')
        if re.search(r'exclud\w*\s+cancel[le]+d|excluding cancelled',text):
            expected = parse_one("NOT LOWER(commerce.orders.order_status) IN ('cancelled','canceled')",read='postgres')
            matches = []
            for scope in scopes:
                for predicate in _conjuncts(scope.expression.args.get('where')):
                    value = _canonical(predicate,scope,parameters,{})
                    if isinstance(value,exp.Not) and isinstance(value.this,exp.In) and value.this.this == expected.this.this:
                        matches.append({v.this for v in value.this.expressions})
            if {'cancelled','canceled'} not in matches:
                raise MetricDefinitionError('Exclude both cancelled/canceled statuses with a case-insensitive source predicate.')
        if re.search(r'highest|most units|lowest',text) and re.search(r'products?',text):
            source = ('returns','return_quantity') if re.search(r'units returned',text) else (
                ('order_items','quantity') if 'quantity' in text else None)
            if source:
                expected = exp.Sum(this=exp.column(source[1],table=source[0],db='commerce'))
                _validate_product_ranking(scopes[-1],expected,parameters,question,(source[0],'products'))
    if question and re.search(r'ratio|divided|tỷ lệ|tỉ lệ', question, re.I) and not metric_names and re.search(
            r'returned units|số lượng trả', question, re.I) and re.search(r'ordered units|số lượng đặt', question, re.I):
        if not {'returns','orders','order_items'} <= tables:
            raise MetricDefinitionError('The requested unit ratio must retain both independently aggregated sources.')
        return _unit_ratio(list(traverse_scope(tree)), parameters, question)
    if question and 'duplicate' in question.casefold() and 'inventory' in tables and not re.search(
            r'\bgroups?\b|participating|all rows|all participating', question, re.I):
        root = list(traverse_scope(tree))[-1]
        expected = parse_one('COALESCE(SUM(COUNT(*) - 1), 0)', read='postgres')
        if len(root.expression.selects) != 1 or _canonical(root.expression.selects[0], root, parameters, {}) != expected:
            raise MetricDefinitionError('Duplicate rows means excess rows beyond one per key: '
                                        'COALESCE(SUM(group_count - 1),0), not number of duplicate groups.')
        groups = [s for s in traverse_scope(tree) if s.expression.args.get('group')]
        keys = {exp.column(name, table='inventory', db='commerce').sql() for name in ('snapshot_date','product_id')}
        if len(groups) != 1 or {_canonical(p, groups[0], parameters, {}).sql()
                for p in groups[0].expression.args['group'].expressions} != keys:
            raise MetricDefinitionError('Duplicate inventory keys must group by both snapshot_date and product_id.')
    if question and re.search(r'\b(?:which|\d+)\s+products\b|từng sản phẩm', question, re.I):
        root = list(traverse_scope(tree))[-1]
        projections = [_canonical(p, root, parameters, {}) for p in root.expression.selects]
        if any(isinstance(p, exp.Column) and p.name == 'product_name' for p in projections) and not any(
                isinstance(p, exp.Column) and p.name == 'product_id' for p in projections):
            raise MetricDefinitionError('Product-level rows require product_id; product_name is not unique.')
    if 'inventory' in tables and tables & {'orders', 'order_items'}:
        return _cross_domain_inventory(sql, metric_names, parameters, table_columns, question)
    if not metric_names:
        tree = parse_one(sql, read='postgres')
        if (tree.find(exp.AggFunc) and any(table.name == 'inventory' and table.db == 'commerce' for table in tree.find_all(exp.Table))
                and not inventory_observation_query(sql, parameters)):
            raise MetricDefinitionError('The dataset does not contain a reviewed definition for this inventory aggregate.', code='metric_unsupported', clarification=True)
        return {}
    if any(get_metric_definition(name).get('domain') == 'inventory_management' for name in metric_names):
        return _validate_inventory_metrics(sql, metric_names, parameters, table_columns, question)
    definitions = {name: get_metric_definition(name) for name in sorted(metric_names)}
    formulas = {}
    for name, definition in METRIC_ONTOLOGY.items():
        if not definition.get("formula"):
            continue
        formula = _formula(definition, table_columns)
        if definition.get("null_handling", "").startswith("COALESCE the aggregate to 0"):
            formula = exp.Coalesce(this=formula, expressions=[exp.Literal.number(0)])
        formulas[name] = formula
    scopes = list(traverse_scope(parse_one(sql, read="postgres")))
    root = scopes[-1]
    matched = set()
    dimensions = {column for definition in definitions.values() for column in definition["dimensions"]}
    measure_columns = {column.sql() for name in metric_names for column in formulas[name].find_all(exp.Column)}
    for projection in root.expression.selects:
        used_scopes = {}
        expression = _canonical(projection, root, parameters, used_scopes)
        if not expression.find(exp.AggFunc):
            if any(column.name not in dimensions for column in expression.find_all(exp.Column)):
                raise MetricDefinitionError("Requested metric does not support this output dimension")
            continue
        matches = {name for name, formula in formulas.items() if expression == formula}
        label = projection.alias.casefold()
        if not matches:
            if label in definitions or any(column.sql() in measure_columns for column in expression.find_all(exp.Column)):
                raise MetricDefinitionError("Aggregate does not match a canonical metric formula")
            continue
        if label in definitions and label not in matches:
            raise MetricDefinitionError(f"Output label {label} conflicts with its canonical metric formula")
        for name in matches:
            definition = get_metric_definition(name)
            for required in definition.get("filters", ()):
                expected = _formula({**definition, "formula": required}, table_columns)
                filters = []
                for scope in list(used_scopes.values()):
                    for predicate in _conjuncts(scope.expression.args.get("where")):
                        try:
                            filters.append(_canonical(predicate, scope, parameters, {}))
                        except MetricDefinitionError:
                            continue
                if expected not in filters:
                    raise MetricDefinitionError(f"Metric {name} requires filter: {required}")
            if "within one snapshot" in definition["formula"] and not _single_snapshot(list(used_scopes.values()), parameters):
                raise MetricDefinitionError(f"Metric {name} requires one snapshot or grouping by snapshot_date")
        matched.update(matches)
    missing = set(metric_names) - matched
    if missing:
        raise MetricDefinitionError("Missing canonical metric formula: " + ", ".join(sorted(missing)))
    return {name: get_metric_definition(name) for name in sorted(matched)}
