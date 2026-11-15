import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.business_decision_support import BusinessDecisionSupportAgent
from core.agents.orchestration.router import AgentRouter
from core.models.agents import AgentRequest, AgentResult


class ReportWorkflow:
    def __init__(self):
        self.calls = []

    async def generate_from_template(self, request, **options):
        self.calls.append((request, options))
        result = AgentResult(answer="Report ready.", agent="report", metadata={"status": "complete"})
        return result, b"# Recommendation\n\nKeep the evidence gap visible.", "text/markdown"


class BusinessDecisionSupportAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_business_agent_uses_combined_report_evidence_flow(self):
        report = ReportWorkflow()
        request = AgentRequest(question="Should we change the current plan?")

        result = await BusinessDecisionSupportAgent(report).run(request)

        self.assertEqual(report.calls, [(request, {"source_mode": "combined", "output_format": "markdown"})])
        self.assertEqual(result.agent, "business_decision_support")
        self.assertEqual(result.metadata["selected_route"], "business_decision_support")
        self.assertIn("Keep the evidence gap visible", result.answer)

    async def test_router_exposes_new_mode_and_keeps_old_mode_alias(self):
        report = ReportWorkflow()
        router = AgentRouter(None, None, None, report_agent=report)
        request = AgentRequest(question="Should we change the current plan?")

        for mode in ("business_decision_support", "decision_support"):
            result = await router.run_mode(request, mode)
            self.assertEqual(result.agent, "business_decision_support")
            self.assertEqual(result.metadata["selected_route"], "business_decision_support")

        self.assertEqual(len(report.calls), 2)

    def test_orchestration_rename_keeps_legacy_imports_working(self):
        from core.agents.decision_support.router import AgentRouter as LegacyRouter

        self.assertIs(LegacyRouter, AgentRouter)


if __name__ == "__main__":
    unittest.main()
