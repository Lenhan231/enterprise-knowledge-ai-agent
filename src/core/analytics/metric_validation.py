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
    numeric = re.search(r'thÃ¡ng\s+(\d{1,2})\s+(?:nÄƒm\s+)?((?:19|20)\d{2})\b', question)
    quarter = re.search(r'(?:\bq|quarter\s*|quÃ½\s*)([1-4])\s+(?:of\s+|nÄƒm\s+)?((?:19|20)\d{2})\b', question)
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
    if re.search(r'\bchange\b|\bdelta\b|\bdifference\b|thay Ä‘á»•i|chÃªnh lá»‡ch', _normalize(question)):
        dates = inventory_explicit_dates(question)
        if len(dates) == 2:
            return tuple(d.isoformat() for d in dates)
    return None


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
    if inventory and re.search(r'latest|má»›i nháº¥t|gáº§n nháº¥t', question, re.I) and re.search(r'\b(?:19|20)\d{2}\b', question):
        raise MetricDefinitionError('Do you want the latest dataset snapshot or a snapshot within the specified period?',
                                    code='ambiguous_snapshot', clarification=True)
    if inventory:
        for value in re.findall(r'\b\d{4}-\d{2}-\d{2}\b', question):
            try:
                date.fromisoformat(value)
            except ValueError as error:
                raise MetricDefinitionError('Use a valid snapshot date (YYYY-MM-DD).', code='invalid_date_scope', clarification=True) from error
        if not re.search(r'\b\d{4}-\d{2}-\d{2}\b', question) and re.search(
                r'quarter|quÃ½|thÃ¡ng\s+\d+|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+(?:19|20)\d{2}|last month|last year|thÃ¡ng trÆ°á»›c|nÄƒm ngoÃ¡i', question):
            try:
                scope = inventory_time_scope(question)
            except ValueError:
                scope = None
            if scope is None:
                raise MetricDefinitionError('Specify an exact historical snapshot date or ISO date range for that period.', code='snapshot_required', clarification=True)
    if inventory and not re.search(r'\b(?:19|20)\d{2}\b|latest|histor|trend|snapshot_date|má»›i nháº¥t|gáº§n nháº¥t|lá»‹ch sá»­|xu hÆ°á»›ng', question, re.I):
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
    if re.search(r'latest|má»›i nháº¥t|gáº§n nháº¥t', question, re.I):
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


def validate_metric_definitions(sql, metric_names, parameters, table_columns, *, question=None):
    """Verify recognized metrics; generic queries retain the existing SQL safety path."""
    tree = parse_one(sql, read='postgres')
    comparison = inventory_comparison_dates(question) if question else None
    if comparison and metric_names == {'stock_on_hand'}:
        return validate_stock_comparison(sql, parameters, comparison)
    tables = {t.name for t in tree.find_all(exp.Table) if t.db == 'commerce'}
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
    if 'inventory' in tables and question and re.search(r'\b(?:which|\d+)\s+products\b|tá»«ng sáº£n pháº©m', question, re.I):
        root = list(traverse_scope(tree))[-1]
        projections = [_canonical(p, root, parameters, {}) for p in root.expression.selects]
        if any(isinstance(p, exp.Column) and p.name == 'product_name' for p in projections) and not any(
                isinstance(p, exp.Column) and p.name == 'product_id' for p in projections):
            raise MetricDefinitionError('Product-level rows require product_id; product_name is not unique.')
    if not metric_names:
        tree = parse_one(sql, read='postgres')
        if (tree.find(exp.AggFunc) and any(table.name == 'inventory' and table.db == 'commerce' for table in tree.find_all(exp.Table))
                and not inventory_observation_query(sql, parameters)):
            raise MetricDefinitionError('The dataset does not contain a reviewed definition for this inventory aggregate.', code='metric_unsupported', clarification=True)
        return {}
    if any(get_metric_definition(name).get('domain') == 'inventory_management' for name in metric_names):
        return _validate_inventory_metrics(sql, metric_names, parameters, table_columns, question)
    definitions = {name: get_metric_definition(name) for name in sorted(metric_names)}
    formulas = {name: _formula(definition, table_columns) for name, definition in METRIC_ONTOLOGY.items()
                if definition.get("formula")}
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
