"""Allowlist validation for generated analytics SQL."""

from sqlglot import exp, parse
from sqlglot.errors import ParseError

SOURCE_CTES = {"authorized_financial_metrics", "authorized_business_metrics", "authorized_documents"}
ALLOWED_COLUMNS = {
    "company", "domain", "title", "document_type", "format", "fiscal_year",
    "processing_status", "metric_name", "metric_label", "metric_value", "unit",
    "value_qualifier", "reporting_period",
    "document_id", "metric_id", "business_metric_id", "page_number", "source_url", "source_quote",
    "metric_domain", "scope",
}
ALLOWED_AGGREGATES = (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.ArrayAgg)
ALLOWED_EXPRESSION_NODES = (exp.Case, exp.If)
MAX_ROWS = 100


class UnsafeAnalyticsQuery(ValueError):
    pass


def validate_analytics_sql(sql: str) -> str:
    """Accept one SELECT over one authorized CTE and cap its result size."""
    try:
        statements = parse(sql, read="postgres", max_nodes=500)
    except (ParseError, ValueError) as error:
        raise UnsafeAnalyticsQuery("The generated analytics query is invalid") from error
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise UnsafeAnalyticsQuery("Only one SELECT statement is allowed")

    query = statements[0]
    if any(query.args.get(key) for key in ("with", "joins", "into", "locks", "hint")):
        raise UnsafeAnalyticsQuery("Nested CTEs and joins are not allowed")
    tables = list(query.find_all(exp.Table))
    if len(tables) != 1 or tables[0].name not in SOURCE_CTES or tables[0].db or tables[0].catalog:
        raise UnsafeAnalyticsQuery("Query must read one authorized analytics source")
    metric_source = tables[0].name in {"authorized_financial_metrics", "authorized_business_metrics"}
    evidence_alias = ("evidence_business_metric_ids" if tables[0].name == "authorized_business_metrics"
                      else "evidence_metric_ids" if tables[0].name == "authorized_financial_metrics"
                      else "evidence_document_ids")
    if metric_source:
        projected_metrics = {
            selection.name.casefold()
            for selection in query.expressions
            if isinstance(selection, exp.Column)
        }
        if not {"metric_name", "fiscal_year"}.issubset(projected_metrics):
            raise UnsafeAnalyticsQuery("Metric results must project metric_name and fiscal_year for exact evidence citations")
    if any(isinstance(node, (exp.Subquery, exp.Union, exp.Intersect, exp.Except, exp.Window))
           for node in query.walk()):
        raise UnsafeAnalyticsQuery("Nested queries, set operations and windows are not allowed")
    if any(
        isinstance(node, exp.Func)
        and not isinstance(node, (*ALLOWED_AGGREGATES, *ALLOWED_EXPRESSION_NODES,
                                  exp.Connector, exp.Predicate, exp.Binary, exp.Unary))
        for node in query.walk()
    ):
        raise UnsafeAnalyticsQuery("Only approved aggregates and conditional CASE expressions are allowed")
    for column in query.find_all(exp.Column):
        if column.name.casefold() not in ALLOWED_COLUMNS or column.is_star:
            raise UnsafeAnalyticsQuery(f"Column is not available for analytics: {column.name}")
    output_names = [selection.alias_or_name.casefold() for selection in query.expressions]
    if len(output_names) != len(set(output_names)):
        raise UnsafeAnalyticsQuery("Selected columns must have unique names")
    if evidence_alias not in output_names:
        raise UnsafeAnalyticsQuery(f"Query must return {evidence_alias} for source citations")
    evidence_projection = next(
        selection for selection in query.expressions
        if selection.alias_or_name.casefold() == evidence_alias
    )
    evidence_expression = evidence_projection.this if isinstance(evidence_projection, exp.Alias) else evidence_projection
    evidence_columns = {column.name.casefold() for column in evidence_expression.find_all(exp.Column)}
    expected_evidence_column = {
        "evidence_metric_ids": "metric_id",
        "evidence_business_metric_ids": "business_metric_id",
        "evidence_document_ids": "document_id",
    }[evidence_alias]
    if not isinstance(evidence_expression, exp.ArrayAgg) or evidence_columns != {expected_evidence_column}:
        raise UnsafeAnalyticsQuery(f"{evidence_alias} must aggregate authorized source IDs")

    limit = query.args.get("limit")
    if limit:
        limit_value = limit.expression
        if not isinstance(limit_value, exp.Literal) or not limit_value.is_int:
            raise UnsafeAnalyticsQuery("LIMIT must be an integer literal")
        if int(limit_value.this) < 1:
            raise UnsafeAnalyticsQuery("LIMIT must be positive")
        limit.expression.set("this", str(min(int(limit_value.this), MAX_ROWS)))
    else:
        query.limit(MAX_ROWS, copy=False)
    return query.sql(dialect="postgres")


