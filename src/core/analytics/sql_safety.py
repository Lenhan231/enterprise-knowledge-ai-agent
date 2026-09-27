"""Allowlist validation for generated analytics SQL."""

from sqlglot import exp, parse
from sqlglot.errors import ParseError

SOURCE_CTES = {"authorized_financial_metrics", "authorized_documents"}
ALLOWED_COLUMNS = {
    "company", "domain", "title", "document_type", "format", "fiscal_year",
    "processing_status", "metric_name", "metric_label", "metric_value", "unit",
    "document_id", "page_number", "source_url", "source_quote", "official_url",
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
    if tables[0].name == "authorized_financial_metrics":
        projected_metrics = {
            selection.name.casefold()
            for selection in query.expressions
            if isinstance(selection, exp.Column)
        }
        if not {"metric_name", "fiscal_year"}.issubset(projected_metrics):
            raise UnsafeAnalyticsQuery(
                "Financial results must project metric_name and fiscal_year for exact evidence citations"
            )
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
    if "evidence_document_ids" not in output_names:
        raise UnsafeAnalyticsQuery("Query must return evidence_document_ids for source citations")
    evidence_projection = next(
        selection for selection in query.expressions
        if selection.alias_or_name.casefold() == "evidence_document_ids"
    )
    evidence_expression = evidence_projection.this if isinstance(evidence_projection, exp.Alias) else evidence_projection
    evidence_columns = {column.name.casefold() for column in evidence_expression.find_all(exp.Column)}
    if not isinstance(evidence_expression, exp.ArrayAgg) or evidence_columns != {"document_id"}:
        raise UnsafeAnalyticsQuery("evidence_document_ids must aggregate source document IDs")

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
