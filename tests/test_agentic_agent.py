import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.router import AgentRouter
from core.models.agents import AgentRequest, AgentResult, Evidence


class LangGraphRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_agentic_mode_calls_both_agents_once_and_merges_evidence(self):
        llm = AsyncMock()
        llm.generate.side_effect = ['{"knowledge":true,"sql":true}', "Combined answer from both sources."]
        knowledge = AsyncMock()
        knowledge.run.return_value = AgentResult(
            answer="Policy answer.", agent="knowledge",
            evidence=[Evidence(citation_id="S1", source_type="document", source="policy.pdf")],
        )
        analytics = AsyncMock()
        analytics.run.return_value = AgentResult(
            answer="SQL answer.", agent="analytics",
            evidence=[Evidence(citation_id="S1", source_type="database", source="commerce.sales")],
            data={"rows": [{"revenue": 100}]},
        )
        agent = AgentRouter(None, knowledge, analytics, llm=llm)

        result = await agent.run_mode(AgentRequest(question="What does policy say about revenue?"), "agentic")

        knowledge.run.assert_awaited_once()
        analytics.run.assert_awaited_once()
        self.assertEqual(result.agent, "agentic")
        self.assertTrue(result.answer.startswith("Combined answer from both sources."))
        self.assertIn("[S1] policy.pdf", result.answer)
        self.assertIn("[S2] commerce.sales", result.answer)
        self.assertIn("[S2] commerce.sales", llm.generate.await_args_list[1].args[0])
        self.assertEqual([e.source for e in result.evidence], ["policy.pdf", "commerce.sales"])
        self.assertEqual([e.citation_id for e in result.evidence], ["S1", "S2"])

    async def test_agentic_mode_calls_only_selected_agent(self):
        llm = AsyncMock()
        llm.generate.return_value = '{"knowledge":false,"sql":true}'
        knowledge, analytics = AsyncMock(), AsyncMock()
        analytics.run.return_value = AgentResult(answer="Rows", agent="analytics")
        agent = AgentRouter(None, knowledge, analytics, llm=llm)

        result = await agent.run_mode(AgentRequest(question="How many orders?"), "agentic")

        knowledge.run.assert_not_awaited()
        analytics.run.assert_awaited_once()
        self.assertEqual(result.answer, "Rows")
        llm.generate.assert_awaited_once()

    async def test_invalid_agentic_plan_returns_clear_failure_without_calling_tools(self):
        llm = AsyncMock()
        llm.generate.return_value = "not json"
        knowledge, analytics = AsyncMock(), AsyncMock()
        agent = AgentRouter(None, knowledge, analytics, llm=llm)

        result = await agent.run_mode(AgentRequest(question="Combine something"), "agentic")

        knowledge.run.assert_not_awaited()
        analytics.run.assert_not_awaited()
        self.assertFalse(result.metadata["ok"])


if __name__ == "__main__":
    unittest.main()
