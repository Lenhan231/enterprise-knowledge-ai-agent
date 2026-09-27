"""Return persisted, role-filtered corpus and verified metric data to the UI."""

from core.agents.base import BaseAgent
from core.database.document_repository import DocumentRepository
from core.models.agents import AgentRequest, AgentResult


class DashboardAgent(BaseAgent):
    def __init__(self, repository: DocumentRepository | None = None):
        self.repository = repository or DocumentRepository()

    def run(self, request: AgentRequest) -> AgentResult:
        role = request.metadata.get("role")
        if not role:
            raise ValueError("Dashboard requires a trusted authenticated role")
        data = self.repository.corpus_dashboard(
            role, request.user_id or "", include_analytics=True,
            company=request.metadata.get("company"),
        )
        return AgentResult(answer="Live database dashboard data is ready.", agent="dashboard", data=data)

    def close(self) -> None:
        self.repository.close()
