"""Generate bounded, read-only analytics SQL over role-filtered CTEs."""

import json
import re

from core.analytics.business_metric_catalog import (
    BUSINESS_DECISION_PROFILES,
    BUSINESS_METRIC_CATALOG,
    resolve_business_metric_names,
)
from core.agents.base import BaseAgent
from core.analytics.sql_safety import UnsafeAnalyticsQuery, validate_analytics_sql
from core.database.document_repository import DocumentRepository
from core.llm.groq_provider import GroqProvider
from core.models.agents import AgentRequest, AgentResult, Evidence

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


class SQLAnalyticsAgent(BaseAgent):
    def __init__(self, repository: DocumentRepository | None = None, llm: GroqProvider | None = None):
        self.repository = repository or DocumentRepository()
        self.llm = llm or GroqProvider()

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
            query_business_metrics.update(scoped_business_names if decision_profile and not query_business_metrics else ())
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
