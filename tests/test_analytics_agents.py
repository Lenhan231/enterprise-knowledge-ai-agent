import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
import json
from test_bounded_execution import IDENTITY, source_result, FakeProvider, task

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.sql_agent.analytics_agent import AnalyticsAgent
from core.agents.base import BaseAgent
from core.agents.router import AgentRouter
from core.sql_agent.agent import payload_to_agent_result
from core.agents.sql.agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest, AgentResult, VerifiedIdentity


class AnalyticsAgentContractTest(unittest.IsolatedAsyncioTestCase):
    def test_payload_mapping_keeps_rows_evidence_and_limitations(self):
        result = payload_to_agent_result({
            "ok": False,
            "rows": [{"category": "Outdoor", "count": 12}],
            "evidence": [{"source": "commerce.products"}],
            "limitations": ["Limited to the approved data sources."],
        })

        self.assertEqual(result.agent, "analytics")
        self.assertEqual(result.data["rows"][0]["count"], 12)
        self.assertEqual(result.evidence[0].source, "commerce.products")
        self.assertIn("limitations", result.metadata)

    async def test_agents_follow_base_contract_and_close_repository(self):
        repository = AsyncMock()
        sql_agent = type("SQL", (BaseAgent,), {"run": AsyncMock(), "close": AsyncMock()})()
        analytics = AnalyticsAgent(sql_agent)
        self.assertIsInstance(analytics, BaseAgent)
        await analytics.close()
        sql_agent.close.assert_awaited_once()

    async def test_router_auto_and_explicit_modes(self):
        request = AgentRequest(question="List products", identity=IDENTITY)

        class Classifier:
            def classify(self, _question):
                return type("Intent", (), {"intent": "analytics", "output_mode": "answer",
                                            "needs_knowledge": False, "needs_sql": True})()

        knowledge, sql = AsyncMock(), AsyncMock()
        for name, agent in (("knowledge", knowledge), ("analytics", sql)):
            agent.run.return_value = source_result(name, rows=[{"count": 1}] if name == "analytics" else None)
        llm = AsyncMock()
        llm.generate.return_value = json.dumps({'objective': 'List products', 'tasks': [{'id': 's', 'agent': 'sql', 'question': 'List products'}]})
        router = AgentRouter(Classifier(), knowledge, sql, llm=llm)

        auto = await router.run(request)
        explicit = await router.run_mode(request, "sql")

        self.assertEqual(auto.agent, "analytics")
        self.assertEqual(explicit.agent, "analytics")
        self.assertEqual(sql.run.await_count, 2)

    async def test_auto_uses_raw_sql_engine_while_sql_mode_adds_summary(self):
        class LLM:
            def __init__(self):
                self.prompts = []

            def generate(self, prompt):
                self.prompts.append(prompt)
                return 'Doanh thu năm 2025 là 123 [S1].'

        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{'revenue': 123}]
        llm = LLM()
        engine = SQLAnalyticsAgent(repository, llm=llm)
        presentation = AnalyticsAgent(engine)
        router = AgentRouter(None, None, presentation)
        request = AgentRequest(question='doanh thu năm 2025', identity=IDENTITY)

        self.assertIs(router.analytics_agent, engine)
        self.assertIs(router.sql_mode_agent, presentation)
        result = await router.run_mode(request, 'sql')

        self.assertTrue(result.answer.startswith('Doanh thu năm 2025 là 123'))
        self.assertEqual(len(llm.prompts), 1)
        self.assertIn("Answer the user's question", llm.prompts[0])

    async def test_langgraph_router_runs_both_agents_for_hybrid_auto_intent(self):
        request = AgentRequest(question="Compare policy and stock", identity=IDENTITY)

        class Classifier:
            def classify(self, _question):
                return type("Intent", (), {"intent": "hybrid", "output_mode": "answer",
                                            "needs_knowledge": True, "needs_sql": True})()

        knowledge, sql = AsyncMock(), AsyncMock()
        knowledge.run.return_value = source_result("knowledge")
        sql.run.return_value = source_result("analytics", rows=[{"count": 3}])
        router = AgentRouter(Classifier(), knowledge, sql, llm=FakeProvider([task('k', 'knowledge', 'Stock policy'), task('s', 'sql', 'Stock count')]))

        result = await router.run(request)

        self.assertEqual(knowledge.run.await_args.args[0].question, "Stock policy")
        self.assertEqual(sql.run.await_args.args[0].question, "Stock count")
        self.assertEqual(router.last_destination, "hybrid")
        self.assertEqual(result.agent, "hybrid")
        self.assertTrue(result.evidence)


if __name__ == "__main__":
    unittest.main()
