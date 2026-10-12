"""Controlled commerce text-to-SQL planning and structural validation.

The interpreter produces a small semantic plan. SQL is compiled by application
code, then parsed and checked again before the repository may execute it.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from core.analytics.metric_ontology import get_metric_definition, resolve_metric_names


MAX_RESULT_ROWS = 200

# This is intentionally narrower than the live schema. Customer and payment
# data are not approved for the first text-to-SQL slice.
APPROVED_COLUMNS: dict[str, frozenset[str]] = {
    "commerce.sales": frozenset({"date", "revenue", "cogs"}),
    "commerce.orders": frozenset({
        "order_id", "order_date", "zip", "order_status", "payment_method",
        "device_type", "order_source",
    }),
    "commerce.order_items": frozenset({
        "order_item_id", "order_id", "product_id", "quantity", "unit_price",
        "discount_amount", "promo_id", "promo_id_2",
    }),
    "commerce.geography": frozenset({"zip", "city", "region", "district"}),
    "commerce.inventory": frozenset({
        "snapshot_date", "product_id", "stock_on_hand", "units_received",
        "units_sold", "stockout_days", "days_of_supply", "fill_rate",
        "stockout_flag", "overstock_flag", "reorder_flag", "sell_through_rate",
        "product_name", "category", "segment", "year", "month",
    }),
    "commerce.products": frozenset({
        "product_id", "product_name", "category", "segment", "size", "color",
        "price", "cogs",
    }),
    "commerce.promotions": frozenset({
        "promo_id", "promo_name", "promo_type", "discount_value", "start_date",
        "end_date", "applicable_category", "promo_channel", "stackable_flag",
        "min_order_value",
    }),
    "commerce.returns": frozenset({
        "return_id", "order_id", "product_id", "return_date", "return_reason",
        "return_quantity", "refund_amount",
    }),
    "commerce.reviews": frozenset({
        "review_id", "order_id", "product_id", "review_date", "rating",
        "review_title",
    }),
    "commerce.shipments": frozenset({
        "order_id", "ship_date", "delivery_date", "shipping_fee",
    }),
    "commerce.web_traffic": frozenset({
        "date", "sessions", "unique_visitors", "page_views", "bounce_rate",
        "avg_session_duration_sec", "traffic_source",
    }),
}


def _edge(
    left_table: str,
    left_column: str,
    right_table: str,
    right_column: str,
) -> frozenset[tuple[str, str]]:
    return frozenset({(left_table, left_column), (right_table, right_column)})


APPROVED_JOINS = frozenset({
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

APPROVED_FUNCTIONS = frozenset({
    "AND", "AVG", "COALESCE", "COUNT", "DATE_TRUNC", "MAX", "MIN", "NULLIF",
    "ROUND", "SUM", "TIMESTAMP_TRUNC",
})


class SQLValidationError(ValueError):
    """Raised when generated SQL is outside the approved read-only subset."""


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class QueryPlan:
    sql: str
    parameters: tuple[Any, ...]
    sources: tuple[str, ...]
    metric: str | None
    metric_definition: str
    time_grain: str | None
    output_shape: str
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class Interpretation:
    plan: QueryPlan | None = None
    clarification: str | None = None
    unsupported_reason: str | None = None


def _table_name(table: exp.Table) -> str:
    if not table.db or table.catalog:
        raise SQLValidationError("Mọi bảng phải được định danh trực tiếp trong schema commerce.")
    return f"{table.db}.{table.name}".casefold()


def validate_commerce_sql(sql: str) -> ValidatedSQL:
    """Parse and enforce the approved single-statement PostgreSQL subset."""
    try:
        statements = parse(sql, read="postgres")
    except ParseError as error:
        raise SQLValidationError("SQL không phân tích được.") from error
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise SQLValidationError("Chỉ cho phép đúng một câu lệnh SELECT.")

    tree = statements[0]
    if sum(1 for _ in tree.find_all(exp.Select)) != 1:
        raise SQLValidationError("Không cho phép truy vấn lồng hoặc CTE.")
    if any(tree.find(node_type) for node_type in (
        exp.Subquery, exp.With, exp.Union, exp.Command, exp.Into, exp.Lock,
    )):
        raise SQLValidationError("Cấu trúc truy vấn không được phép.")

    tables = list(tree.find_all(exp.Table))
    if not tables:
        raise SQLValidationError("Truy vấn phải đọc từ một nguồn đã phê duyệt.")
    aliases: dict[str, str] = {}
    sources: list[str] = []
    for table in tables:
        source = _table_name(table)
        if source not in APPROVED_COLUMNS:
            raise SQLValidationError(f"Nguồn không được phép: {source}")
        alias = (table.alias_or_name or table.name).casefold()
        if alias in aliases:
            raise SQLValidationError("Alias bảng bị trùng.")
        aliases[alias] = source
        sources.append(source)

    for star in tree.find_all(exp.Star):
        raise SQLValidationError("Không cho phép SELECT *.")

    for column in tree.find_all(exp.Column):
        if not column.table:
            raise SQLValidationError(f"Cột phải có alias bảng: {column.name}")
        source = aliases.get(column.table.casefold())
        if source is None or column.name.casefold() not in APPROVED_COLUMNS[source]:
            raise SQLValidationError(f"Cột không được phép: {column.sql()}")

    for function in tree.find_all(exp.Func):
        function_name = (
            function.name if isinstance(function, exp.Anonymous) else function.sql_name()
        ).upper()
        if function_name not in APPROVED_FUNCTIONS:
            raise SQLValidationError(f"Hàm không được phép: {function_name}")

    for join in tree.find_all(exp.Join):
        if join.kind.casefold() == "cross" or not join.args.get("on"):
            raise SQLValidationError("Không cho phép CROSS JOIN hoặc JOIN thiếu điều kiện.")
        equality = join.args["on"]
        approved_equality = isinstance(equality, exp.EQ)
        if approved_equality:
            left, right = equality.this, equality.expression
            approved_equality = isinstance(left, exp.Column) and isinstance(right, exp.Column)
        if approved_equality:
            left_source = aliases.get(left.table.casefold())
            right_source = aliases.get(right.table.casefold())
            approved_equality = bool(left_source and right_source and _edge(
                left_source, left.name.casefold(), right_source, right.name.casefold()
            ) in APPROVED_JOINS)
        if not approved_equality:
            raise SQLValidationError("JOIN không khớp khóa quan hệ đã phê duyệt.")

    inventory_stock_sums = [
        aggregate
        for aggregate in tree.find_all(exp.Sum)
        if any(
            aliases.get(column.table.casefold()) == "commerce.inventory"
            and column.name.casefold() == "stock_on_hand"
            for column in aggregate.find_all(exp.Column)
        )
    ]
    if inventory_stock_sums:
        grouped_by_snapshot = any(
            aliases.get(column.table.casefold()) == "commerce.inventory"
            and column.name.casefold() == "snapshot_date"
            for column in (tree.args.get("group") or exp.Group()).find_all(exp.Column)
        )
        filtered_to_snapshot = False
        for equality in (tree.args.get("where") or exp.Where()).find_all(exp.EQ):
            pairs = ((equality.this, equality.expression), (equality.expression, equality.this))
            if any(
                isinstance(column, exp.Column)
                and aliases.get(column.table.casefold()) == "commerce.inventory"
                and column.name.casefold() == "snapshot_date"
                and isinstance(value, (exp.Parameter, exp.Literal))
                for column, value in pairs
            ):
                filtered_to_snapshot = True
                break
        if not grouped_by_snapshot and not filtered_to_snapshot:
            raise SQLValidationError(
                "Không được cộng tồn kho giữa nhiều snapshot."
            )

    limit = tree.args.get("limit")
    limit_value = getattr(getattr(limit, "expression", None), "this", None)
    valid_limit = (
        limit is not None
        and str(limit_value).isdigit()
        and 1 <= int(limit_value) <= MAX_RESULT_ROWS
    )
    if not valid_limit:
        raise SQLValidationError(f"LIMIT phải nằm trong khoảng 1..{MAX_RESULT_ROWS}.")

    return ValidatedSQL(sql=sql, sources=tuple(dict.fromkeys(sources)))


class CommerceQuestionInterpreter:
    """Interpret a bounded set of schema-grounded analytical and lookup requests."""

    _RANKING = re.compile(
        r"thấp nhất|ít nhất|nhỏ nhất|cao nhất|nhiều nhất|lớn nhất|lowest|highest|minimum|maximum",
        re.I,
    )
    _EXPLICIT_GRAIN = re.compile(
        r"theo ngày|từng ngày|ngày nào|theo tháng|từng tháng|tháng nào|"
        r"khu vực|vùng|region|daily|monthly|by day|by month",
        re.I,
    )

    def interpret(self, question: str) -> Interpretation:
        text = question.strip()
        metrics = resolve_metric_names(text)
        if metrics & {"revenue", "regional_revenue"} and self._RANKING.search(text):
            if re.search(r"(?<!\d)(?:19|20)\d{2}(?!\d)", text) and not self._EXPLICIT_GRAIN.search(text):
                return Interpretation(clarification=(
                    "Bạn muốn so sánh doanh thu theo ngày hay tháng trong năm đó?"
                ))

        period = self._period(text)
        daily_revenue = bool(re.search(r"theo ngày|từng ngày|ngày nào|daily|by day", text, re.I))
        if metrics == {"revenue"} and daily_revenue:
            if period is None:
                return Interpretation(clarification="Vui lòng nêu tháng hoặc năm cần phân tích.")
            start, end, period_grain = period
            ranking = self._RANKING.search(text)
            if ranking:
                descending = bool(re.search(
                    r"cao nhất|nhiều nhất|lớn nhất|highest|maximum", text, re.I
                ))
                order = "DESC" if descending else "ASC"
                limit = 1
            elif period_grain == "year":
                return Interpretation(clarification=(
                    "Bảng theo ngày cho cả năm vượt giới hạn kết quả; vui lòng chọn một tháng."
                ))
            else:
                order = "ASC"
                limit = MAX_RESULT_ROWS
            sql = (
                "SELECT s.date AS period, SUM(s.revenue) AS revenue "
                "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 "
                f"GROUP BY s.date ORDER BY SUM(s.revenue) {order} LIMIT {limit}"
            )
            validated = validate_commerce_sql(sql)
            definition = get_metric_definition("revenue")
            return Interpretation(plan=QueryPlan(
                sql=sql,
                parameters=(start, end),
                sources=validated.sources,
                metric="revenue",
                metric_definition=str(definition["formula"]),
                time_grain="day",
                output_shape="scalar" if ranking else "table",
                limitations=tuple(definition.get("limitations", ())),
            ))

        product = re.search(r"(?:sản phẩm|product)\s*(?:mã|id)?\s*#?\s*(\d+)(?!\d)", text, re.I)
        if product:
            sql = (
                "SELECT p.product_id, p.product_name, p.category, p.segment, p.size, "
                "p.color, p.price, p.cogs FROM commerce.products AS p "
                "WHERE p.product_id = $1 LIMIT 50"
            )
            validated = validate_commerce_sql(sql)
            return Interpretation(plan=QueryPlan(
                sql=sql,
                parameters=(int(product.group(1)),),
                sources=validated.sources,
                metric=None,
                metric_definition="Tra cứu bản ghi sản phẩm theo product_id.",
                time_grain=None,
                output_shape="records",
                limitations=("Đơn vị tiền tệ của price và cogs không được dataset xác định.",),
            ))

        if metrics & {"sessions", "bounce_rate"}:
            if period is None:
                return Interpretation(clarification="Vui lòng nêu tháng hoặc năm cần phân tích.")
            metric = "sessions" if "sessions" in metrics else "bounce_rate"
            definition = get_metric_definition(metric)
            aggregate = "SUM(wt.sessions)" if metric == "sessions" else "AVG(wt.bounce_rate)"
            start, end, time_grain = period
            by_source = bool(re.search(
                r"theo nguồn|nguồn truy cập|traffic source|by source", text, re.I
            ))
            select_parts = []
            group_parts = []
            if by_source:
                select_parts.append("wt.traffic_source AS traffic_source")
                group_parts.append("wt.traffic_source")
            select_parts.append(f"{aggregate} AS {metric}")
            sql = (
                f"SELECT {', '.join(select_parts)} FROM commerce.web_traffic AS wt "
                "WHERE wt.date >= $1 AND wt.date < $2 "
            )
            if group_parts:
                sql += f"GROUP BY {', '.join(group_parts)} ORDER BY 1 "
            sql += f"LIMIT {MAX_RESULT_ROWS}"
            validated = validate_commerce_sql(sql)
            return Interpretation(plan=QueryPlan(
                sql=sql,
                parameters=(start, end),
                sources=validated.sources,
                metric=metric,
                metric_definition=str(definition["formula"]),
                time_grain=time_grain,
                output_shape="table" if by_source else "scalar",
                limitations=tuple(definition.get("limitations", ())),
            ))

        flexible_metrics = metrics & {
            "order_count", "average_order_value", "rating", "delivery_time",
        }
        if flexible_metrics:
            if len(flexible_metrics) > 1:
                return Interpretation(clarification="Vui lòng hỏi một chỉ số trong mỗi truy vấn.")
            if period is None:
                return Interpretation(clarification="Vui lòng nêu tháng hoặc năm cần phân tích.")
            return self._compile_flexible_metric(next(iter(flexible_metrics)), text, period)

        return Interpretation(unsupported_reason=(
            "Ý nghĩa này chưa có kế hoạch truy vấn an toàn trong phạm vi dữ liệu được phê duyệt."
        ))

    @staticmethod
    def _period(question: str) -> tuple[date, date, str] | None:
        month = re.search(r"(?<!\d)(20\d{2})[-/](0?[1-9]|1[0-2])(?!\d)", question)
        if not month:
            month = re.search(
                r"(?:tháng|month)\s+(0?[1-9]|1[0-2])\s*(?:/|năm|year)\s*(20\d{2})",
                question,
                re.I,
            )
            if month:
                year, month_number = int(month.group(2)), int(month.group(1))
            else:
                year_match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", question)
                if not year_match:
                    return None
                year = int(year_match.group(1))
                return date(year, 1, 1), date(year + 1, 1, 1), "year"
        else:
            year, month_number = int(month.group(1)), int(month.group(2))
        start = date(year, month_number, 1)
        end = date(year, month_number, calendar.monthrange(year, month_number)[1]) + timedelta(days=1)
        return start, end, "month"

    @staticmethod
    def _compile_flexible_metric(
        metric: str,
        question: str,
        period: tuple[date, date, str],
    ) -> Interpretation:
        start, end, period_grain = period
        definition = get_metric_definition(metric)
        text = question.casefold()
        by_month = bool(re.search(r"theo tháng|từng tháng|mỗi tháng|monthly|by month", text))
        dimensions: list[tuple[str, str]] = []
        joins: list[str] = []
        extra_filters: list[str] = []

        if metric == "order_count":
            source_sql = "commerce.orders AS o"
            date_column = "o.order_date"
            aggregate = "COUNT(DISTINCT o.order_id)"
            if re.search(r"trạng thái|status", text):
                dimensions.append(("o.order_status", "order_status"))
            elif re.search(r"thiết bị|device", text):
                dimensions.append(("o.device_type", "device_type"))
            elif re.search(r"nguồn đơn|order source", text):
                dimensions.append(("o.order_source", "order_source"))
            elif re.search(r"khu vực|vùng|region", text):
                joins.append("JOIN commerce.geography AS g ON g.zip = o.zip")
                dimensions.append(("g.region", "region"))
        elif metric == "average_order_value":
            source_sql = "commerce.orders AS o"
            joins.append("JOIN commerce.order_items AS oi ON oi.order_id = o.order_id")
            date_column = "o.order_date"
            aggregate = (
                "SUM(oi.quantity * oi.unit_price - oi.discount_amount) "
                "/ NULLIF(COUNT(DISTINCT o.order_id), 0)"
            )
            if re.search(r"khu vực|vùng|region", text):
                joins.append("JOIN commerce.geography AS g ON g.zip = o.zip")
                dimensions.append(("g.region", "region"))
        elif metric == "rating":
            source_sql = "commerce.reviews AS r"
            date_column = "r.review_date"
            aggregate = "AVG(r.rating)"
            if re.search(r"danh mục|category", text):
                joins.append("JOIN commerce.products AS p ON p.product_id = r.product_id")
                dimensions.append(("p.category", "category"))
            elif re.search(r"sản phẩm|product", text):
                joins.append("JOIN commerce.products AS p ON p.product_id = r.product_id")
                dimensions.append(("p.product_name", "product_name"))
        else:
            source_sql = "commerce.shipments AS s"
            date_column = "s.ship_date"
            aggregate = "AVG(s.delivery_date - s.ship_date)"
            extra_filters.extend(("s.ship_date IS NOT NULL", "s.delivery_date IS NOT NULL"))
            if re.search(r"khu vực|vùng|region", text):
                joins.extend((
                    "JOIN commerce.orders AS o ON o.order_id = s.order_id",
                    "JOIN commerce.geography AS g ON g.zip = o.zip",
                ))
                dimensions.append(("g.region", "region"))

        if by_month:
            dimensions.insert(0, (f"DATE_TRUNC('month', {date_column})", "period"))

        select_parts = [f"{expression} AS {alias}" for expression, alias in dimensions]
        select_parts.append(f"{aggregate} AS {metric}")
        filters = [f"{date_column} >= $1", f"{date_column} < $2", *extra_filters]
        sql = (
            f"SELECT {', '.join(select_parts)} FROM {source_sql} "
            f"{' '.join(joins)} WHERE {' AND '.join(filters)} "
        )
        if dimensions:
            sql += "GROUP BY " + ", ".join(expression for expression, _ in dimensions) + " ORDER BY 1 "
        sql += f"LIMIT {MAX_RESULT_ROWS}"
        validated = validate_commerce_sql(sql)
        return Interpretation(plan=QueryPlan(
            sql=sql,
            parameters=(start, end),
            sources=validated.sources,
            metric=metric,
            metric_definition=str(definition["formula"]),
            time_grain="month" if by_month else period_grain,
            output_shape="table" if dimensions else "scalar",
            limitations=tuple(definition.get("limitations", ())),
        ))
