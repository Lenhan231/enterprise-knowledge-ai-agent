"""Generate bounded, read-only analytics SQL over role-filtered CTEs."""

import json
import re

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError, TokenError

from core.analytics.commerce_decision_support import (
    COMMERCE_DECISION_PROFILES,
    COMMERCE_QUERY_TABLES,
    unavailable_commerce_dimensions,
)
from core.agents.base import BaseAgent
from core.analytics.sql_safety import UnsafeAnalyticsQuery, validate_analytics_sql, validate_commerce_sql
from core.database.document_repository import DocumentRepository
from core.llm.groq_provider import GroqProvider
from core.llm.provider_fallback import accumulate_token_usage, generate_with_provider_fallback
from core.models.agents import AgentRequest, AgentResult, Evidence


class UnsupportedCommerceDimension(ValueError):
    """Raised when a requested reporting dimension is absent from the domain schema."""

    def __init__(self, dimensions: list[str], available_columns: set[str]):
        self.dimensions = dimensions
        self.available_columns = available_columns
        super().__init__(
            "Requested reporting dimension is not available in this Commerce domain: "
            + ", ".join(dimensions)
        )


def _sql_from_model(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:sql)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            text = payload.get("sql", "")
    except json.JSONDecodeError:
        pass
    if not isinstance(text, str) or not text.strip():
        raise UnsafeAnalyticsQuery("The model did not return an analytics SELECT")
    return validate_analytics_sql(text)


def _scope_inventory_query_to_latest_snapshot(sql: str, snapshot_date: str | None) -> str:
    """Use the database's latest inventory date so model-chosen dates cannot skew current-state answers."""
    if not snapshot_date:
        raise UnsafeAnalyticsQuery("No inventory snapshot date is available")

    query = parse_one(sql, read="postgres")
    inventory = next((table for table in query.find_all(exp.Table) if table.name.casefold() == "inventory"), None)
    if inventory is None:
        raise UnsafeAnalyticsQuery("Current inventory questions must read commerce.inventory")
    predicate = exp.EQ(
        this=exp.column("snapshot_date", table=inventory.alias_or_name),
        expression=exp.Literal.string(snapshot_date),
    )
    existing = query.args.get("where")
    query.set("where", exp.Where(this=exp.and_(existing.this, predicate)) if existing else exp.Where(this=predicate))
    return query.sql(dialect="postgres")


def _inventory_question_needs_latest_snapshot(question: str) -> bool:
    text = question.casefold()
    if re.search(r"\b(?:19|20)\d{2}\b", text):
        return False
    historical = (
        r"\b(trend|historical|over time|year.over.year|by year|by month|across years|all years|all.time|"
        r"repeated(?:ly)?|recurring|persistent|across snapshots|multiple snapshots)\b"
        r"|qua các năm|theo năm|theo tháng|thay đổi theo thời gian|xu hướng|toàn bộ dữ liệu|tất cả các năm"
        r"|lặp lại|tái diễn|nhiều snapshot|nhiều kỳ|liên tiếp"
    )
    return not re.search(historical, text)


def _asks_repeated_inventory_flags(question: str) -> bool:
    return bool(re.search(
        r"\b(repeated(?:ly)?|recurring|persistent|across snapshots|multiple snapshots)\b"
        r"|lặp lại|tái diễn|nhiều snapshot|nhiều kỳ|liên tiếp",
        question,
        re.IGNORECASE,
    ))


