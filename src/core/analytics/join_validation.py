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


def _column_name(column):
    identifier = column.this
    return identifier.this if identifier.args.get('quoted') else identifier.this.casefold()


def _primary_key(table, primary_keys):
    return primary_keys.get(table, primary_keys.get(table.rsplit('.', 1)[-1], set()))


def grouped_key(scope, primary_keys=PRIMARY_KEYS):
    """Output names of explicit GROUP BY expressions, or no proof of uniqueness."""
    if not isinstance(scope, Scope) or not scope.expression.args.get('group') or scope.expression.args.get('limit'):
        return None
    projections = scope.expression.selects
    names = set()
    origins = {}
    for value in scope.expression.args['group'].expressions:
        if isinstance(value, exp.Literal) and value.is_int:
            index = int(value.this) - 1
            if not 0 <= index < len(projections):
                return None
            value = projections[index].unalias()
        matches = [p.alias_or_name.casefold() for p in projections if p.unalias() == value]
        if len(matches) != 1:
            return None
        name = matches[0]
        names.add(name)
        projection = next(p for p in projections if p.unalias() == value)
        expression = projection.unalias()
        if isinstance(expression, exp.Column):
            origins[name] = column_origin(scope, expression)
    joined_dimensions = {}
    for join in scope.expression.args.get('joins', ()):
        for equality in join.args.get('on', exp.And()).find_all(exp.EQ):
            left, right = equality.this, equality.expression
            if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                continue
            left_origin, right_origin = column_origin(scope, left), column_origin(scope, right)
            if not left_origin or not right_origin:
                continue
            if _primary_key(left_origin[0], primary_keys) == {left_origin[1]}:
                joined_dimensions[right_origin] = left_origin[0]
            if _primary_key(right_origin[0], primary_keys) == {right_origin[1]}:
                joined_dimensions[left_origin] = right_origin[0]
    dependent = set()
    for name, origin in origins.items():
        if not origin:
            continue
        determined_tables = {origin[0]}
        if origin[1] in _primary_key(origin[0], primary_keys):
            determined_tables.add(origin[0])
        if origin in joined_dimensions:
            determined_tables.add(joined_dimensions[origin])
        if len(determined_tables) == 1 and origin[1] not in _primary_key(origin[0], primary_keys):
            continue
        dependent.update(other for other, other_origin in origins.items()
                         if other != name and other_origin and other_origin[0] in determined_tables)
    names -= dependent
    return names or None


def passthrough_key(scope, primary_keys=PRIMARY_KEYS, visited=()):
    """Keep a uniqueness key through a projection with only many-to-one joins."""
    if not isinstance(scope, Scope) or id(scope) in visited or scope.expression.args.get('group'):
        return None
    from_clause = scope.expression.args.get('from_')
    if not from_clause:
        return None
    root_alias = from_clause.this.alias_or_name.casefold()
    root_source = scope.sources.get(root_alias)
    upstream = relation_key(root_source, primary_keys, (*visited, id(scope)))
    if not upstream:
        return None
    for join in scope.expression.args.get('joins', ()):
        target_alias = join.this.alias_or_name.casefold()
        target_key = relation_key(scope.sources.get(target_alias), primary_keys, (*visited, id(scope)))
        if not target_key:
            return None
        target_columns = set()
        predicates = []

        def flatten(expression):
            if isinstance(expression, exp.And):
                flatten(expression.this)
                flatten(expression.expression)
            else:
                predicates.append(expression)

        if not join.args.get('on'):
            return None
        flatten(join.args['on'])
        for predicate in predicates:
            if not isinstance(predicate, exp.EQ) or not all(
                    isinstance(side, exp.Column) for side in (predicate.this, predicate.expression)):
                return None
            for side in (predicate.this, predicate.expression):
                if side.table.casefold() == target_alias:
                    target_columns.add(side.name.casefold())
        if not target_key <= target_columns:
            return None
    outputs = {}
    for projection in scope.expression.selects:
        value = projection.unalias()
        if isinstance(value, exp.Column) and value.name.casefold() in upstream \
                and (not value.table or value.table.casefold() == root_alias):
            outputs.setdefault(value.name.casefold(), []).append(projection.alias_or_name.casefold())
    preserved = [names[0] for key, names in outputs.items() if key in upstream and len(names) == 1]
    return set(preserved) if set(outputs) >= set(upstream) and len(preserved) == len(upstream) else None


def relation_key(source, primary_keys=PRIMARY_KEYS, visited=()):
    if not isinstance(source, exp.Table):
        limit = source.expression.args.get('limit') if isinstance(source, Scope) else None
        if (limit and isinstance(limit.expression, exp.Literal) and limit.expression.is_int
                and int(limit.expression.this) == 1):
            # Any projected column uniquely identifies a relation with at most one row.
            return {projection.alias_or_name.casefold() for projection in source.expression.selects
                    if projection.alias_or_name}
        return grouped_key(source, primary_keys) or passthrough_key(source, primary_keys, visited)
    name = f'{source.db}.{source.name}'.casefold() if source.db else source.name.casefold()
    return primary_keys.get(name, primary_keys.get(source.name.casefold()))


