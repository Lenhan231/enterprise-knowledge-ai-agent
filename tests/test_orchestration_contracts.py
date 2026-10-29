import asyncio
import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.agents.runtime import deadline, run_sync
from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.router import AgentRouter
from core.agents.response import _supported_numbers
from core.models.agents import AgentRequest, AgentResult, Evidence, VerifiedIdentity
from test_bounded_execution import FakeAgent, FakeProvider, IDENTITY, source_result, task


class OrchestrationContractTest(unittest.IsolatedAsyncioTestCase):
    def test_numeric_grounding_accepts_localized_thousands_but_not_new_magnitudes(self):
        inputs = [{'data': {'rows': [{'count': 1320}]}, 'evidence': []}]
        self.assertTrue(_supported_numbers('1,320 products [S1]', inputs, 'Count products'))
        self.assertTrue(_supported_numbers('1.320 sản phẩm [S1]', inputs, 'Count products'))
        self.assertFalse(_supported_numbers('1.32 products [S1]', inputs, 'Count products'))
        self.assertFalse(_supported_numbers('1320e6 products [S1]', inputs, 'Count products'))

    async def test_knowledge_fails_closed_for_missing_or_empty_document_scope(self):
        rag = Mock()
        agent = KnowledgeAgent(rag)
        for identity in [None, VerifiedIdentity(subject='x'),
                         VerifiedIdentity(subject='x', document_roles={'admin'})]:
            with self.subTest(identity=identity), self.assertRaises(PermissionError):
                await agent.run(AgentRequest(question='policy', identity=identity))
        rag.generate_answer.assert_not_called()

    async def test_knowledge_insufficient_context_is_explicit_empty_outcome(self):
        rag = Mock()
        rag.generate_answer.return_value = type('R', (), {'answer': 'No evidence', 'contexts': [],
                                                         'source_ids': [], 'insufficient_context': True})()
        result = await KnowledgeAgent(rag).run(AgentRequest(question='policy', identity=IDENTITY))
        self.assertFalse(result.metadata['ok'])
        self.assertTrue(result.metadata['insufficient_context'])

    async def test_policy_to_sql_dependency_preserves_cited_threshold(self):
        tasks = [task('k', 'knowledge', 'Policy stockout threshold'),
                 task('s', 'sql', 'Count rows exceeding the cited threshold', depends_on=['k'],
                      inputs=[{'task_id': 'k', 'kind': 'evidence'}])]
        sql = FakeAgent(source_result('analytics', rows=[{'count': 3}]))
        knowledge = FakeAgent(source_result('knowledge', content='Approved reorder threshold: 5 units.'))
        await AgentRouter(None, knowledge, sql, llm=FakeProvider(tasks)).run(
            AgentRequest(question='Count rows above policy threshold', identity=IDENTITY))
        self.assertIn('5 units', sql.requests[0].question)
        self.assertIn('policy.pdf', sql.requests[0].question)

    async def test_failed_dependency_blocks_child_and_unchanged_revision_stops(self):
        tasks = [task('s', 'sql', 'Count orders'), task('k', 'knowledge', 'Policy for returned rows',
                 depends_on=['s'], inputs=[{'task_id': 's', 'kind': 'rows'}])]
        sql, knowledge = FakeAgent(ValueError('unsupported')), FakeAgent(source_result('knowledge'))
        result = await AgentRouter(None, knowledge, sql, llm=FakeProvider(tasks)).run(
            AgentRequest(question='Orders then policy', identity=IDENTITY))
        self.assertEqual(len(sql.requests), 1)
        self.assertFalse(knowledge.requests)
        self.assertIn('blocked', [entry['status'] for entry in result.metadata['task_trace']])

    async def test_invented_numbers_in_synthesis_fall_back_to_actual_evidence(self):
        class Inventing(FakeProvider):
            async def generate(self, prompt):
                if prompt.startswith('You plan'):
                    return await super().generate(prompt)
                return json.dumps({'answer': '999 stockouts [S2]. Approval [S1].', 'used_tasks': ['k', 's']})
        tasks = [task('k', 'knowledge', 'Policy'), task('s', 'sql', 'Stockouts')]
        result = await AgentRouter(None, FakeAgent(source_result('knowledge')),
                                  FakeAgent(source_result('analytics', rows=[{'stockouts': 3}])),
                                  llm=Inventing(tasks)).run(AgentRequest(question='Stockouts and policy', identity=IDENTITY))
        self.assertTrue(result.metadata['fallback'])
        self.assertNotIn('999', result.answer)
        self.assertIn('3', result.answer)
        self.assertIn('[S2]', result.answer)

    async def test_synchronous_worker_slot_lasts_until_thread_exits(self):
        release = threading.Event()
        started = threading.Event()
        def blocking():
            started.set()
            release.wait(2)
            return 'done'
        token = deadline.set(time.monotonic() + 0.03)
        try:
            with self.assertRaises(TimeoutError):
                await run_sync(blocking)
            self.assertTrue(started.is_set())
        finally:
            release.set()
            deadline.reset(token)
        await asyncio.sleep(0.01)
        self.assertEqual(await run_sync(lambda: 'available'), 'available')

    async def test_generated_agent_prose_cannot_validate_an_invented_number(self):
        class Repeating(FakeProvider):
            async def generate(self, prompt):
                if prompt.startswith('You plan'):
                    return await super().generate(prompt)
                return json.dumps({'answer': 'Policy approval [S1]. 999 products [S2].', 'used_tasks': ['k', 's']})
        sql_result = source_result('analytics', rows=[{'count': 3}])
        sql_result.answer = 'There are 999 products [S1].'
        result = await AgentRouter(None, FakeAgent(source_result('knowledge')), FakeAgent(sql_result),
            llm=Repeating([task('k', 'knowledge', 'Policy'), task('s', 'sql', 'Count products')])).run(
                AgentRequest(question='Count products and explain policy', identity=IDENTITY))
        self.assertTrue(result.metadata['fallback'])
        self.assertNotIn('999', result.answer)

    async def test_concurrent_results_do_not_depend_on_shared_destination(self):
        class Selecting(FakeProvider):
            async def generate(self, prompt):
                question = json.loads(prompt.split('DATA:\n')[1].split('\nInvalid')[0])['question']
                return json.dumps({'objective': question, 'tasks': [task('one', 'sql' if question == 'orders' else 'knowledge', question)]})
        router = AgentRouter(None, FakeAgent(source_result('knowledge')),
                             FakeAgent(source_result('analytics', rows=[{'count': 3}])), llm=Selecting([]))
        results = await asyncio.gather(*(router.run(AgentRequest(question=q, identity=IDENTITY)) for q in ['orders', 'policy']))
        self.assertEqual([r.metadata['selected_route'] for r in results], ['analytics', 'knowledge'])
