"""Return persisted, role-filtered corpus and verified metric data to the UI."""

from decimal import Decimal, InvalidOperation
from math import isfinite
import re

from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.commerce_decision_support import COMMERCE_DECISION_PROFILES, resolve_commerce_decision_domain
from core.agents.base import BaseAgent
from core.database.document_repository import DocumentRepository
from core.models.agents import AgentRequest, AgentResult, Evidence


def _financial_time_series(rows: list[dict], title: str) -> dict | None:
    """Build a chart only from unambiguous, source-linked verified observations."""
    observations: dict[tuple[str, str], dict[int, float]] = {}
    units = set()
    for row in rows:
        if not row.get("metric_name") or not row.get("metric_label") or not row.get("unit"):
            return None
        try:
            year = int(row["fiscal_year"])
            value = Decimal(str(row["metric_value"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return None
        if not value.is_finite():
            return None
        key = (str(row["metric_name"]), str(row["metric_label"]))
        values = observations.setdefault(key, {})
        if year in values:
            return None
        chart_value = float(value)
        if not isfinite(chart_value):
            return None
        values[year] = chart_value
        units.add(str(row["unit"]))

    if len(units) != 1:
        return None
    categories = sorted({year for values in observations.values() for year in values})
    series = [
        {"name": label, "values": [values.get(year) for year in categories]}
        for (_, label), values in sorted(observations.items())
        if sum(year in values for year in categories) >= 2
    ]
    if len(categories) < 2 or not series:
        return None
    return {
        "type": "line",
        "title": title,
        "unit": next(iter(units)),
        "categories": categories,
        "series": series,
    }


class DashboardAgent(BaseAgent):
    def __init__(self, repository: DocumentRepository | None = None, analytics=None):
        self.repository = repository or DocumentRepository()
        self.analytics = analytics

    @staticmethod
    def _requests_financial_chart(question: str) -> bool:
        text = question.casefold()
        wants_visual = any(term in text for term in (
            "dashboard", "chart", "graph", "plot", "visualize", "visualise",
            "trend", "over time", "by year", "biểu đồ", "xu hướng", "theo năm", "qua các năm",
        ))
        return wants_visual and bool(resolve_metric_names(question))

    @staticmethod
    def _commerce_chart(question: str, domain: str, data: dict) -> tuple[dict | None, list[dict]]:
        observations = data
        if domain == "inventory_allocation":
            rows = observations.get("inventory_by_year", [])
            if any(term in question.casefold() for term in ("fill rate", "fill_rate", "tỷ lệ đáp ứng")):
                series = [{"name": "Average fill rate", "unit": "%", "value": lambda row: float(row["avg_fill_rate"]) * 100}]
                title = "Average fill rate by year"
            else:
                series = [
                    {"name": "Stockout snapshots", "unit": "snapshots", "value": lambda row: float(row["stockout_snapshots"])},
                    {"name": "Overstock snapshots", "unit": "snapshots", "value": lambda row: float(row["overstock_snapshots"])},
                ]
                title = "Inventory flags by year"
            key = "inventory_by_year"
        elif domain == "promotion_planning":
            rows = observations.get("promotions_by_year", [])
            proxy = any(term in question.casefold() for term in ("gross profit", "gross margin", "lợi nhuận gộp", "biên lợi nhuận"))
            metric = "merchandise_gross_profit_proxy" if proxy else "net_sales"
            unit = "dataset units · catalog COGS proxy" if proxy else "dataset units"
            series = [
                {"name": f"Promotion-tagged · {metric.replace('_', ' ')}", "unit": unit,
                 "value": lambda row: float(row[metric]) if row.get("used_promotion") else None},
                {"name": f"Untagged · {metric.replace('_', ' ')}", "unit": unit,
                 "value": lambda row: float(row[metric]) if not row.get("used_promotion") else None},
            ]
            key, title = "promotions_by_year", "Promotion-tagged and untagged outcomes by year"
        else:
            rows = observations.get("logistics_by_year_region", [])
            fee = any(term in question.casefold() for term in ("shipping fee", "shipping cost", "cước", "chi phí vận chuyển"))
            metric, unit = ("avg_shipping_fee", "dataset units; currency not declared") if fee else ("avg_transit_days", "days")
            regions = sorted({row.get("region") for row in rows if row.get("region")})
            series = [{"name": str(region), "unit": unit,
                       "value": lambda row, selected=region: float(row[metric]) if row.get("region") == selected else None}
                      for region in regions]
            key, title = "logistics_by_year_region", "Regional logistics by year"

        years = sorted({int(row["year"]) for row in rows if row.get("year") is not None})
        requested_years = sorted({int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", question)})
        if requested_years:
            year_range = set(range(requested_years[0], requested_years[-1] + 1))
            rows = [row for row in rows if int(row["year"]) in year_range]
            years = [year for year in years if year in year_range]
        if len(years) < 2 or not series:
            return None, rows
        chart_series = []
        for item in series:
            values_by_year = {}
            for row in rows:
                try:
                    value = item["value"](row)
                except (KeyError, TypeError, ValueError):
                    value = None
                if value is not None and isfinite(value):
                    values_by_year[int(row["year"])] = value
            if sum(year in values_by_year for year in years) >= 2:
                chart_series.append({"name": item["name"], "values": [values_by_year.get(year) for year in years]})
        if not chart_series:
            return None, rows
        return {"type": "line", "title": title, "unit": series[0]["unit"], "categories": years,
                "series": chart_series}, rows

    def run(self, request: AgentRequest) -> AgentResult:
        role = request.metadata.get("role")
        if not role:
            raise ValueError("Dashboard requires a trusted authenticated role")
        commerce_domain = request.metadata.get("business_decision_domain") or resolve_commerce_decision_domain(request.question)
        if commerce_domain in COMMERCE_DECISION_PROFILES:
            profile = COMMERCE_DECISION_PROFILES[commerce_domain]
            data = self.repository.commerce_dashboard(profile["dashboard_keys"])
            visualization, rows = self._commerce_chart(request.question, commerce_domain, data)
            evidence = [Evidence(
                citation_id="C1", source_type="commerce_sql",
                source=f"Commerce dashboard aggregate · {profile['label']}",
                content=f"Read-only aggregate rows from {', '.join(profile['source_tables'])}.",
                metadata={
                    "company": "Commerce Demo", "commerce_domain": commerce_domain,
                    "commerce_observation_group": profile["label"], "commerce_observations": rows,
                    "source_tables": list(profile["source_tables"]),
                    "dataset_note": (data.get("data_notes") or ["Synthetic Commerce data."])[0],
                },
            )]
            answer = (
                f"Dashboard chart for {profile['label']} is grounded in the synthetic Commerce aggregates. [C1]"
                if visualization else
                f"The selected Commerce domain does not contain enough annual observations for a chart. [C1]"
            )
            return AgentResult(answer=answer, agent="dashboard", evidence=evidence, data={
                "visualization": visualization,
                "visualization_status": "ready" if visualization else "insufficient_series",
                "domain": commerce_domain,
                "domain_label": profile["label"],
                "observations": {"rows": rows},
            }, metadata={"business_decision_domain": commerce_domain})
        if self.analytics and self._requests_financial_chart(request.question):
            analytics_request = request.model_copy(update={
                "metadata": {**request.metadata, "dashboard_visualization": True},
            })
            result = self.analytics.run(analytics_request)
            rows = result.data.get("financial", [])
            visualization = _financial_time_series(rows, request.question)
            return result.model_copy(update={
                "agent": "dashboard",
                "data": {
                    "results": rows,
                    "visualization": visualization,
                    "visualization_status": "ready" if visualization else "insufficient_verified_series",
                },
            })
        data = self.repository.corpus_dashboard(
            role, request.user_id or "", include_analytics=True,
            company=request.metadata.get("company"),
        )
        return AgentResult(answer="Live database dashboard data is ready.", agent="dashboard", data=data)

    def close(self) -> None:
        self.repository.close()
