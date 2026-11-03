"""Prompt and validate read-only SQL for the approved commerce schema."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import ParseError, TokenError

from core.analytics.metric_ontology import get_metric_definition, resolve_metric_names
from core.analytics.join_validation import PRIMARY_KEYS, validate_join_aggregations, approved_derived_join, column_origin
from core.analytics.metric_validation import _single_snapshot
from sqlglot.optimizer.scope import traverse_scope
from core.prompts.sql import SQL_GENERATION_PROMPT, SQL_REPAIR_PROMPT, INVENTORY_SQL_INSTRUCTIONS


MAX_RESULT_ROWS = 200
APPROVED_COLUMNS: dict[str, frozenset[str]] = {
    "commerce.sales": frozenset({"date", "revenue", "cogs"}),
    "commerce.orders": frozenset({
        "order_id", "order_date", "customer_id", "zip", "order_status", "payment_method", "device_type", "order_source",
    }),
    "commerce.customers": frozenset({
        "customer_id", "zip", "city", "signup_date", "gender", "age_group", "acquisition_channel",
    }),
    "commerce.payments": frozenset({"order_id", "payment_method", "payment_value", "installments"}),
    "commerce.order_items": frozenset({
        "order_item_id", "order_id", "product_id", "quantity", "unit_price", "discount_amount", "promo_id", "promo_id_2",
    }),
    "commerce.geography": frozenset({"zip", "city", "region", "district"}),
    "commerce.inventory": frozenset({
        "snapshot_date", "product_id", "stock_on_hand", "units_received", "units_sold", "stockout_days",
        "days_of_supply", "fill_rate", "stockout_flag", "overstock_flag", "reorder_flag", "sell_through_rate",
        "product_name", "category", "segment", "year", "month",
    }),
    "commerce.products": frozenset({"product_id", "product_name", "category", "segment", "size", "color", "price", "cogs"}),
    "commerce.promotions": frozenset({
        "promo_id", "promo_name", "promo_type", "discount_value", "start_date", "end_date", "applicable_category",
        "promo_channel", "stackable_flag", "min_order_value",
    }),
    "commerce.returns": frozenset({"return_id", "order_id", "product_id", "return_date", "return_reason", "return_quantity", "refund_amount"}),
    "commerce.reviews": frozenset({"review_id", "order_id", "product_id", "review_date", "rating", "review_title"}),
    "commerce.shipments": frozenset({"order_id", "ship_date", "delivery_date", "shipping_fee"}),
    "commerce.web_traffic": frozenset({
        "date", "sessions", "unique_visitors", "page_views", "bounce_rate", "avg_session_duration_sec", "traffic_source",
    }),
}


def _edge(left_table: str, left_column: str, right_table: str, right_column: str):
    return frozenset({(left_table, left_column), (right_table, right_column)})


APPROVED_JOINS = frozenset({
    _edge("commerce.customers", "customer_id", "commerce.orders", "customer_id"),
    _edge("commerce.customers", "zip", "commerce.geography", "zip"),
    _edge("commerce.orders", "order_id", "commerce.payments", "order_id"),
    _edge("commerce.orders", "order_id", "commerce.order_items", "order_id"),
    _edge("commerce.orders", "zip", "commerce.geography", "zip"),
    _edge("commerce.order_items", "product_id", "commerce.products", "product_id"),
    _edge("commerce.order_items", "promo_id", "commerce.promotions", "promo_id"),
    _edge("commerce.order_items", "promo_id_2", "commerce.promotions", "promo_id"),
    _edge("commerce.inventory", "product_id", "commerce.products", "product_id"),
    _edge("commerce.returns", "order_id", "commerce.orders", "order_id"),
    _edge("commerce.returns", "product_id", "commerce.products", "product_id"),
    _edge("commerce.reviews", "order_id", "commerce.orders", "order_id"),
    _edge("commerce.reviews", "product_id", "commerce.products", "product_id"),
    _edge("commerce.shipments", "order_id", "commerce.orders", "order_id"),
})
APPROVED_DATE_COLUMNS = frozenset({
    ("commerce.customers", "signup_date"),
    ("commerce.inventory", "snapshot_date"),
    ("commerce.orders", "order_date"),
    ("commerce.promotions", "start_date"), ("commerce.promotions", "end_date"),
    ("commerce.returns", "return_date"),
    ("commerce.reviews", "review_date"),
    ("commerce.sales", "date"),
    ("commerce.shipments", "ship_date"), ("commerce.shipments", "delivery_date"),
    ("commerce.web_traffic", "date"),
})

APPROVED_FUNCTIONS = frozenset({
    "ABS", "AND", "AVG", "CAST", "CEIL", "COALESCE", "COUNT", "DATE_PART", "DATE_TRUNC", "EXTRACT", "FLOOR", "GREATEST",
    "LEAST", "LOWER", "MAX", "MIN", "NULLIF", "OR", "ROUND", "STRING_AGG", "SUM", "TIMESTAMP_TRUNC", "UPPER", "EXISTS",
})
FORBIDDEN_NODES = (exp.Command, exp.Into, exp.Lock, exp.Union, exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create)


class SQLValidationError(ValueError):
    """Raised when model-generated SQL is outside the read-only query subset."""


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class QueryPlan:
    sql: str | None = None
    parameters: tuple[Any, ...] = ()
    explanation: str = ""
    clarification: str | None = None


def _source_name(table: exp.Table) -> str:
    if not table.db or table.catalog:
        raise SQLValidationError("Tables must be fully qualified in the commerce schema.")
    return f"{table.db}.{table.name}".casefold()


def _output_columns(select: exp.Select) -> frozenset[str]:
    names = set()
    for projection in select.expressions:
        name = projection.alias_or_name
        if not name:
            raise SQLValidationError("Subquery columns must have names.")
        names.add(name.casefold())
    return frozenset(names)


def validate_commerce_sql(sql: str) -> ValidatedSQL:
    """Validate one bounded SELECT, including its nested SELECTs and CTEs."""
    try:
        statements = parse(sql, read="postgres")
    except (ParseError, TokenError) as error:
        raise SQLValidationError("SQL could not be parsed.") from error
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise SQLValidationError("Exactly one SELECT statement is allowed.")

    tree = statements[0]
    if any(tree.find(node_type) for node_type in FORBIDDEN_NODES):
        raise SQLValidationError("This SQL structure is not allowed.")
    if any(isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count) for node in tree.walk()):
        raise SQLValidationError("SELECT * is not allowed.")

    ctes = {cte.alias_or_name.casefold(): cte.this for cte in tree.find_all(exp.CTE)}
    relations: dict[str, tuple[str | None, frozenset[str]]] = {}
    sources: list[str] = []
    for table in tree.find_all(exp.Table):
        name = table.name.casefold()
        alias = (table.alias_or_name or name).casefold()
        if name in ctes and not table.db:
            relation = (None, _output_columns(ctes[name]))
        else:
            source = _source_name(table)
            if source not in APPROVED_COLUMNS:
                raise SQLValidationError(f"Source is not approved: {source}")
            relation = (source, APPROVED_COLUMNS[source])
            sources.append(source)
        if alias in relations and relations[alias] != relation:
            raise SQLValidationError("Table aliases must be unique across the query.")
        relations[alias] = relation

    for subquery in tree.find_all(exp.Subquery):
        alias = (subquery.alias_or_name or "").casefold()
        if alias:
            relation = (None, _output_columns(subquery.this))
            if alias in relations and relations[alias] != relation:
                raise SQLValidationError("Table aliases must be unique across the query.")
            relations[alias] = relation

    if not sources:
        raise SQLValidationError("The query must read an approved commerce source.")

    for column in tree.find_all(exp.Column):
        if not column.table:
            raise SQLValidationError(f"Columns must use a table alias: {column.name}")
        relation = relations.get(column.table.casefold())
        if relation is None or column.name.casefold() not in relation[1]:
            raise SQLValidationError(f"Column is not approved: {column.sql()}")

    for function in tree.find_all(exp.Func):
        name = function.name if isinstance(function, exp.Anonymous) else function.sql_name()
        if name.upper() not in APPROVED_FUNCTIONS:
            raise SQLValidationError(f"Function is not approved: {name}")
        if isinstance(function, exp.Cast) and function.to.this not in {exp.DataType.Type.DATE, exp.DataType.Type.DECIMAL}:
            raise SQLValidationError("Only DATE and NUMERIC casts are approved.")

    def join_equalities(expression):
        if isinstance(expression, exp.And):
            return (*join_equalities(expression.this), *join_equalities(expression.expression))
        if not isinstance(expression, exp.EQ):
            raise SQLValidationError("JOIN conditions must use approved equality keys.")
        left, right = expression.this, expression.expression
        if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
            raise SQLValidationError("JOIN conditions must compare approved columns.")
        left_relation = relations.get(left.table.casefold())
        right_relation = relations.get(right.table.casefold())
        if not left_relation or not right_relation or not left_relation[0] or not right_relation[0]:
            raise SQLValidationError("JOINs must connect approved base tables.")
        edge = _edge(left_relation[0], left.name.casefold(), right_relation[0], right.name.casefold())
        if edge not in APPROVED_JOINS:
            raise SQLValidationError("JOIN does not match an approved relationship.")
        return (expression,)

    def join_predicates(expression):
        if isinstance(expression, exp.And):
            yield from join_predicates(expression.this)
            yield from join_predicates(expression.expression)
        else:
            yield expression

    scopes_by_select = {id(scope.expression): scope for scope in traverse_scope(tree)}
    for exists in tree.find_all(exp.Exists):
        scope = scopes_by_select.get(id(exists.this))
        if not scope or not scope.external_columns:
            raise SQLValidationError('EXISTS must express a correlated approved-key presence check.')
        for column in scope.external_columns:
            equality = column.parent
            if not isinstance(equality, exp.EQ) or not isinstance(equality.this, exp.Column) or not isinstance(equality.expression, exp.Column):
                raise SQLValidationError('EXISTS correlations must use approved equality keys.')
            other = equality.expression if equality.this is column else equality.this
            parent = scope.parent
            while parent and column.table not in parent.sources:
                parent = parent.parent
            origins = (column_origin(parent, column) if parent else None, column_origin(scope, other))
            if not all(origins) or frozenset(origins) not in APPROVED_JOINS or equality.find_ancestor(exp.Or):
                raise SQLValidationError('EXISTS correlation does not match an approved relationship.')
    for join in tree.find_all(exp.Join):
        if (join.kind or "").casefold() == "cross" or not join.args.get("on"):
            raise SQLValidationError("CROSS JOIN and JOIN without ON are not allowed.")
        keys = 0
        predicates = list(join_predicates(join.args['on']))
        scope = scopes_by_select[id(join.find_ancestor(exp.Select))]
        if join.this.alias_or_name.casefold() not in {c.table.casefold() for p in predicates for c in p.find_all(exp.Column)}:
            raise SQLValidationError('JOIN condition must connect the joined relation.')
        if any(isinstance(p, exp.EQ) and any(
                isinstance(c, exp.Column) and not relations[c.table.casefold()][0]
                for c in (p.this, p.expression)) for p in predicates):
            if not all(isinstance(p, exp.EQ) for p in predicates) or not approved_derived_join(scope, predicates, APPROVED_JOINS):
                raise SQLValidationError('Derived joins require complete grouped keys and approved dimension lineage.')
            continue
        for predicate in predicates:
            # Snapshot filters belong in ON for an outer join to preserve missing observations.
            if isinstance(predicate, (exp.EQ, exp.GTE, exp.GT, exp.LTE, exp.LT)):
                left, right = predicate.this, predicate.expression
                column, value = (left, right) if isinstance(left, exp.Column) else (right, left)
                if (isinstance(column, exp.Column)
                        and (relations.get(column.table.casefold(), (None,))[0], column.name.casefold()) in APPROVED_DATE_COLUMNS
                        and isinstance(value, (exp.Parameter, exp.Literal))):
                    continue
            keys += len(join_equalities(predicate))
        if not keys:
            raise SQLValidationError('JOIN requires an approved relationship in addition to any date filters.')

    validate_join_aggregations(tree, SQLValidationError)

    def owning_select(node):
        while node is not None and not isinstance(node, exp.Select):
            node = node.parent
        return node

    select_scopes = {id(scope.expression): scope for scope in traverse_scope(tree)}
    for select in tree.find_all(exp.Select):
        inventory_sums = [
            aggregate for aggregate in select.find_all(exp.Sum)
            if owning_select(aggregate) is select and any(
                relations.get(column.table.casefold(), (None,))[0] == "commerce.inventory"
                and column.name.casefold() == "stock_on_hand"
                for column in aggregate.find_all(exp.Column)
            )
        ]
        if not inventory_sums:
            continue
        if not _single_snapshot([select_scopes[id(select)]], ()):
            raise SQLValidationError("Inventory stock cannot be summed across snapshots.")

    limit = tree.args.get("limit")
    value = getattr(getattr(limit, "expression", None), "this", None)
    if limit is None or not str(value).isdigit() or not 1 <= int(value) <= MAX_RESULT_ROWS:
        raise SQLValidationError(f"The final SELECT needs LIMIT 1..{MAX_RESULT_ROWS}.")

    return ValidatedSQL(sql=sql, sources=tuple(dict.fromkeys(sources)))


def parse_json_response(raw: str):
    if isinstance(raw,str):
        raw = raw.strip()
        if raw.startswith('```json') and raw.endswith('```'):
            raw = raw[7:-3].strip()
    return json.loads(raw)


def decode_query_plan(raw: str) -> QueryPlan:
    try:
        payload = parse_json_response(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise SQLValidationError("The model did not return valid JSON.") from error
    if not isinstance(payload, dict):
        raise SQLValidationError("The query plan must be a JSON object.")
    clarification = payload.get("clarification")
    if clarification is not None:
        if not isinstance(clarification, str) or not clarification.strip():
            raise SQLValidationError("Clarification must be a non-empty string.")
        return QueryPlan(clarification=clarification.strip())
    sql = payload.get("sql")
    parameters = payload.get("parameters", [])
    explanation = payload.get("explanation", "")
    if not isinstance(sql, str) or not isinstance(parameters, list) or not isinstance(explanation, str):
        raise SQLValidationError("The query plan must include SQL, a parameter list, and an explanation.")
    if len(parameters) > 32 or any(not isinstance(value, (str, int, float, bool, type(None))) for value in parameters):
        raise SQLValidationError("Query parameters must be at most 32 scalar JSON values.")
    validated = validate_commerce_sql(sql)
    parameter_indexes = sorted({
        int(node.this.this)
        for node in parse(sql, read="postgres")[0].find_all(exp.Parameter)
        if isinstance(node.this, exp.Literal) and str(node.this.this).isdigit()
    })
    if parameter_indexes != list(range(1, len(parameters) + 1)):
        raise SQLValidationError("SQL placeholders must match the supplied parameters exactly.")
    date_indexes = _date_parameter_indexes(sql)
    for index in date_indexes:
        value = parameters[index - 1]
        if isinstance(value, str):
            try:
                parameters[index - 1] = date.fromisoformat(value)
            except ValueError as error:
                raise SQLValidationError(f"Date parameter ${index} must use YYYY-MM-DD format.") from error
    tree = parse(sql, read='postgres')[0]
    changed = False
    for parameter in list(tree.find_all(exp.Parameter)):
        index = int(parameter.this.this)
        if index in date_indexes and isinstance(parameters[index-1], date) and parameter.find_ancestor(
                exp.TimestampTrunc, exp.DateTrunc, exp.Extract):
            parameter.replace(exp.Cast(this=parameter.copy(), to=exp.DataType.build('DATE')))
            changed = True
    if changed:
        sql = tree.sql(dialect='postgres')
        validate_commerce_sql(sql)
    return QueryPlan(sql=sql, parameters=tuple(parameters), explanation=explanation.strip())


def _date_parameter_indexes(sql: str) -> set[int]:
    tree = parse(sql, read="postgres")[0]
    table_sources = {
        (table.alias_or_name or table.name).casefold(): _source_name(table)
        for table in tree.find_all(exp.Table) if table.db
    }
    indexes = set()
    comparisons = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)
    for comparison in tree.find_all(comparisons):
        for column_side, value_side in ((comparison.this, comparison.expression),
                                        (comparison.expression, comparison.this)):
            if not any((table_sources.get(column.table.casefold()), column.name.casefold())
                       in APPROVED_DATE_COLUMNS for column in column_side.find_all(exp.Column)):
                continue
            indexes.update(
                int(parameter.this.this)
                for parameter in value_side.find_all(exp.Parameter)
                if isinstance(parameter.this, exp.Literal) and str(parameter.this.this).isdigit()
            )
    return indexes


def relevant_schema_tables(question, definitions):
    """Select prompt context only; authorization always uses the full backend allowlist."""
    text = question.casefold().replace('_', ' ')
    tables = {table for definition in definitions.values()
              for table in re.findall(r'commerce\.\w+', definition['source'])}
    cues = {
        'inventory': r'inventory|stock|snapshot|tồn kho',
        'products': r'product|category|catalog|sku|sản phẩm|danh mục',
        'returns': r'return|refund|trả hàng|hoàn hàng',
        'orders': r'order|ordered|đơn hàng',
        'order_items': r'quantity|quantities|ordered units|line value|order items|ordered quantities',
        'customers': r'customer|khách hàng',
        'geography': r'region|district|city|khu vực|thành phố',
        'payments': r'payment|installment|thanh toán',
        'promotions': r'promotion|promo|khuyến mãi',
        'reviews': r'review|rating|đánh giá',
        'shipments': r'shipment|shipping|delivery|giao hàng',
        'web_traffic': r'session|traffic|bounce|truy cập',
        'sales': r'revenue|cogs|gross profit|doanh thu|lợi nhuận',
    }
    tables.update('commerce.'+name for name, pattern in cues.items() if re.search(pattern, text))
    # Supply bridge tables for approved paths, without inventing direct fact-to-fact joins.
    if tables & {'commerce.inventory', 'commerce.returns', 'commerce.reviews', 'commerce.order_items'}:
        tables.add('commerce.products')
    if 'commerce.orders' in tables and 'commerce.products' in tables:
        tables.add('commerce.order_items')
    if 'commerce.order_items' in tables:
        tables.add('commerce.orders')
    return tables or set(APPROVED_COLUMNS)


def approved_join_path(tables):
    reached = {min(tables)} if tables else set()
    while True:
        expanded = reached | {table for edge in APPROVED_JOINS for table, _ in edge
                              if any(source in reached for source, _ in edge) and table in tables}
        if expanded == reached:
            return bool(tables) and reached == set(tables)
        reached = expanded


def build_sql_prompt(
    question: str, *, validation_error: str | None = None, previous_response: str | None = None,
    metric_names: set[str] | None = None, interpretation: dict | None = None,
) -> str:
    metrics = sorted(resolve_metric_names(question) if metric_names is None else metric_names)
    definitions = {name: get_metric_definition(name) for name in metrics}
    stored_fields = {}
    if interpretation and interpretation.get('representation') == 'product':
        stored_fields = {name: d.get('scalar_formula') or d['formula'].split(' within ')[0] for name,d in definitions.items()}
        definitions = {name: {**d,'formula':stored_fields[name],'aggregation':'value'} for name,d in definitions.items()}
    inventory = any(definition.get('domain') == 'inventory_management' for definition in definitions.values())
    tables = relevant_schema_tables(question, definitions)
    prompt_columns = {table: set(columns) for table, columns in APPROVED_COLUMNS.items() if table in tables}
    if inventory:
        prompt_columns['commerce.inventory'] -= {'year', 'month', 'category', 'segment', 'product_name'}
        prompt_columns['commerce.products'] -= {'price', 'cogs'}
    schema = "\n".join(f"{table}: {', '.join(sorted(columns))}" for table, columns in prompt_columns.items())
    joins = "\n".join(f"{left[0]}.{left[1]} = {right[0]}.{right[1]}" for join in sorted(APPROVED_JOINS, key=lambda edge: sorted(edge))
                       for left, right in [sorted(join)] if left[0] in tables and right[0] in tables)
    functions = ", ".join(sorted(APPROVED_FUNCTIONS - {"AND"}))
    return (
        SQL_GENERATION_PROMPT.format(
            inventory_instructions=INVENTORY_SQL_INSTRUCTIONS if inventory and not (
                'commerce.inventory' in tables and tables & {'commerce.orders', 'commerce.order_items'}) else "",
            functions=functions,
            max_rows=MAX_RESULT_ROWS,
            metrics=json.dumps({'metrics': metrics}),
            definitions=json.dumps(definitions, ensure_ascii=False),
            schema=schema,
            joins=joins,
            question=question,
        )
        + '\nPrimary keys (one row per key; inventory is product_snapshot grain): '+json.dumps(
            {table: sorted(PRIMARY_KEYS[table.split('.')[1]]) for table in sorted(tables)})
        + '\nExplicit calculations with clear operands are supported without creating a canonical KPI. '
          'Aliases must be unique across the entire query, including base tables inside CTEs and outer CTE aliases. '
          'For returned-unit / ordered-unit ratios, independently aggregate returns.return_quantity by return_date '
          'and order_items.quantity by orders.order_date at the requested product grain and period, '
          'then join their complete grouped product keys. Cast numerator AS NUMERIC and divide by NULLIF(denominator,0). '
          'This is not the canonical order-based return_rate. Never join raw fact rows for this ratio. '
          'For inventory/order presence use correlated EXISTS through approved product keys; do not multiply inventory rows. '
          'Compare inventory and order measures using independent category aggregates, never an unaggregated fact join. '
          'For an explicit inventory units_sold / ordered-quantity comparison, the inventory CTE selects only '
          'products.category and SUM(inventory.units_sold), groups by category, filters the entire requested period, '
          'and has no inner LIMIT. This explicit movement-observation sum is not a balance KPI. '
          'FULL JOIN the complete category aggregates, select COALESCE of category keys, and keep absent measures NULL. '
          'For stockout_flag=true plus order presence, select snapshot_date and product identity, filter the flag '
          'and the requested inventory period, use EXISTS with order_items.product_id=products.product_id '
          'and filter orders.order_date independently to the requested order period. '
          'Do not treat missing observations as zero or infer that inventory units_sold equals ordered quantities. '
          'For duplicate rows report excess rows SUM(group_count-1), COALESCE to zero; distinguish duplicate groups '
          'and all participating rows when those are explicitly requested. '
          'Use typed DATE range parameters for transaction periods; avoid EXTRACT on an untyped parameter.'
          ' Product names are not unique: product-level results must include product_id, and product-level '
          'aggregates must group by product_id as well as any displayed name.'
          ' For missing returned product-order pairs, anchor returns through its approved products and orders joins, '
          'then use NOT EXISTS order_items with order_items.product_id=products.product_id AND '
          'order_items.order_id=orders.order_id. Select DISTINCT product_id,order_id when pairs are requested. '
          'An indirect approved path does not require user confirmation; preserve source grain and validated keys.'
        + ('\nStored projection fields: '+json.dumps(stored_fields)+
           '. Select these directly from the inventory alias. Do not aggregate or GROUP BY in product representation. '
           'Product identity may use inventory.product_id or the joined products.product_id.\n' if stored_fields else '')
        + ('\nValidated interpretation: '+json.dumps(interpretation,ensure_ascii=False)+
           '\nPreserve exactly these metrics, dimensions, source-row filters, date scope, output grain and ranking. '
           'Project snapshot_date plus only the requested dimensions and metrics. Product representation uses stored scalar values. '
           'Use GROUP BY qualified columns, ORDER BY positions, direct SELECT without CTE/HAVING/DISTINCT. '
           'Use the declared ranking limit, otherwise LIMIT 200. For an inclusive date range use snapshot_date >= start '
           'AND snapshot_date < the day AFTER end. For latest use the unfiltered MAX subquery. '
           'Filters use field <operator> parameter (IN uses a list of parameters); do not add other restrictions.'
           ' A concrete snapshot in the validated interpretation may have been resolved by the server from latest; '
           'use that concrete date, not a MAX subquery, when time.mode is snapshot.'
           if interpretation is not None else '')
        + (SQL_REPAIR_PROMPT.format(validation_error=validation_error, previous_response=previous_response)
           if validation_error is not None else "")
    )
