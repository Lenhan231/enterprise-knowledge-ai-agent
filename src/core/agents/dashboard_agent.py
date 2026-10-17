"""Return persisted, role-filtered corpus and verified metric data to the UI."""

from math import isfinite
import re

from core.analytics.commerce_decision_support import COMMERCE_DECISION_PROFILES, resolve_commerce_decision_domain
from core.agents.base import BaseAgent
from core.database.document_repository import DocumentRepository
from core.models.agents import AgentRequest, AgentResult, Evidence


class DashboardAgent(BaseAgent):
    def __init__(self, repository: DocumentRepository | None = None):
        self.repository = repository or DocumentRepository()

    @staticmethod
    def _commerce_chart(question: str, domain: str, data: dict) -> tuple[dict | None, list[dict], list[int]]:
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

        source_rows = rows
        available_years = sorted({int(row["year"]) for row in source_rows if row.get("year") is not None})
        years = available_years
        requested_years = sorted({int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", question)})
        if requested_years:
            year_range = set(range(requested_years[0], requested_years[-1] + 1))
            rows = [row for row in rows if int(row["year"]) in year_range]
            years = [year for year in years if year in year_range]
            if not rows:
                rows = source_rows
        if len(years) < 2 or not series:
            return None, rows, available_years
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
            return None, rows, available_years
        return {"type": "line", "title": title, "unit": series[0]["unit"], "categories": years,
                "series": chart_series}, rows, available_years

    def run(self, request: AgentRequest) -> AgentResult:
        role = request.metadata.get("role")
        if not role:
            raise ValueError("Dashboard requires a trusted authenticated role")
        commerce_domain = request.metadata.get("business_decision_domain") or resolve_commerce_decision_domain(request.question)
        if commerce_domain in COMMERCE_DECISION_PROFILES:
            profile = COMMERCE_DECISION_PROFILES[commerce_domain]
            data = self.repository.commerce_dashboard(profile["dashboard_keys"])
            visualization, rows, available_years = self._commerce_chart(request.question, commerce_domain, data)
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
            requested_years = sorted({int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", request.question)})
            requested_range = set(range(requested_years[0], requested_years[-1] + 1)) if requested_years else set()
            matching_years = requested_range.intersection(available_years)
            if visualization:
                answer = f"Dashboard chart for {profile['label']} is grounded in the synthetic Commerce aggregates. [C1]"
                status = "ready"
            elif requested_range and not matching_years:
                available_label = ", ".join(map(str, available_years)) or "none"
                answer = (
                    f"No observations match the requested period FY{requested_years[0]}–FY{requested_years[-1]}. "
                    f"Available years for {profile['label']}: {available_label}. [C1]"
                )
                status = "no_matching_period"
            else:
                answer = f"There are not enough annual observations to chart {profile['label']} for that period. [C1]"
                status = "insufficient_series"
            return AgentResult(answer=answer, agent="dashboard", evidence=evidence, data={
                "visualization": visualization,
                "visualization_status": status,
                "domain": commerce_domain,
                "domain_label": profile["label"],
                "observations": {"rows": rows},
                "available_years": available_years,
            }, metadata={"business_decision_domain": commerce_domain})
        labels = ", ".join(profile["label"] for profile in COMMERCE_DECISION_PROFILES.values())
        return AgentResult(
            answer=f"Choose a Commerce dashboard domain: {labels}.",
            agent="dashboard",
            metadata={"needs_domain_clarification": True},
        )

    def close(self) -> None:
        self.repository.close()
