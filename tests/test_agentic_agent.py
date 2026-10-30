import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.router import AgentRouter
from core.models.agents import AgentRequest, AgentResult, Evidence
from test_bounded_execution import IDENTITY


class LangGraphRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_agentic_mode_calls_both_agents_once_and_merges_evidence(self):
        llm = AsyncMock()
        llm.generate.side_effect = [json.dumps({'objective': 'Policy and revenue', 'tasks': [{'id': 'k', 'agent': 'knowledge', 'question': 'Policy about revenue'}, {'id': 's', 'agent': 'sql', 'question': 'Revenue total'}]}), json.dumps({'answer': 'Policy [S1] and revenue [S2].', 'used_tasks': ['k', 's']})]
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

        result = await agent.run_mode(AgentRequest(question="What does policy say about revenue?", identity=IDENTITY), "agentic")

        knowledge.run.assert_awaited_once()
        analytics.run.assert_awaited_once()
        self.assertEqual(result.agent, "hybrid")
        self.assertTrue(result.answer.startswith("Policy [S1] and revenue [S2]."))
        self.assertEqual(result.evidence[0].source, "policy.pdf")
        self.assertEqual(result.evidence[1].source, "commerce.sales")
        self.assertIn("commerce.sales", llm.generate.await_args_list[1].args[0])
        self.assertEqual([e.source for e in result.evidence], ["policy.pdf", "commerce.sales"])
        self.assertEqual([e.citation_id for e in result.evidence], ["S1", "S2"])

    async def test_agentic_mode_calls_only_selected_agent(self):
        llm = AsyncMock()
        llm.generate.return_value = json.dumps({'objective': 'Count orders', 'tasks': [{'id': 's', 'agent': 'sql', 'question': 'Count orders'}]})
        knowledge, analytics = AsyncMock(), AsyncMock()
        analytics.run.return_value = AgentResult(answer="Rows [S1]", agent="analytics", evidence=[Evidence(citation_id="S1", source_type="database", source="commerce.orders")], data={"rows": [{"count": 1}]})
        agent = AgentRouter(None, knowledge, analytics, llm=llm)

        result = await agent.run_mode(AgentRequest(question="How many orders?", identity=IDENTITY), "agentic")

        knowledge.run.assert_not_awaited()
        analytics.run.assert_awaited_once()
        self.assertEqual(result.answer, "Rows [S1]")
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
