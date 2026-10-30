"""Conservative checks of ontology formulas before executing model-generated SQL."""
from __future__ import annotations

import re

from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import Scope, traverse_scope

from core.analytics.metric_ontology import METRIC_ONTOLOGY, get_metric_definition


class MetricDefinitionError(ValueError):
    """A query cannot be verified against a requested canonical metric."""


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
        for predicate in _conjuncts(scope.expression.args.get("where")):
            if isinstance(predicate, exp.EQ):
                for column, value in ((predicate.this, predicate.expression), (predicate.expression, predicate.this)):
                    if isinstance(column, exp.Column) and isinstance(value, (exp.Parameter, exp.Literal)):
                        if _canonical(column, scope, parameters, {}) == snapshot:
                            return True
    return False


def validate_metric_definitions(sql, metric_names, parameters, table_columns):
    """Verify recognized metrics; generic queries retain the existing SQL safety path."""
    if not metric_names:
        return {}
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
