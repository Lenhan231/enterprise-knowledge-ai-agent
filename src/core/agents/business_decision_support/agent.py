"""Run a source-grounded business consultation using the report evidence workflow."""

from core.agents.base import BaseAgent
from core.models.agents import AgentRequest, AgentResult


class BusinessDecisionSupportAgent(BaseAgent):
    """Generate a business consultation from authorized SQL and knowledge sources."""

    def __init__(self, report_agent):
        self.report_agent = report_agent

    async def run(self, request: AgentRequest) -> AgentResult:
        result, payload, _media_type = await self.report_agent.generate_from_template(
            request,
            source_mode="combined",
            output_format="markdown",
        )
        if payload:
            result = result.model_copy(update={"answer": payload.decode("utf-8")})
        return result.model_copy(update={
            "agent": "business_decision_support",
            "metadata": {
                **result.metadata,
                "selected_route": "business_decision_support",
            },
        })

    async def close(self) -> None:
        # The report agent is owned and closed by the application router.
        return None