def _validate_repeated_inventory_flags(question: str, sql: str) -> str:
    """Require repeated inventory flags to be counted across snapshots per product."""
    text = question.casefold()
    if not _asks_repeated_inventory_flags(text):
        return sql
    requested_flags = []
    if re.search(r"\b(stock.?out|out of stock)\b|hết hàng|thiếu hàng", text):
        requested_flags.append("stockout_flag")
    if re.search(r"\b(over.?stock|excess stock)\b|tồn kho dư|tồn kho quá mức", text):
        requested_flags.append("overstock_flag")
    if not requested_flags:
        return sql

    query = parse_one(sql, read="postgres")
    if any(
        {column.name.casefold() for column in predicate.find_all(exp.Column)} == {"snapshot_date"}
        and any(isinstance(value, exp.Literal) for value in predicate.find_all(exp.Literal))
        for predicate in query.find_all(exp.EQ)
    ):
        raise UnsafeAnalyticsQuery(
            "Repeated inventory flags cannot be restricted to one snapshot_date; count historical snapshots"
        )
    grouped_columns = {
        column.name.casefold()
        for expression in (query.args.get("group").expressions if query.args.get("group") else ())
        for column in expression.find_all(exp.Column)
    }

    def is_flagged_snapshot_count(expression: exp.Expression, flag: str) -> bool:
        if isinstance(expression, exp.Alias):
            expression = expression.this
        filter_node = expression if isinstance(expression, exp.Filter) else expression.find_ancestor(exp.Filter)
        count = filter_node.this if filter_node else expression
        return (
            isinstance(count, exp.Count)
            and isinstance(count.args.get("this"), exp.Distinct)
            and {column.name.casefold() for column in count.find_all(exp.Column)} == {"snapshot_date"}
            and filter_node is not None
            and {column.name.casefold() for column in filter_node.expression.find_all(exp.Column)} == {flag}
        )

    for flag in requested_flags:
        if "product_id" not in grouped_columns:
            raise UnsafeAnalyticsQuery(
                f"Repeated {flag.removesuffix('_flag')} evidence must group by product_id and count "
                f"COUNT(DISTINCT snapshot_date) FILTER (WHERE {flag})"
            )
        counts = [selection for selection in query.expressions if is_flagged_snapshot_count(selection, flag)]
        if not counts:
            raise UnsafeAnalyticsQuery(
                f"Repeated {flag.removesuffix('_flag')} evidence must count distinct snapshot_date "
                f"per product with COUNT(DISTINCT snapshot_date) FILTER (WHERE {flag})"
            )
        having = query.args.get("having")
        has_repeat_gate = bool(having) and any(
            isinstance(condition, exp.GTE)
            and is_flagged_snapshot_count(condition.this, flag)
            and isinstance(condition.expression, exp.Literal)
            and condition.expression.is_int
            and int(condition.expression.this) == 2
            for condition in having.find_all(exp.GTE)
        )
        if not has_repeat_gate:
            raise UnsafeAnalyticsQuery(
                f"Repeated {flag.removesuffix('_flag')} products must be filtered with "
                f"HAVING COUNT(DISTINCT snapshot_date) FILTER (WHERE {flag}) >= 2"
            )
    return sql


def _commerce_sql_from_model(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|sql)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            text = payload.get("sql", "")
    except json.JSONDecodeError:
        pass
    if not isinstance(text, str) or not text.strip():
        raise UnsafeAnalyticsQuery("The model did not return a Commerce SELECT")
    return text


def _validate_comparison_groups(question: str, sql: str) -> str:
    """Keep all peer groups in ranking queries instead of filtering competitors away."""
    group = re.search(
        r"\b(?:categor(?:y|ies)|groups?|regions?|segments?|campaigns?|locations?|warehouses?|carriers?)\b|"
        r"(?:danh mục|nhóm|vùng|khu vực|chiến dịch|địa điểm|kho|nhà vận chuyển)",
        question,
        re.IGNORECASE,
    )
    ranking = re.search(
        r"\b(?:which|rank(?:ing)?|highest|lowest|most|least|largest|smallest|top|prioriti[sz]e|best|worst)\b|"
        r"(?:nào|cao nhất|thấp nhất|nhiều nhất|ít nhất|lớn nhất|nhỏ nhất|ưu tiên|tốt nhất|kém nhất)",
        question,
        re.IGNORECASE,
    )
    if group and ranking and re.search(r"\bHAVING\b", sql, re.IGNORECASE):
        raise UnsafeAnalyticsQuery(
            "A comparative ranking must retain every peer group; do not filter groups with HAVING"
        )
    return sql


