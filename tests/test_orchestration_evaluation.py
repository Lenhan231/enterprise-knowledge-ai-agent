import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
from core.agents.router import AgentRouter
from core.models.agents import AgentRequest, VerifiedIdentity
from test_bounded_execution import FakeAgent, FakeProvider, IDENTITY, source_result, task
from scripts.agents.benchmark_router_25 import benchmark_unified


class OrchestrationEvaluationTest(unittest.IsolatedAsyncioTestCase):
    async def test_24_bilingual_scenario_contracts(self):
        cases = json.loads((ROOT/'data/evaluation/orchestration_cases.json').read_text(encoding='utf-8'))['cases']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({c['id'] for c in cases}), 24)
        self.assertEqual({c['language'] for c in cases}, {'en', 'vi'})
        self.assertTrue(all(any(ord(ch) > 127 for ch in c['question'])
                            for c in cases if c['language'] == 'vi'))
        for case in cases:
            with self.subTest(case=case['id']):
                tasks = [task('k', 'knowledge', 'Inventory policy approval requirements')]
                if case['expected_route'] == 'analytics':
                    tasks = [task('s', 'sql', 'Count orders in 2022')]
                elif case['expected_route'] == 'hybrid':
                    tasks.append(task('s', 'sql', 'Inventory counts in 2022'))
                if case['scenario'] == 'sql-knowledge':
                    tasks[0].update(depends_on=['s'], inputs=[{'task_id': 's', 'kind': 'rows', 'field': 'category'}])
                if case['scenario'] == 'knowledge-sql':
                    tasks[1].update(depends_on=['k'], inputs=[{'task_id': 'k', 'kind': 'evidence'}])
                class ScenarioProvider(FakeProvider):
                    async def generate(self, prompt):
                        if case['scenario'] == 'provider-failure':
                            raise RuntimeError('provider offline')
                        if case['expected_route'] == 'clarification':
                            return json.dumps({'objective': case['question'], 'tasks': [], 'clarification': 'Which scope or standalone mode?'})
                        return await super().generate(prompt)
                knowledge = FakeAgent(source_result('knowledge', content='Approval requires inventory checks. Threshold 5 units.'))
                sql = FakeAgent(source_result('analytics', rows=[{'category': 'Outdoor', 'stockouts': 3}]))
                router = AgentRouter(None, knowledge, sql, llm=ScenarioProvider(tasks))
                identity = IDENTITY
                if case['scenario'] == 'denial':
                    identity = VerifiedIdentity(subject='viewer', permissions={'documents:read'}, document_roles={'employee'})
                    with self.assertRaises(PermissionError):
                        await router.run(AgentRequest(question=case['question'], identity=identity))
                    self.assertFalse(sql.requests)
                    continue
                result = await router.run(AgentRequest(question=case['question'], identity=identity))
                if case['scenario'] == 'provider-failure':
                    self.assertFalse(sql.requests)
                    self.assertFalse(knowledge.requests)
                else:
                    self.assertEqual(result.metadata['selected_route'], case['expected_route'])
                self.assertLessEqual(result.metadata.get('specialist_invocations', 0), 6)

    async def test_benchmark_refuses_existing_directory_and_zero_cases(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                await benchmark_unified(Path(root), [], b'{}')
            with self.assertRaises(ValueError):
                await benchmark_unified(Path(root)/'new', [], b'{}')


class OrchestrationAPIBoundaryTest(unittest.TestCase):
    def test_both_api_models_reject_forged_server_fields(self):
        from core.agents.main import ChatRequest
        from app.agents import AgentChatRequest
        for model in [ChatRequest, AgentChatRequest]:
            self.assertEqual(model(question='q').agent_mode, 'auto')
            for key in ['identity', 'history', 'plan', 'task_results', 'deadline', '_orchestration']:
                with self.subTest(model=model.__name__, key=key), self.assertRaises(ValueError):
                    model(question='q', metadata={key: 'forged'})

    def test_auto_and_legacy_alias_use_the_actual_graph_through_api(self):
        from fastapi.testclient import TestClient
        from core.agents.main import create_app
        router = AgentRouter(None, FakeAgent(source_result('knowledge')),
                             FakeAgent(source_result('analytics', rows=[{'count': 3}])),
                             llm=FakeProvider([task('s', 'sql', 'Count orders')]))
        with TestClient(create_app(chat_agent=router, identity_resolver=lambda _: IDENTITY)) as client:
            for mode in ['auto', 'agentic']:
                result = client.post('/api/chat', json={'question':'Count orders', 'agent_mode':mode})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()['metadata']['status'], 'complete')
                self.assertEqual(result.json()['metadata']['selected_route'], 'analytics')
