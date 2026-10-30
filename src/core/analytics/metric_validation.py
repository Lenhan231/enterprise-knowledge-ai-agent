"""Conservative checks of ontology formulas before executing model-generated SQL."""
from __future__ import annotations

import re
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
        source = {name.casefold(): value for name, value in scope.sources.items()}.get(node.table.casefold())
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
    if has_aggregates and any(definition['aggregation'] == 'value' for definition in definitions.values()):
        raise MetricDefinitionError('Stored product values and aggregate metrics have incompatible output grains. Request separate results or an explicit mean.', code='incompatible_grain', clarification=True)
    dimensions = set.intersection(*(set(definition['dimensions']) for definition in definitions.values()))
    dimension_sources = {exp.column(column, table=table.split('.')[1], db='commerce').sql()
                         for definition in definitions.values() for table, columns in definition['source_columns'].items()
                         for column in columns if column in dimensions}
    matched, used_scopes, representations = set(), {}, {}
    projected_snapshot = False
    for projection in root.expression.selects:
        expression = _canonical(projection, root, parameters, used_scopes)
        if expression == exp.column('snapshot_date', table='inventory', db='commerce') and projection.alias_or_name.casefold() == 'snapshot_date':
            projected_snapshot = True
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
    if not _single_snapshot(list(used_scopes.values()), parameters):
        raise MetricDefinitionError('Inventory metrics require one snapshot or separate exact snapshot_date groups.', code='invalid_date_scope')
    if set(metric_names) - matched:
        raise MetricDefinitionError('Missing canonical inventory formula: ' + ', '.join(sorted(set(metric_names)-matched)))
    if question is not None:
        validate_metric_request(question, metric_names)
        _validate_inventory_time(list(used_scopes.values()), parameters, question)
        if not projected_snapshot:
            raise MetricDefinitionError('Select i.snapshot_date AS snapshot_date; for aggregates also GROUP BY i.snapshot_date. Include LIMIT 200. An aggregate-only row cannot identify its historical as-of date.', code='invalid_date_scope')
    return {name: {**active[name], 'representation': representations[name]} for name in sorted(matched)}


def validate_metric_definitions(sql, metric_names, parameters, table_columns, *, question=None):
    """Verify recognized metrics; generic queries retain the existing SQL safety path."""
    if not metric_names:
        tree = parse_one(sql, read='postgres')
        if tree.find(exp.AggFunc) and any(table.name == 'inventory' and table.db == 'commerce' for table in tree.find_all(exp.Table)):
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