def _validate_requested_year_filter(question: str, sql: str) -> str:
    """Require explicit question years to constrain the SQL time period."""
    years = sorted({int(year) for year in re.findall(r"\b((?:19|20)\d{2})\b", question)})
    if not years:
        return sql
    query = parse_one(sql, read="postgres")
    where = query.args.get("where")
    temporal_columns = {
        "year", "fiscal_year", "snapshot_date", "order_date", "delivery_date",
        "ship_date", "start_date", "end_date",
    }
    if where is None:
        raise UnsafeAnalyticsQuery(
            f"The question requests year(s) {years}; filter a time column in WHERE"
        )
    predicate = where.this
    where_sql = predicate.sql(dialect="postgres")
    where_years = {int(year) for year in re.findall(r"\b((?:19|20)\d{2})\b", where_sql)}
    has_temporal_column = any(
        column.name.casefold() in temporal_columns for column in predicate.find_all(exp.Column)
    )
    if any(
        any(column.name.casefold() in temporal_columns for column in clause.find_all(exp.Column))
        for clause in predicate.find_all(exp.Or)
    ):
        raise UnsafeAnalyticsQuery(
            "The requested year filter is mixed with OR; constrain the selected period without broadening it"
        )
    if not has_temporal_column:
        raise UnsafeAnalyticsQuery(
            f"The question requests year(s) {years}; filter a time column in WHERE"
        )

    range_match = re.search(
        r"\b((?:19|20)\d{2})\s*(?:[-–—]|\bto\b|\bthrough\b|\bđến\b)\s*((?:19|20)\d{2})\b",
        question,
        re.IGNORECASE,
    )
    if range_match:
        start_year, end_year = map(int, range_match.groups())
        expected_years = set(range(start_year, end_year + 1))
        between_covers_range = any(
            (
                isinstance(between.this, exp.Column)
                and between.this.name.casefold() in temporal_columns
                or any(column.name.casefold() in temporal_columns
                       for column in between.this.find_all(exp.Column))
            )
            and {int(year) for year in re.findall(
                r"\b((?:19|20)\d{2})\b", between.sql(dialect="postgres"),
            )}.issuperset({start_year, end_year})
            for between in predicate.find_all(exp.Between)
        )
        if not between_covers_range and not expected_years.issubset(where_years):
            raise UnsafeAnalyticsQuery(
                f"The question requests the full year range {start_year}-{end_year}; filter that complete range in WHERE"
            )
    elif where_years != set(years):
        raise UnsafeAnalyticsQuery(
            f"The question requests year(s) {years}; WHERE must filter exactly those year(s)"
        )
    return sql


def _asks_for_promotion_tag_comparison(question: str) -> bool:
    text = question.casefold()
    positive = re.search(
        r"\btagged\b|\bwith\s+(?:a\s+)?(?:promo(?:tion)?(?:\s+tags?)?|tags?)|có\s+(?:gắn|tag|khuyến mãi)",
        text,
    )
    negative = re.search(
        r"\buntagged\b|\bwithout\s+(?:a\s+)?(?:promo(?:tion)?(?:\s+tags?)?|tags?)|"
        r"\bno\s+(?:promo(?:tion)?(?:\s+tags?)?|tags?)|không\s+(?:gắn|có)\s*(?:tag|khuyến mãi)?",
        text,
    )
    return bool(positive and negative)


def _validate_promotion_tag_groups(question: str, observations: list[dict]) -> None:
    """Reject a with/without promotion comparison when SQL returned only one group."""
    if not _asks_for_promotion_tag_comparison(question):
        return
    groups = {
        row.get("used_promotion")
        for row in observations
        if isinstance(row, dict) and isinstance(row.get("used_promotion"), bool)
    }
    if groups != {True, False}:
        raise UnsafeAnalyticsQuery(
            "A with/without promotion comparison must return both values of used_promotion"
        )


