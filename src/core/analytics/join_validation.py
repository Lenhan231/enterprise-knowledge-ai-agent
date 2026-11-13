"""Reject aggregates whose input rows can be multiplied by approved joins."""
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope


# Primary keys from 20261003055344_datathon_commerce_schema.sql, not inferred from data.
PRIMARY_KEYS = {
    'invoices': {'invoice_id'}, 'invoice_items': {'invoice_id', 'line_no'},
    'products': {'product_id'}, 'geography': {'zip'}, 'customers': {'customer_id'},
    'promotions': {'promo_id'}, 'orders': {'order_id'}, 'order_items': {'order_item_id'},
    'payments': {'order_id'}, 'shipments': {'order_id'}, 'returns': {'return_id'},
    'reviews': {'review_id'}, 'inventory': {'snapshot_date', 'product_id'},
    'web_traffic': {'date', 'traffic_source'}, 'sales': {'date'},
}


def grouped_key(scope):
    """Output names of an explicit GROUP BY key, or no proof of uniqueness."""
    if not isinstance(scope, Scope) or not scope.expression.args.get('group') or scope.expression.args.get('limit'):
        return None
    projections = scope.expression.selects
    names = set()
    for value in scope.expression.args['group'].expressions:
        if isinstance(value, exp.Literal) and value.is_int:
            index = int(value.this) - 1
            if not 0 <= index < len(projections):
                return None
            value = projections[index].unalias()
        matches = [p.alias_or_name.casefold() for p in projections if p.unalias() == value]
        if len(matches) != 1 or not isinstance(value, exp.Column):
            return None
        names.add(matches[0])
    return names or None


def column_origin(scope, column, visited=()):
    """Resolve only transparent key projections; computed expressions are not join keys."""
    if id(scope) in visited:
        return None
    source = scope.sources.get(column.table)
    if isinstance(source, exp.Table):
        return (f'{source.db}.{source.name}'.casefold(), column.name.casefold())
    if isinstance(source, Scope):
        projections = [p for p in source.expression.selects if p.alias_or_name.casefold() == column.name.casefold()]
        if len(projections) == 1 and isinstance(projections[0].unalias(), exp.Column):
            return column_origin(source, projections[0].unalias(), (*visited, id(scope)))
    return None


def relation_key(source):
    return PRIMARY_KEYS.get(source.name.casefold()) if isinstance(source, exp.Table) else grouped_key(source)


def approved_derived_join(scope, equalities, approved_joins):
    """Permit independently grouped, unique keys with approved dimension lineage."""
    keys = {}
    for equality in equalities:
        left, right = equality.this, equality.expression
        if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
            return False
        for column in (left, right):
            keys.setdefault(column.table, set()).add(column.name.casefold())
        origins = (column_origin(scope, left), column_origin(scope, right))
        if not all(origins):
            return False
        # Product foreign keys share the approved products key only after independent grouping.
        product_keys = {('commerce.products', 'product_id')}
        product_keys.update(endpoint for edge in approved_joins if ('commerce.products', 'product_id') in edge for endpoint in edge)
        same_dimension = origins[0] == origins[1] and origins[0][0] == 'commerce.products'
        if not (same_dimension or set(origins) <= product_keys or frozenset(origins) in approved_joins):
            return False
    return bool(keys) and all(relation_key(scope.sources.get(alias)) is not None
                              and relation_key(scope.sources[alias]) <= columns
                              for alias, columns in keys.items())


def validate_join_aggregations(tree, error_type):
    """Prove preservation of each aggregate's source grain using declared keys."""
    scopes = list(traverse_scope(tree))
    sources = {id(scope): {alias.casefold(): source for alias, (_, source)
                           in scope.selected_sources.items()} for scope in scopes}
    duplicated = {}
    for scope in scopes:
        relations = sources[id(scope)]
        edges = []
        for join in scope.expression.args.get('joins', ()):
            for equality in join.args['on'].find_all(exp.EQ):
                left, right = equality.this, equality.expression
                if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                    edges.extend(((left.table.casefold(), right.table.casefold(), right.name.casefold()),
                                  (right.table.casefold(), left.table.casefold(), left.name.casefold())))
        unsafe = set()
        for origin in relations:
            reached = {origin}
            while True:
                additions = set()
                for alias, source in relations.items():
                    key = relation_key(source)
                    columns = {column for left, right, column in edges if left in reached and right == alias}
                    if key and key <= columns:
                        additions.add(alias)
                additions -= reached
                if not additions:
                    break
                reached.update(additions)
            if reached != set(relations):
                unsafe.add(origin)
        duplicated[id(scope)] = unsafe

    def column_duplicated(column, scope):
        alias = column.table.casefold()
        if alias in duplicated[id(scope)]:
            return True
        source = sources[id(scope)].get(alias)
        if isinstance(source, Scope):
            projections = [p for p in source.expression.selects
                           if p.alias_or_name.casefold() == column.name.casefold()]
            if len(projections) != 1:
                return True
            projection = projections[0]
            # Inner aggregate inputs are checked in their own scope; other output columns still carry grain.
            return any(column_duplicated(c, source) for c in projection.find_all(exp.Column)
                       if c.find_ancestor(exp.Select) is source.expression
                       and c.find_ancestor(exp.AggFunc) is None)
        return False

    def rows_duplicated(scope):
        if duplicated[id(scope)]:
            return True
        return any(isinstance(source, Scope) and not any(
                       agg.find_ancestor(exp.Select) is source.expression
                       for agg in source.expression.find_all(exp.AggFunc))
                   and rows_duplicated(source) for source in sources[id(scope)].values())

    for scope in scopes:
        for aggregate in scope.expression.find_all(exp.AggFunc):
            if aggregate.find_ancestor(exp.Select) is not scope.expression:
                continue
            if isinstance(aggregate, (exp.Min, exp.Max)) or (
                isinstance(aggregate, exp.Count) and isinstance(aggregate.this, exp.Distinct)
            ):
                continue
            columns = list(aggregate.find_all(exp.Column))
            if any(column_duplicated(column, scope) for column in columns) or (
                not columns and rows_duplicated(scope)
            ):
                raise error_type(
                    'Aggregate input may be duplicated by a one-to-many join. '
                    'Aggregate from its source without the multiplying join, or use COUNT(DISTINCT key) '
                    'for entity counts. SUM(DISTINCT value) does not restore source grain.'
                )
