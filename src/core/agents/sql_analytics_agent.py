"""Generate bounded, read-only analytics SQL over role-filtered CTEs."""

import json
import re

from sqlglot import exp, parse_one

from core.analytics.business_metric_catalog import (
    BUSINESS_DECISION_PROFILES,
    BUSINESS_METRIC_CATALOG,
    resolve_business_metric_names,
)
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
        r"\b(trend|historical|over time|year.over.year|by year|by month|across years|all years|all.time)\b"
        r"|qua các năm|theo năm|theo tháng|thay đổi theo thời gian|xu hướng|toàn bộ dữ liệu|tất cả các năm"
    )
    return not re.search(historical, text)


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


def _validate_campaign_outcome_query(question: str, sql: str) -> str:
    """Reject campaign outcome SQL that does not apply the dataset's attribution rules."""
    asks_campaign_outcome = (
        re.search(r"\bcampaigns?\b|chiến dịch", question, re.IGNORECASE)
        and re.search(
            r"\b(?:sales|revenue|orders?|units?|discounts?)\b|doanh thu|đơn hàng|sản phẩm|giảm giá",
            question,
            re.IGNORECASE,
        )
    )
    if not asks_campaign_outcome:
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
                "year to the campaign dates as well as the order dates. Use INNER JOINs for eligible order items "
                "and orders, or filter every order-derived aggregate to matched orders if a LEFT JOIN is needed. "
                "Calculate net item sales as quantity * unit_price - discount_amount. Preserve the requested "
                "campaign/channel/year dimensions in grouped results."
            )
        if domain == "inventory_allocation":
            schema_note += (
                "\nBoolean-column note: inventory.stockout_flag, overstock_flag and reorder_flag are BOOLEAN. "
                "Filter with boolean predicates and count with COUNT(*) FILTER (WHERE flag); do not compare "
                "these columns with integer 1/0 or sum them."
            )
        prompt = (
            "Translate the user's Commerce question into one PostgreSQL SELECT and return JSON only: "
            '{"sql":"SELECT ..."}. Use only the exact tables and columns listed below. '
            "Qualify every source column with its table name or alias. Use explicit, key-based JOINs only. "
            "Return aggregated or grouped observations, never individual customer or transaction records. "
            "Select an aggregate for every measure explicitly requested in the question, and group by every requested dimension and period. "
            "Do not reduce a multi-measure comparison to only one available measure; if a requested measure is not in the approved schema, omit it and let the answer state that it is unavailable. "
            "Hard SQL constraints: one SELECT only; no CTEs, nested queries, scalar subqueries, or window functions. "
            "Every selected non-aggregate expression must appear in GROUP BY; use only allowlisted SQL functions. "
            "Inventory questions without an explicit year or historical-trend request are scoped by the server "
            "to the database's latest snapshot date. Group only by the requested dimensions; do not guess dates "
            "or add time dimensions. "
            "For ranking or prioritization among categories, groups, regions, or other peer dimensions, include all "
            "peer groups with comparable measures and order them; do not use HAVING to remove competitors unless "
            "the user explicitly asks for a threshold-defined subset. "
            "List the grouped dimension expressions explicitly; do not use ordinal GROUP BY positions. "
            "Do not calculate causal lift, ROI, or an unsupported target. Use the period requested; if none is given, "
            "prefer the most recent period represented by the relevant table. Do not invent data. Include LIMIT 100.\n\n"
            f"Approved domain schema for {domain}:\n{schema}{schema_note}\n\nQuestion: {question}"
        )
        text = ""
        rejected_sql = ""
        token_usage = None

        def validated_query(raw: str) -> str:
            query = _validate_comparison_groups(question, _commerce_sql_from_model(raw))
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

        try:
            raw, generation_provider = generate_with_provider_fallback(self.llm, prompt)
            token_usage = accumulate_token_usage(token_usage, self.llm)
            rejected_sql = _commerce_sql_from_model(raw)
            text = validated_query(raw)
            observations = self.repository.execute_commerce_analytics(text, domain)
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
            raw, generation_provider = generate_with_provider_fallback(self.llm, prompt + correction)
            token_usage = accumulate_token_usage(token_usage, self.llm)
            text = validated_query(raw)
            observations = self.repository.execute_commerce_analytics(text, domain)
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
            " For a requested dashboard visualization, return individual observations only: project metric_name, "
            "metric_label, fiscal_year, metric_value, unit, and document_id directly, without summing or averaging values. "
            "Group by those exact fields and keep every fiscal year separate."
            if request.metadata.get("dashboard_visualization") else ""
        )
        decision_domain = request.metadata.get("business_decision_domain")
        decision_profile = BUSINESS_DECISION_PROFILES.get(decision_domain)
        scoped_business_names = {
            name for name, definition in BUSINESS_METRIC_CATALOG.items()
            if not decision_profile or definition["domain"] == decision_domain
        }
        business_catalog = "; ".join(
            f"{name} ({definition['label']}; domain={definition['domain']}; unit={definition['unit_guidance']}; "
            f"aliases={', '.join(definition.get('aliases', ()))})"
            for name, definition in BUSINESS_METRIC_CATALOG.items()
            if name in scoped_business_names
        )
        matched_business_metrics = sorted(
            resolve_business_metric_names(request.question) & scoped_business_names
        )
        query_business_metrics = set(matched_business_metrics)
        export_market_metrics = {
            "guinea_export_revenue_growth", "hong_kong_export_revenue_growth",
            "japan_export_revenue_growth",
        }
        if export_market_metrics.issubset(query_business_metrics):
            # Provide company-level scale alongside country growth for decision context.
            query_business_metrics.update({
                "export_net_revenue", "export_net_revenue_growth",
                "commercial_export_revenue", "commercial_export_revenue_growth",
                "export_volume_teu",
            })
        growth_pair = {
            "domestic_consolidated_net_revenue_growth",
            "overseas_market_net_revenue_growth",
        }
        growth_amounts = {
            "domestic_consolidated_net_revenue",
            "overseas_market_net_revenue",
        }
        if growth_pair.issubset(matched_business_metrics):
            # Decision comparisons need growth and scale, including prior-year revenue
            # so the report can calculate the absolute change from source observations.
            matched_business_metrics = sorted(set(matched_business_metrics) | growth_amounts)
            query_business_metrics.update(growth_amounts)
        mapped_metrics_instruction = (
            "Canonical business metric codes matching this question: "
            + ", ".join(sorted(query_business_metrics))
            + ". Include every listed metric_name in the result; do not omit a requested segment or measure. "
            if matched_business_metrics else ""
        )
        decision_scope_instruction = (
            f"The user selected decision domain {decision_domain} ({decision_profile['label']}). "
            f"Its management question is: {decision_profile['management_question']} "
            f"Only use verified business metrics from this domain; its primary decision metrics are "
            f"{', '.join(decision_profile['primary_metrics'])}. Other metrics in the same domain may be used "
            "only as supporting evidence when the question calls for them. Do not substitute another domain. "
            if decision_profile else ""
        )
        prompt = (
            "Translate the analytics request into exactly one PostgreSQL SELECT. Return JSON only: "
            '{"sql":"..."}. You may read only one source: authorized_financial_metrics '
            "(company, fiscal_year, metric_name, metric_label, metric_value, unit, document_id, "
            "page_number, source_url, source_quote) or authorized_documents (document_id, company, "
            "domain, title, document_type, format, fiscal_year (integer or NULL), processing_status, source_url). They are already "
            "filtered for this user's role and requested company. Do not add a company equality filter. "
            "authorized_business_metrics (business_metric_id, company, metric_domain, fiscal_year, metric_name, "
            "metric_label, metric_value, unit, value_qualifier, reporting_period, scope, document_id, "
            "page_number, source_url, source_quote). "
            "All are already filtered for this user's role and company; verified business rows only. "
            "Use only these columns. No joins, nested queries, CTEs, "
            "comments, semicolons, or functions other than COUNT, SUM, AVG, MIN, MAX, ARRAY_AGG. "
            "Do not pivot multiple metric names into one row with CASE expressions. "
            "For metric_name filters, use only canonical codes: net_revenue, total_consolidated_revenue, "
            "profit_after_tax, total_assets, cost_of_goods_sold, gross_profit, cash_and_equivalents, "
            "inventory, employees, state_budget_contribution. Map consolidated revenue to "
            "total_consolidated_revenue, net revenue to net_revenue, and after-tax profit to "
            "profit_after_tax; do not use display words such as 'Revenue' or 'Profit' as codes. "
            "For authorized_financial_metrics, select ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids. "
            "For authorized_business_metrics, select ARRAY_AGG(DISTINCT business_metric_id) AS evidence_business_metric_ids. "
            "For authorized_documents, select ARRAY_AGG(DISTINCT document_id) AS evidence_document_ids. "
            "For business metric queries, preserve value_qualifier and reporting_period in the result. "
            "Never treat values qualified as more_than, at_least, less_than, at_most, or approximately as exact. "
            f"{decision_scope_instruction}"
            f"Business metric catalog (filter metric_name using these codes): {business_catalog}. "
            f"{mapped_metrics_instruction}"
            "For either metric CTE, also project metric_name and fiscal_year directly and never "
            "combine different metric names or years in one result row; group by them when aggregating. "
            "This keeps each result tied to the exact source KPI. Use a numeric LIMIT at most 100. "
            "Do not invent data." + chart_instruction + "\n\n"
            f"Request: {request.question}"
        )
        if matched_business_metrics or decision_profile:
            # A selected decision scope always runs against its verified business
            # metrics, even when the question uses wording outside the alias map.
            # This prevents fallback SQL from crossing into an unrelated domain.
            if decision_profile and not query_business_metrics:
                if request.metadata.get("decision_suggestions"):
                    query_business_metrics.update(decision_profile["primary_metrics"])
                else:
                    query_business_metrics.update(scoped_business_names)
            metric_names = ", ".join(f"'{name}'" for name in sorted(query_business_metrics))
            years = sorted(set(re.findall(r"(?<!\d)(?:FY\s*)?((?:19|20)\d{2})\b", request.question, re.I)))
            if len(years) >= 2 and max(map(int, years)) - min(map(int, years)) >= 2:
                years = [str(year) for year in range(int(years[0]), int(years[-1]) + 1)]
            elif len(years) == 1 and growth_pair.issubset(matched_business_metrics):
                years = sorted(set(years) | {str(int(year) - 1) for year in years})
            year_filter = f" AND fiscal_year IN ({', '.join(years)})" if years else ""
            query = validate_analytics_sql(
                "SELECT metric_name, fiscal_year, reporting_period, metric_value, unit, value_qualifier, "
                "ARRAY_AGG(DISTINCT business_metric_id) AS evidence_business_metric_ids "
                "FROM authorized_business_metrics "
                f"WHERE metric_name IN ({metric_names}){year_filter} "
                "GROUP BY metric_name, fiscal_year, reporting_period, metric_value, unit, value_qualifier LIMIT 100"
            )
        else:
            query = _sql_from_model(self.llm.generate(prompt))
        data = self.repository.execute_authorized_analytics(
            query, role, request.user_id or "", request.metadata.get("company")
        )
        source_name = next((name for name in (
            "authorized_financial_metrics", "authorized_business_metrics", "authorized_documents"
        ) if f"from {name}" in query.casefold()), "authorized_documents")
        is_metric_query = source_name != "authorized_documents"
        is_business_query = source_name == "authorized_business_metrics"
        evidence_key = ("evidence_business_metric_ids" if is_business_query else
                        "evidence_metric_ids" if is_metric_query else "evidence_document_ids")
        evidence_rows = data.get("business_evidence", []) if is_business_query else data["evidence"]
        rows = [
            row for row in data["results"]
            if isinstance(row.get(evidence_key), (list, tuple))
            and row[evidence_key]
        ]
        answer = "No verified, role-visible data matched this analytics request."
        metric_evidence = [Evidence(
            citation_id=f"M{index}", source_type="verified_metric",
            source=(f"{row['company']} {row.get('reporting_period', 'FY')} {row['fiscal_year']} · "
                    f"{row['metric_label']}"),
            content=row.get("source_quote") or row.get("source_note"),
            metadata={"metric_id": row.get("metric_id"), "document_id": row.get("document_id"), "page_number": row.get("page_number"),
                      "chunk_index": row.get("source_chunk_index"),
                      "source_chunk_id": row.get("source_chunk_id"), "chunk_id": row.get("source_chunk_id"),
                      "source_content_hash": row.get("source_content_hash"),
                      "extraction_method": row.get("extraction_method"),
                      "extractor_version": row.get("extractor_version"),
                      "source_url": row.get("source_url"), "metric_name": row["metric_name"],
                      "metric_domain": row.get("metric_domain"), "scope": row.get("scope"),
                      "value_qualifier": row.get("value_qualifier", "exact"),
                      "reporting_period": row.get("reporting_period", "FY"),
                      "source_reference": row.get("source_reference"), "entry_method": row.get("entry_method", "extracted"),
                      "company": row["company"], "fiscal_year": row["fiscal_year"],
                      "business_metric_id": row.get("business_metric_id"),
                      "metric_domain": row.get("metric_domain"), "scope": row.get("scope"),
                      "metric_label": row["metric_label"], "metric_value": row["metric_value"],
                      "unit": row["unit"],
                      "value_qualifier": row.get("value_qualifier", "exact"),
                      "reporting_period": row.get("reporting_period", "FY")},
        ) for index, row in enumerate(evidence_rows, 1)]
        document_evidence = [Evidence(
            citation_id=f"D{index}", source_type="document",
            source=row["title"], content=None,
            metadata={"document_id": row["document_id"], "company": row["company"],
                      "domain": row["domain"], "source_url": row["source_url"]},
        ) for index, row in enumerate(data["documents"], 1)]
        source_evidence = metric_evidence if is_metric_query else document_evidence
        financial_rows_by_citation = {
            f"M{index}": row for index, row in enumerate(evidence_rows, 1)
        }
        selected_evidence = {}
        if rows:
            lines = ["Analytics results (computed from role-visible verified data):"]
            for row in rows:
                values = [f"{key}: {value}" for key, value in row.items() if key != evidence_key]
                source_ids = set(row.get(evidence_key, []))
                matching_evidence = [
                    item for item in source_evidence
                    if item.metadata.get("business_metric_id" if is_business_query else
                                         "metric_id" if is_metric_query else "document_id") in source_ids
                    and (not is_metric_query or all(
                        key not in row or str(row[key]) == str(item.metadata.get(key))
                        for key in ("metric_name", "fiscal_year", "company", "unit", "metric_domain",
                                    "value_qualifier", "reporting_period")
                    ))
                ]
                if not matching_evidence:
                    return AgentResult(
                        answer="Analytics results could not be matched to exact role-visible source evidence.",
                        agent="analytics",
                        metadata={"insufficient_context": True},
                    )
                selected_evidence.update((item.citation_id, item) for item in matching_evidence)
                citations = [item.citation_id for item in matching_evidence]
                citation_text = " ".join(f"[{citation}]" for citation in citations)
                lines.append("- " + "; ".join(values) + (f" {citation_text}" if citation_text else ""))
            answer = "\n".join(lines)
        evidence = list(selected_evidence.values())
        selected_metric_rows = [
            financial_rows_by_citation[citation_id]
            for citation_id in selected_evidence
            if citation_id in financial_rows_by_citation
        ]
        selected_financial_rows = selected_metric_rows if not is_business_query else []
        selected_business_rows = selected_metric_rows if is_business_query else []
        if is_business_query:
            evidence_by_id = {row["business_metric_id"]: row for row in evidence_rows}
            for result_row in selected_business_rows:
                source_ids = result_row.get(evidence_key, [])
                match = next((evidence_by_id[source_id] for source_id in source_ids
                              if source_id in evidence_by_id), None)
                if match is not None:
                    result_row["business_metric_id"] = match["business_metric_id"]
        return AgentResult(answer=answer, agent="analytics", evidence=evidence,
                           data={"results": rows, "financial": selected_financial_rows,
                                 "business_metrics": selected_business_rows,
                                 "documents": data["documents"], "query_sql": query})

    def close(self) -> None:
        self.repository.close()
        if hasattr(self.llm, "close"):
            self.llm.close()