def _asks_for_campaign_scoped_outcomes(question: str) -> bool:
    """Only require campaign-window attribution when the question requests campaign-level results."""
    text = question.casefold()
    outcome = re.search(
        r"\b(?:sales|revenue|orders?|units?|discounts?|performance|outcomes?|results?)\b|"
        r"(?:doanh thu|đơn hàng|sản phẩm|giảm giá|hiệu quả|kết quả)",
        text,
    )
    scope = re.search(
        r"\bwhich\s+(?:\d{4}\s+)?campaigns?\b|"
        r"\b(?:compare|rank|ranking)\b[^.!?\n]{0,80}\bcampaigns?\b|"
        r"\b(?:each|per|by|during|within)\s+(?:the\s+)?campaigns?\b|"
        r"\bcampaign[- ]window\b|"
        r"(?:campaign nào|chiến dịch nào|từng chiến dịch|theo chiến dịch|trong thời gian chạy chiến dịch|kết quả từng chiến dịch)",
        text,
    )
    return bool(outcome and scope)


def _validate_campaign_outcome_query(question: str, sql: str) -> str:
    """Reject campaign outcome SQL that does not apply the dataset's attribution rules."""
    if not _asks_for_campaign_scoped_outcomes(question):
        return sql

    statement = parse_one(sql, read="postgres")
    aliases = {
        table.name.casefold(): table.alias_or_name.casefold()
        for table in statement.find_all(exp.Table)
    }
    promotion_alias = aliases.get("promotions")
    item_alias = aliases.get("order_items")
    orders_alias = aliases.get("orders")
    missing = []
    if not item_alias or not promotion_alias or not orders_alias:
        missing.append("join promotions, tagged order items and orders")

    def equality_pairs_campaign_ids(or_expression: exp.Expression) -> bool:
        pairs = set()
        for equality in or_expression.find_all(exp.EQ):
            columns = [node for node in equality.find_all(exp.Column)]
            if len(columns) == 2:
                pairs.add(frozenset((
                    (columns[0].table.casefold(), columns[0].name.casefold()),
                    (columns[1].table.casefold(), columns[1].name.casefold()),
                )))
        return bool(
            item_alias and promotion_alias
            and frozenset(((item_alias, "promo_id"), (promotion_alias, "promo_id"))) in pairs
            and frozenset(((item_alias, "promo_id_2"), (promotion_alias, "promo_id"))) in pairs
        )

    item_joins = [
        join for join in statement.find_all(exp.Join)
        if isinstance(join.this, exp.Table) and join.this.name.casefold() == "order_items"
    ]
    if not any(
        equality_pairs_campaign_ids(or_expression)
        for join in item_joins
        for or_expression in join.find_all(exp.Or)
    ):
        missing.append("attribute a line tagged in either promo_id or promo_id_2")
    if not re.search(rf"\b{re.escape(orders_alias or 'orders')}\.order_status\s*=\s*'delivered'", sql, re.IGNORECASE):
        missing.append("filter to delivered orders")
    if not any(
        isinstance(condition, exp.Between)
        and isinstance(condition.this, exp.Column)
        and condition.this.name.casefold() == "order_date"
        and isinstance(condition.args.get("low"), exp.Column)
        and condition.args["low"].name.casefold() == "start_date"
        and isinstance(condition.args.get("high"), exp.Column)
        and condition.args["high"].name.casefold() == "end_date"
        for condition in statement.find_all(exp.Between)
    ):
        missing.append("restrict order_date to each campaign's start_date through end_date")

    order_joins = [
        join for join in statement.find_all(exp.Join)
        if isinstance(join.this, exp.Table) and join.this.name.casefold() == "orders"
    ]
    left_orders = any((join.args.get("side") or "").casefold() == "left" for join in order_joins)
    if left_orders:
        for aggregate in statement.find_all(exp.AggFunc):
            filter_clause = aggregate.parent if isinstance(aggregate.parent, exp.Filter) else None
            if (filter_clause is None
                    or not re.search(
                        rf"\b{re.escape(orders_alias or 'orders')}\.order_id\s+IS\s+NOT\s+NULL\b",
                        filter_clause.sql(), re.IGNORECASE,
                    )):
                missing.append("filter every LEFT JOIN aggregate to matched delivered orders")
                break

    years = sorted({int(value) for value in re.findall(r"\b(20\d{2})\b", question)})
    where_sql = statement.args["where"].sql() if statement.args.get("where") else ""
    if years and promotion_alias:
        start_date = re.escape(promotion_alias) + r"\.start_date"
        year_expr = rf"EXTRACT\s*\(\s*YEAR\s+FROM\s+{start_date}\s*\)"
        if len(years) == 1:
            first, last = years[0], years[0]
            year_filter = re.search(rf"{year_expr}\s*=\s*{first}\b", where_sql, re.IGNORECASE)
        else:
            first, last = years[0], years[-1]
            year_filter = re.search(
                rf"{year_expr}\s+BETWEEN\s+{first}\s+AND\s+{last}\b", where_sql, re.IGNORECASE,
            )
        date_range_filter = re.search(
            rf"{start_date}\s*>=\s*'{first}-01-01'.*{start_date}\s*<\s*'{last + 1}-01-01'",
            where_sql,
            re.IGNORECASE,
        )
        if not year_filter and not date_range_filter:
            missing.append(f"filter campaign start date to requested year range {first}-{last}")
    if missing:
        raise UnsafeAnalyticsQuery("Campaign outcome SQL must " + "; ".join(dict.fromkeys(missing)))
    return sql