def _date_bucket_key(source, output_name):
    if not isinstance(source, Scope):
        return None
    projections = [projection for projection in source.expression.selects
                   if projection.alias_or_name.casefold() == output_name.casefold()]
    if len(projections) != 1:
        return None
    expression = projections[0].unalias()
    if isinstance(expression, exp.Column):
        return _date_bucket_key(source.sources.get(expression.table), expression.name)
    while isinstance(expression, (exp.Cast, exp.Paren)):
        expression = expression.this
    if not isinstance(expression, exp.TimestampTrunc) or not isinstance(expression.this, exp.Column):
        return None
    origin = column_origin(source, expression.this)
    if not origin or not origin[0].startswith('commerce.'):
        return None
    unit = expression.args['unit'].this.casefold()
    if unit not in {'day', 'week', 'month', 'quarter', 'year'}:
        return None
    return unit, origin


def _join_key_side(expression, scope):
    """Return a join key with date bucket and source lineage when available."""
    if isinstance(expression, exp.Paren):
        return _join_key_side(expression.this, scope)
    if isinstance(expression, exp.Cast) and expression.args.get('to') \
            and expression.args['to'].this == exp.DataType.Type.DATE:
        return _join_key_side(expression.this, scope)
    if isinstance(expression, exp.TimestampTrunc) and isinstance(expression.this, exp.Column):
        column = expression.this
        unit = expression.args.get('unit')
        origin = column_origin(scope, column)
        if unit and origin:
            return (column.table.casefold(), column.name.casefold(),
                    unit.this.casefold(), None, None, origin)
    offset_unit = offset_amount = None
    column = expression if isinstance(expression, exp.Column) else None
    if isinstance(expression, (exp.Add, exp.Sub)) and isinstance(expression.this, exp.Column) \
            and isinstance(expression.expression, exp.Interval):
        interval = expression.expression
        if not isinstance(interval.this, exp.Literal) or not interval.this.is_string:
            return None
        try:
            offset_amount = int(interval.this.this)
        except (TypeError, ValueError):
            return None
        if offset_amount == 0:
            return None
        offset_unit = interval.args['unit'].this.casefold()
        if isinstance(expression, exp.Sub):
            offset_amount *= -1
        column = expression.this
    if column is None:
        return None
    alias, name = column.table.casefold(), column.name.casefold()
    source = scope.sources.get(alias)
    bucket = _date_bucket_key(source, name)
    return alias, name, bucket[0] if bucket else None, offset_unit, offset_amount, bucket[1] if bucket else None


def approved_derived_join(scope, equalities, approved_joins, primary_keys=PRIMARY_KEYS):
    """Permit independently grouped, unique keys with approved dimension lineage."""
    keys = {}
    for equality in equalities:
        left, right = equality.this, equality.expression
        left_key, right_key = _join_key_side(left, scope), _join_key_side(right, scope)
        if not left_key or not right_key:
            return False
        for alias, name, *_ in (left_key, right_key):
            keys.setdefault(alias, set()).add(name)
        if (left_key[2] and left_key[2] == right_key[2]
                and left_key[5] and left_key[5] == right_key[5]
                and not left_key[3] and not right_key[3]):
            continue
        if left_key[3] or right_key[3]:
            if (not left_key[3] or not right_key[3]) and left_key[2] == right_key[2] == 'month' \
                    and {left_key[3], right_key[3]} in ({None, 'month'}, {None, 'year'}) \
                    and abs((left_key[4] or 0) - (right_key[4] or 0)) == 1:
                continue
            return False
        if left_key[0] in scope.sources and right_key[0] in scope.sources:
            left_column, right_column = left, right
            origins = (column_origin(scope, left_column), column_origin(scope, right_column))
            if all(origins):
                product_keys = {('commerce.products', 'product_id')}
                product_keys.update(endpoint for edge in approved_joins
                                    if ('commerce.products', 'product_id') in edge for endpoint in edge)
                same_source_key = origins[0] == origins[1]
                if same_source_key or set(origins) <= product_keys or frozenset(origins) in approved_joins:
                    continue
            left_bucket = _date_bucket_key(scope.sources[left_key[0]], left_key[1])
            right_bucket = _date_bucket_key(scope.sources[right_key[0]], right_key[1])
            if left_bucket and right_bucket and left_bucket[0] == right_bucket[0] \
                    and (left_bucket[1] == right_bucket[1] or left_bucket[0] == 'month'):
                continue
            return False
    def has_complete_key(alias, columns):
        key = relation_key(scope.sources.get(alias), primary_keys)
        return key is not None and key <= columns

    def has_passthrough_key(alias):
        source = scope.sources.get(alias)
        return isinstance(source, Scope) and passthrough_key(source, primary_keys) is not None

    # A base table's complete primary key makes a dimension join many-to-one;
    # grouped sources still need complete keys on both sides of a derived join.
    base_key_is_complete = any(
        isinstance(scope.sources.get(alias), exp.Table) and has_complete_key(alias, columns)
        for alias, columns in keys.items()
    )
    many_to_one_detail_join = any(
        has_complete_key(unique_alias, columns) and has_passthrough_key(detail_alias)
        for unique_alias, columns in keys.items()
        for detail_alias in keys if detail_alias != unique_alias
    )
    return base_key_is_complete or many_to_one_detail_join or (bool(keys) and all(
        has_complete_key(alias, columns) for alias, columns in keys.items()
    ))


