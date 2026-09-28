"""Return persisted, role-filtered corpus and verified metric data to the UI."""

from decimal import Decimal, InvalidOperation
from math import isfinite

from core.analytics.metric_ontology import resolve_metric_names
from core.agents.base import BaseAgent
from core.database.document_repository import DocumentRepository
from core.models.agents import AgentRequest, AgentResult


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

    def run(self, request: AgentRequest) -> AgentResult:
        role = request.metadata.get("role")
        if not role:
            raise ValueError("Dashboard requires a trusted authenticated role")
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