class SQLAnalyticsAgent(BaseAgent):
    def __init__(self, repository: DocumentRepository | None = None, llm: GroqProvider | None = None):
        self.repository = repository or DocumentRepository()
        self.llm = llm or GroqProvider()

    def commerce_decision_snapshot(self, domain: str) -> dict:
        """Read the fixed, domain-scoped Commerce aggregates used in decision reports."""
        return self.repository.commerce_decision_snapshot(domain)

    def commerce_latest_inventory_flag_overlap(self) -> list[dict]:
        """Read the vetted dashboard aggregate for products carrying both inventory flags."""
        return self.repository.commerce_dashboard(("inventory_latest_flag_overlap",))["inventory_latest_flag_overlap"]

    def commerce_question_observations(self, question: str, domain: str) -> dict:
        """Generate a question-specific SELECT over the selected domain's approved schema."""
        tables = COMMERCE_QUERY_TABLES.get(domain)
        if tables is None:
            raise ValueError(f"Unsupported Commerce decision domain: {domain}")
        available_columns = {column for columns in tables.values() for column in columns}
        unavailable = unavailable_commerce_dimensions(question, domain, available_columns)
        if unavailable:
            raise UnsupportedCommerceDimension(unavailable, available_columns)
        schema = "\n".join(
            f"commerce.{table}({', '.join(columns)})"
            for table, columns in tables.items()
        )
        schema_note = (
            "\nTime-grain note: for annual transit-time or shipping-fee trends, group by the completed "
            "delivery year using EXTRACT(YEAR FROM s.delivery_date), unless the user explicitly asks for "
            "order-placement year or dispatch year. This matches the logistics dashboard's reporting period. "
            "Type note: commerce.shipments.ship_date and delivery_date are DATE columns; "
            "subtracting one from the other returns an integer number of days. For transit time, "
            "use AVG(s.delivery_date - s.ship_date); do not wrap that difference in EXTRACT(EPOCH ...)."
            if domain == "nationwide_logistics" else ""
        )
        if domain == "promotion_planning":
            schema_note += (
                "\nCampaign-window note: when comparing promotion campaign outcomes, attribute tagged line items "
                "through either order_items.promo_id or promo_id_2 (use one OR join condition so a line tagged "
                "with the same campaign in both slots is not double-counted). Use only delivered orders whose "
                "order_date falls between that campaign's start_date and end_date; apply a requested campaign "
                "year to the campaign dates as well as the order dates. In SQL, explicitly require "
                "orders.order_status = 'delivered', order_date BETWEEN promotions.start_date AND promotions.end_date, "
                "and EXTRACT(YEAR FROM promotions.start_date) = the requested year (use BETWEEN for a year range). "
                "Place the year predicate in WHERE, not in a JOIN ON clause. "
                "Use INNER JOINs for eligible order items "
                "and orders, or filter every order-derived aggregate to matched orders if a LEFT JOIN is needed. "
                "Calculate net item sales as quantity * unit_price - discount_amount. Preserve the requested "
                "campaign/channel/year dimensions in grouped results."
            )
            if any(term in question.casefold() for term in (
                "gross profit", "gross-profit", "profit proxy", "merchandise gross", "lãi gộp", "lợi nhuận gộp",
            )):
                schema_note += (
                    " For a requested merchandise gross-profit proxy, join commerce.products on "
                    "products.product_id = order_items.product_id and calculate "
                    "SUM(order_items.quantity * order_items.unit_price - order_items.discount_amount "
                    "- order_items.quantity * products.cogs) AS merchandise_gross_profit_proxy. "
                    "The products table owns cogs; promotions.cogs does not exist. Preserve this requested measure."
                )
            if _asks_for_promotion_tag_comparison(question):
                schema_note += (
                    " For a with/without promotion comparison, return both groups using "
                    "(order_items.promo_id IS NOT NULL OR order_items.promo_id_2 IS NOT NULL) "
                    "AS used_promotion, group by that expression, and include both TRUE and FALSE. "
                    "These are item-tag groups; a delivered order may appear in both if its items have mixed tags."
                )
        if domain == "inventory_allocation":
            schema_note += (
                "\nBoolean-column note: inventory.stockout_flag, overstock_flag and reorder_flag are BOOLEAN. "
                "Filter with boolean predicates and count with COUNT(*) FILTER (WHERE flag); do not compare "
                "these columns with integer 1/0 or sum them."
                " When a question asks whether an inventory flag is repeated, recurring, or persistent, "
                "inspect historical product-snapshot rows instead of only the latest snapshot. Count flagged "
                "snapshot dates per product, include only products with at least two flagged dates, and do not "
                "describe those rows as distinct incidents."
            )
        prompt = (
            "Translate the user's Commerce question into one PostgreSQL SELECT and return JSON only: "
            '{"sql":"SELECT ..."}. Use only the exact tables and columns listed below. '
            "Qualify every source column with its table name or alias. Use explicit, key-based JOINs only. "
            "Return aggregated or grouped observations, never individual customer or transaction records. "
            "Select an aggregate for every measure explicitly requested in the question, and group by every requested dimension and period. "
            "For a comparison between named groups (including with/without, tagged/untagged, or before/after groups), "
            "return a group label or boolean dimension and preserve every requested group; do not filter the result to only one side. "
            "For a requested count of records or snapshots, include COUNT(*) as its own measure instead of substituting a flag count. "
            "Do not reduce a multi-measure comparison to only one available measure; if a requested measure is not in the approved schema, omit it and let the answer state that it is unavailable. "
            "Hard SQL constraints: one SELECT only; no CTEs, nested queries, scalar subqueries, or window functions. "
            "Every selected non-aggregate expression must appear in GROUP BY; use only allowlisted SQL functions. "
            "Inventory questions that ask whether flags are repeated, recurring, or persistent require historical "
            "product-snapshot rows, grouped by product and filtered to at least two distinct flagged snapshot dates. "
            "Other inventory questions without an explicit year or historical-trend request "
            "are scoped by the server to the database's latest snapshot date. Group only by requested dimensions; "
            "do not guess dates or add time dimensions. "
            "For ranking or prioritization among categories, groups, regions, or other peer dimensions, include all "
            "peer groups with comparable measures and order them; do not use HAVING to remove competitors unless "
            "the user explicitly asks for a threshold-defined subset. "
            "List the grouped dimension expressions explicitly; do not use ordinal GROUP BY positions. "
            "For an explicit year or year range in the question, constrain the matching time column in WHERE "
            "to exactly that period; never return an unfiltered multi-year aggregate. Do not calculate causal lift, "
            "ROI, or an unsupported target. Use the period requested; if none is given, "
            "prefer the most recent period represented by the relevant table. Do not invent data. Include LIMIT 100.\n\n"
            f"Approved domain schema for {domain}:\n{schema}{schema_note}\n\nQuestion: {question}"
        )
        text = ""
        rejected_sql = ""
        token_usage = None

        def validated_query(raw: str) -> str:
            try:
                query = _validate_comparison_groups(question, _commerce_sql_from_model(raw))
                query = _validate_requested_year_filter(question, query)
                if domain == "inventory_allocation":
                    query = _validate_repeated_inventory_flags(question, query)
                reads_inventory = any(
                    table.name.casefold() == "inventory"
                    for table in parse_one(query, read="postgres").find_all(exp.Table)
                )
                if (domain == "inventory_allocation" and reads_inventory
                        and _inventory_question_needs_latest_snapshot(question)):
                    query = _scope_inventory_query_to_latest_snapshot(
                        query, self.repository.latest_commerce_inventory_snapshot(),
                    )
                safe_query = validate_commerce_sql(query, tables)
                if domain == "promotion_planning":
                    safe_query = _validate_campaign_outcome_query(question, safe_query)
                return safe_query
            except (ParseError, TokenError) as error:
                raise UnsafeAnalyticsQuery(
                    "The model response could not be parsed as one valid PostgreSQL SELECT"
                ) from error

        try:
            raw, generation_provider = generate_with_provider_fallback(self.llm, prompt)
            token_usage = accumulate_token_usage(token_usage, self.llm)
            rejected_sql = _commerce_sql_from_model(raw)
            text = validated_query(raw)
            observations = self.repository.execute_commerce_analytics(text, domain)
            if domain == "promotion_planning":
                _validate_promotion_tag_groups(question, observations)
        except UnsafeAnalyticsQuery as error:
            correction = (
                f"\n\nThe server rejected your previous SQL: {error}. Rewrite it as one safe SELECT that obeys "
                "every stated SQL constraint. Do not use a subquery, CTE, window, unqualified source column, "
                "raw transaction row, or unapproved field/function. For a latest snapshot, group by and return "
                "the snapshot date instead of calculating MAX in a subquery. Return corrected JSON only.\n"
                "If the question ranks or prioritizes peer groups, include all peer groups with comparable measures; "
                "do not filter competitors with HAVING unless the user explicitly requested a threshold-defined subset.\n"
                f"Rejected SQL: {rejected_sql}"
            )
            if domain == "promotion_planning" and _asks_for_campaign_scoped_outcomes(question):
                correction += (
                    " Preserve every requested metric and campaign dimension. For each campaign outcome query, "
                    "include orders.order_status = 'delivered', order_date BETWEEN promotions.start_date AND "
                    "promotions.end_date, and EXTRACT(YEAR FROM promotions.start_date) constrained to the requested "
                    "year(s) in WHERE, not in a JOIN ON clause. When a merchandise gross-profit proxy is requested, join commerce.products by product_id "
                    "and use SUM(quantity * unit_price - discount_amount - quantity * products.cogs); do not read cogs "
                    "from promotions or omit the proxy."
                )
            if domain == "inventory_allocation" and _asks_repeated_inventory_flags(question):
                correction += (
                    " For repeated inventory flags, query historical commerce.inventory rows grouped by i.product_id. "
                    "Select COUNT(DISTINCT i.snapshot_date) FILTER (WHERE i.stockout_flag) and/or "
                    "COUNT(DISTINCT i.snapshot_date) FILTER (WHERE i.overstock_flag), matching the flags asked about; "
                    "add HAVING for each requested count >= 2. Do not group only by category or restrict to one snapshot."
                )
            raw, generation_provider = generate_with_provider_fallback(self.llm, prompt + correction)
            token_usage = accumulate_token_usage(token_usage, self.llm)
            text = validated_query(raw)
            observations = self.repository.execute_commerce_analytics(text, domain)
            if domain == "promotion_planning":
                _validate_promotion_tag_groups(question, observations)
        used_tables = list(dict.fromkeys(re.findall(
            r"\b(?:from|join)\s+commerce\.([a-z_][a-z0-9_]*)\b", text, re.IGNORECASE,
        )))
        return {
            "domain": domain,
            "source_tables": [f"commerce.{name}" for name in used_tables],
            "sql_query": text,
            "sql_generation_provider": generation_provider,
            "sql_generation_usage": token_usage,
            "observations": observations,
            "limitations": list(COMMERCE_DECISION_PROFILES[domain]["limitations"]),
            "dataset_note": "Synthetic Kaggle Datathon 2026 Round 1 Commerce data; not observed results from a real retailer.",
        }

    def run(self, request: AgentRequest) -> AgentResult:
        role = request.metadata.get("role")
        if not role:
            raise ValueError("Analytics requires a trusted authenticated role")
        chart_instruction = (
            " For a requested dashboard visualization, return individual document observations without aggregation."
            if request.metadata.get("dashboard_visualization") else ""
        )
        prompt = (
            "Translate the analytics request into exactly one PostgreSQL SELECT. Return JSON only: "
            '{"sql":"..."}. You may read only authorized_documents (document_id, company, domain, title, '
            "document_type, format, fiscal_year, processing_status, source_url). They are already filtered "
            "for this user's role and company; do not add a company equality filter. "
            "Use only these columns. No joins, nested queries, CTEs, comments, semicolons, or functions other than "
            "COUNT, MIN, MAX, ARRAY_AGG. Return "
            "ARRAY_AGG(DISTINCT document_id) AS evidence_document_ids. Group by selected document metadata "
            "columns when aggregating; use a numeric LIMIT at most 100. Do not infer financial "
            "values from document metadata or invent data."
            + chart_instruction + f"\n\nRequest: {request.question}"
        )
        query = _sql_from_model(self.llm.generate(prompt))
        data = self.repository.execute_authorized_analytics(
            query, role, request.user_id or "", request.metadata.get("company")
        )
        evidence_key = "evidence_document_ids"
        evidence_rows = data["documents"]
        evidence = [
            Evidence(
                citation_id=f"D{index}",
                source_type="document",
                source=row["title"],
                metadata={"document_id": row["document_id"], "company": row["company"],
                          "domain": row["domain"], "source_url": row["source_url"]},
            )
            for index, row in enumerate(evidence_rows, 1)
        ]
        evidence_by_id = {
            item.metadata["document_id"]: item
            for item in evidence
        }
        result_rows = [
            row for row in data["results"]
            if isinstance(row.get(evidence_key), (list, tuple)) and row[evidence_key]
        ]
        lines = ["Analytics results (computed from role-visible document metadata):"]
        selected_ids = set()
        for row in result_rows:
            source_ids = row[evidence_key]
            matches = [evidence_by_id[source_id] for source_id in source_ids if source_id in evidence_by_id]
            if not matches:
                return AgentResult(
                    answer="Analytics results could not be matched to exact role-visible source evidence.",
                    agent="analytics", metadata={"insufficient_context": True},
                )
            selected_ids.update(item.citation_id for item in matches)
            values = [f"{key}: {value}" for key, value in row.items() if key != evidence_key]
            lines.append("- " + "; ".join(values) + " " + " ".join(f"[{item.citation_id}]" for item in matches))
        selected_evidence = [item for item in evidence if item.citation_id in selected_ids]
        answer = "\n".join(lines) if result_rows else "No verified, role-visible data matched this analytics request."
        return AgentResult(
            answer=answer,
            agent="analytics",
            evidence=selected_evidence,
            data={"results": result_rows, "documents": data["documents"], "query_sql": query},
        )

    def close(self) -> None:
        self.repository.close()
        if hasattr(self.llm, "close"):
            self.llm.close()