def validate_join_aggregations(tree, error_type, primary_keys=PRIMARY_KEYS):
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
                    edges.extend(((left.table.casefold(), right.table.casefold(), _column_name(right)),
                                  (right.table.casefold(), left.table.casefold(), _column_name(left))))
                elif isinstance(left, exp.Column) or isinstance(right, exp.Column):
                    left_key, right_key = _join_key_side(left, scope), _join_key_side(right, scope)
                    if (left_key and right_key and left_key[2] and left_key[2] == right_key[2]
                            and left_key[5] and left_key[5] == right_key[5]
                            and not left_key[3] and not right_key[3]):
                        edges.extend(((left_key[0], right_key[0], right_key[1]),
                                      (right_key[0], left_key[0], left_key[1])))
                    elif (left_key and right_key and left_key[1] == right_key[1]
                            and left_key[2] == right_key[2] == 'month'
                            and {left_key[3], right_key[3]} in ({None, 'month'}, {None, 'year'})
                            and abs((left_key[4] or 0) - (right_key[4] or 0)) == 1):
                        edges.extend(((left_key[0], right_key[0], right_key[1]),
                                      (right_key[0], left_key[0], left_key[1])))
        unsafe = set()
        for origin in relations:
            reached = {origin}
            while True:
                additions = set()
                for alias, source in relations.items():
                    key = relation_key(source, primary_keys)
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

    def weighted_product_cost(inputs, scope):
        origins = {column_origin(scope, column) for column in inputs}
        return {('commerce.products', 'cogs'), ('commerce.order_items', 'quantity')} <= origins

    def column_duplicated(column, scope):
        alias = column.table.casefold()
        if alias in duplicated[id(scope)]:
            return True
        source = sources[id(scope)].get(alias)
        if isinstance(source, Scope):
            if relation_key(source, primary_keys) is not None:
                # The inner scope has a proven unique grain, and any multiplying join
                # at this level was already ruled out by duplicated[id(scope)].
                return False
            projections = [p for p in source.expression.selects
                           if p.alias_or_name.casefold() == column.name.casefold()]
            if len(projections) != 1:
                return True
            projection = projections[0]
            # Inner aggregate inputs are checked in their own scope; other output columns still carry grain.
            inputs = [c for c in projection.find_all(exp.Column)
                      if c.find_ancestor(exp.Select) is source.expression
                      and c.find_ancestor(exp.AggFunc) is None]
            # A dimension value combined with a fact-grain column (for example
            # quantity * product.cogs) is a line-level measure, not a repeated
            # parent measure. Keep rejecting dimension-only aggregates.
            if weighted_product_cost(inputs, source):
                return False
            return bool(inputs) and all(column_duplicated(c, source) for c in inputs)
        return False

    def rows_duplicated(scope):
        from_clause = scope.expression.args.get('from_')
        root = from_clause.this.alias_or_name.casefold() if from_clause else None
        if root in duplicated[id(scope)]:
            return True
        source = sources[id(scope)].get(root)
        return bool(isinstance(source, Scope) and not any(
            agg.find_ancestor(exp.Select) is source.expression
            for agg in source.expression.find_all(exp.AggFunc)) and rows_duplicated(source))

    for scope in scopes:
        for aggregate in scope.expression.find_all(exp.AggFunc):
            if aggregate.find_ancestor(exp.Select) is not scope.expression:
                continue
            if isinstance(aggregate, (exp.Min, exp.Max)) or (
                isinstance(aggregate, exp.Count) and isinstance(aggregate.this, exp.Distinct)
            ):
                continue
            columns = list(aggregate.find_all(exp.Column))
            duplicated_inputs = [column for column in columns if column_duplicated(column, scope)]
            unweighted_parent = duplicated_inputs and not weighted_product_cost(columns, scope)
            if unweighted_parent or (not columns and rows_duplicated(scope)):
                raise error_type(
                    'Aggregate input may be duplicated by a one-to-many join. '
                    'Aggregate from its source without the multiplying join, or use COUNT(DISTINCT key) '
                    'for entity counts. SUM(DISTINCT value) does not restore source grain.'
                )


def column_origin(scope, column, visited=()):
    """Resolve only transparent key projections; computed expressions are not join keys."""
    if id(scope) in visited:
        return None
    source = scope.sources.get(column.table)
    if isinstance(source, exp.Table):
        return (f'{source.db}.{source.name}', _column_name(column))
    if isinstance(source, Scope):
        projections = [p for p in source.expression.selects if p.alias_or_name.casefold() == column.name.casefold()]
        if len(projections) == 1 and isinstance(projections[0].unalias(), exp.Column):
            return column_origin(source, projections[0].unalias(), (*visited, id(scope)))
    return None
