"""Generate bounded, read-only analytics SQL over role-filtered CTEs."""

import json
import re

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
        prompt = (
            "Translate the analytics request into exactly one PostgreSQL SELECT. Return JSON only: "
            '{"sql":"..."}. You may read only one source: authorized_financial_metrics '
            "(company, fiscal_year, metric_name, metric_label, metric_value, unit, document_id, "
            "page_number, source_url, source_quote) or authorized_documents (document_id, company, "
            "domain, title, document_type, format, fiscal_year (integer or NULL), processing_status, source_url). They are already "
            "filtered for this user's role and requested company. Do not add a company equality filter. "
            "Use only these columns. No joins, nested queries, CTEs, "
            "comments, semicolons, or functions other than COUNT, SUM, AVG, MIN, MAX, ARRAY_AGG. "
            "Do not pivot multiple metric names into one row with CASE expressions. "
            "For metric_name filters, use only canonical codes: net_revenue, total_consolidated_revenue, "
            "profit_after_tax, total_assets, cost_of_goods_sold, gross_profit, cash_and_equivalents, "
            "inventory, employees, state_budget_contribution. Map consolidated revenue to "
            "total_consolidated_revenue, net revenue to net_revenue, and after-tax profit to "
            "profit_after_tax; do not use display words such as 'Revenue' or 'Profit' as codes. "
            "For authorized_financial_metrics, select ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids. "
            "For authorized_documents, select ARRAY_AGG(DISTINCT document_id) AS evidence_document_ids. "
            "For queries over authorized_financial_metrics, also project metric_name and fiscal_year directly and never "
            "combine different metric names or years in one result row; group by them when aggregating. "
            "This keeps each result tied to the exact source KPI. Use a numeric LIMIT at most 100. "
            "Do not invent data." + chart_instruction + "\n\n"
            f"Request: {request.question}"
        )
        query = _sql_from_model(self.llm.generate(prompt))
        data = self.repository.execute_authorized_analytics(
            query, role, request.user_id or "", request.metadata.get("company")
        )
        is_metric_query = "from authorized_financial_metrics" in query.casefold()
        evidence_key = "evidence_metric_ids" if is_metric_query else "evidence_document_ids"
        rows = [
            row for row in data["results"]
            if isinstance(row.get(evidence_key), (list, tuple))
            and row[evidence_key]
        ]
        answer = "No verified, role-visible data matched this analytics request."
        metric_evidence = [Evidence(
            citation_id=f"M{index}", source_type="verified_metric",
            source=f"{row['company']} {row['fiscal_year']} · {row['metric_label']}",
            content=row.get("source_quote") or row.get("source_note"),
            metadata={"metric_id": row.get("metric_id"), "document_id": row.get("document_id"), "page_number": row.get("page_number"),
                      "source_url": row.get("source_url"), "metric_name": row["metric_name"],
                      "source_reference": row.get("source_reference"), "entry_method": row.get("entry_method", "extracted"),
                      "company": row["company"], "fiscal_year": row["fiscal_year"],
                      "metric_label": row["metric_label"], "metric_value": row["metric_value"],
                      "unit": row["unit"]},
        ) for index, row in enumerate(data["evidence"], 1)]
        document_evidence = [Evidence(
            citation_id=f"D{index}", source_type="document",
            source=row["title"], content=None,
            metadata={"document_id": row["document_id"], "company": row["company"],
                      "domain": row["domain"], "source_url": row["source_url"]},
        ) for index, row in enumerate(data["documents"], 1)]
        source_evidence = metric_evidence if is_metric_query else document_evidence
        financial_rows_by_citation = {
            f"M{index}": row for index, row in enumerate(data["evidence"], 1)
        }
        selected_evidence = {}
        if rows:
            lines = ["Analytics results (computed from role-visible verified data):"]
            for row in rows:
                values = [f"{key}: {value}" for key, value in row.items() if key != evidence_key]
                source_ids = set(row.get(evidence_key, []))
                matching_evidence = [
                    item for item in source_evidence
                    if item.metadata.get("metric_id" if is_metric_query else "document_id") in source_ids
                    and (not is_metric_query or all(
                        key not in row or str(row[key]) == str(item.metadata.get(key))
                        for key in ("metric_name", "fiscal_year", "company", "unit")
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
        selected_financial_rows = [
            financial_rows_by_citation[citation_id]
            for citation_id in selected_evidence
            if citation_id in financial_rows_by_citation
        ]
        return AgentResult(answer=answer, agent="analytics", evidence=evidence,
                           data={"results": rows, "financial": selected_financial_rows,
                                 "documents": data["documents"], "query_sql": query})

    def close(self) -> None:
        self.repository.close()
        if hasattr(self.llm, "close"):
            self.llm.close()
