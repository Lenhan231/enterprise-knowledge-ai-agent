"""Reject aggregates whose input rows can be multiplied by approved joins."""
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope


# Primary keys from 20261003055344_datathon_commerce_schema.sql, not inferred from data.
PRIMARY_KEYS = {
    'products': {'product_id'}, 'geography': {'zip'}, 'customers': {'customer_id'},
    'promotions': {'promo_id'}, 'orders': {'order_id'}, 'order_items': {'order_item_id'},
    'payments': {'order_id'}, 'shipments': {'order_id'}, 'returns': {'return_id'},
    'reviews': {'review_id'}, 'inventory': {'snapshot_date', 'product_id'},
    'web_traffic': {'date', 'traffic_source'}, 'sales': {'date'},
}


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
        # shortcut: filters/regrouping do not prove uniqueness here; extend when supporting those rewrites.
        for origin in relations:
            reached = {origin}
            while True:
                additions = set()
                for alias, source in relations.items():
                    key = PRIMARY_KEYS.get(source.name.casefold()) if isinstance(source, exp.Table) else None
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