def validate_commerce_sql(sql: str, table_columns: dict[str, tuple[str, ...]]) -> str:
    """Validate one bounded read-only Commerce SELECT against domain table metadata."""
    try:
        statements = parse(sql, read="postgres", max_nodes=300)
    except (ParseError, ValueError) as error:
        raise UnsafeAnalyticsQuery("The generated Commerce query is invalid") from error
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise UnsafeAnalyticsQuery("Only one Commerce SELECT is allowed")

    query = statements[0]
    if any(query.args.get(key) for key in ("with", "into", "locks", "hint")):
        raise UnsafeAnalyticsQuery("CTEs and mutating/query-control clauses are not allowed")
    if any(isinstance(node, (exp.Subquery, exp.Union, exp.Intersect, exp.Except, exp.Window))
           for node in query.walk()):
        raise UnsafeAnalyticsQuery("Nested queries, set operations and windows are not allowed")

    aliases: dict[str, set[str]] = {}
    tables = list(query.find_all(exp.Table))
    if not tables:
        raise UnsafeAnalyticsQuery("Query must read an approved Commerce table")
    for table in tables:
        if table.db != "commerce" or table.catalog or table.name not in table_columns:
            raise UnsafeAnalyticsQuery("Query references a table outside the selected Commerce domain")
        alias = table.alias_or_name.casefold()
        aliases[alias] = {name.casefold() for name in table_columns[table.name]}
    if any(join.args.get("on") is None for join in query.find_all(exp.Join)):
        raise UnsafeAnalyticsQuery("Commerce joins must include an explicit ON condition")
    if any(selection.is_star for selection in query.expressions):
        raise UnsafeAnalyticsQuery("Wildcard projections are not allowed")

    projected_names = {selection.alias_or_name.casefold() for selection in query.expressions}
    for column in query.find_all(exp.Column):
        if column.is_star:
            raise UnsafeAnalyticsQuery("Wildcard projections are not allowed")
        qualifier = column.table.casefold()
        if qualifier:
            if qualifier not in aliases or column.name.casefold() not in aliases[qualifier]:
                raise UnsafeAnalyticsQuery(f"Column is not available in this Commerce domain: {column.sql()}")
        elif column.name.casefold() in projected_names and column.find_ancestor(exp.Order):
            continue
        else:
            matches = [alias for alias, columns in aliases.items() if column.name.casefold() in columns]
            if len(matches) != 1:
                if matches:
                    raise UnsafeAnalyticsQuery(
                        f"Unqualified column {column.name} is ambiguous across {', '.join(matches)}; qualify it"
                    )
                raise UnsafeAnalyticsQuery(f"Column is not available in this Commerce domain: {column.name}")
            column.set("table", exp.to_identifier(matches[0]))

    allowed_functions = (
        exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Round,
        exp.Extract, exp.DateTrunc, exp.Coalesce, exp.Nullif, exp.Cast,
        exp.Case, exp.If, exp.Connector, exp.Predicate, exp.Binary, exp.Unary,
    )
    if any(isinstance(node, exp.Func) and not isinstance(node, allowed_functions)
           for node in query.walk()):
        raise UnsafeAnalyticsQuery("Commerce query contains a non-approved function")
    output_names = [selection.alias_or_name.casefold() for selection in query.expressions]
    if len(output_names) != len(set(output_names)):
        raise UnsafeAnalyticsQuery("Selected Commerce columns must have unique names")
    group = query.args.get("group")
    grouped_expressions = {
        expression.sql(dialect="postgres", normalize=True)
        for expression in (group.expressions if group else ())
    }
    for selection in query.expressions:
        expression = selection.this if isinstance(selection, exp.Alias) else selection
        is_aggregate = any(isinstance(node, ALLOWED_AGGREGATES) for node in expression.walk())
        normalized = expression.sql(dialect="postgres", normalize=True)
        if not is_aggregate and normalized not in grouped_expressions:
            raise UnsafeAnalyticsQuery("Commerce results must be aggregated or grouped, not raw records")

    limit = query.args.get("limit")
    if limit:
        value = limit.expression
        if not isinstance(value, exp.Literal) or not value.is_int or int(value.this) < 1:
            raise UnsafeAnalyticsQuery("LIMIT must be a positive integer literal")
        limit.expression.set("this", str(min(int(value.this), MAX_ROWS)))
    else:
        query.limit(MAX_ROWS, copy=False)
    return query.sql(dialect="postgres")
