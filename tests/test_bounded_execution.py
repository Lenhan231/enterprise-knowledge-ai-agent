import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.agents.router import AgentRouter
from core.models.agents import AgentRequest, AgentResult, Evidence, VerifiedIdentity

IDENTITY = VerifiedIdentity(subject='analyst', permissions={'analytics:read', 'documents:read'}, document_roles={'admin'})


def task(key, agent, question, **kwargs):
    return dict(id=key, agent=agent, question=question, **kwargs)


def source_result(agent, *, rows=None, content='Policy requires approval.'):
    return AgentResult(answer='Supported observation [S1].', agent=agent,
                       evidence=[Evidence(citation_id='S1', source_type='document' if agent == 'knowledge' else 'database',
                                          source='policy.pdf' if agent == 'knowledge' else 'commerce.inventory', content=content)],
                       data={} if rows is None else {'rows': rows}, metadata={'ok': True})


class FakeProvider:
    def __init__(self, tasks, revised=None):
        self.tasks, self.revised, self.prompts = tasks, revised, []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        if prompt.startswith('You plan'):
            tasks = self.revised if '"previous": {' in prompt and self.revised else self.tasks
            return json.dumps({'objective': 'Original scope', 'tasks': tasks})
        return json.dumps({'answer': 'Document approval is required [S1]. SQL contains 3 stockouts [S2].',
                           'used_tasks': ['k', 's']})


class FakeAgent:
    def __init__(self, result):
        self.result, self.requests = result, []

    async def run(self, request):
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class BoundedExecutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_mixed_request_is_decomposed_and_identity_preserved_for_both_aliases(self):
        tasks = [task('k', 'knowledge', 'Stockout approval policy'), task('s', 'sql', 'Count stockouts in 2022')]
        for mode in ['auto', 'agentic']:
            knowledge = FakeAgent(source_result('knowledge'))
            sql = FakeAgent(source_result('analytics', rows=[{'stockouts': 3}]))
            router = AgentRouter(None, knowledge, sql, llm=FakeProvider(tasks))
            request = AgentRequest(question='Count stockouts in 2022 and explain approval policy', identity=IDENTITY)
            result = await (router.run(request) if mode == 'auto' else router.run_mode(request, mode))
            self.assertEqual(knowledge.requests[0].question, tasks[0]['question'])
            self.assertEqual(sql.requests[0].question, tasks[1]['question'])
            self.assertEqual(sql.requests[0].identity, IDENTITY)
            self.assertEqual(result.metadata['selected_route'], 'hybrid')
            self.assertEqual(result.metadata['status'], 'complete')
            self.assertEqual([e.citation_id for e in result.evidence], ['S1', 'S2'])

    async def test_dependent_knowledge_receives_only_referenced_rows_with_provenance(self):
        tasks = [task('s', 'sql', 'Rank categories by stockouts'),
                 task('k', 'knowledge', 'Policy for returned categories', depends_on=['s'],
                      inputs=[{'task_id': 's', 'kind': 'rows', 'field': 'category'}])]
        sql = FakeAgent(source_result('analytics', rows=[{'category': 'Outdoor', 'unrelated': 'secret'}]))
        knowledge = FakeAgent(source_result('knowledge'))
        result = await AgentRouter(None, knowledge, sql, llm=FakeProvider(tasks)).run(
            AgentRequest(question='Rank categories and find their policy', identity=IDENTITY))
        self.assertIn('Outdoor', knowledge.requests[0].question)
        self.assertNotIn('secret', knowledge.requests[0].question)
        self.assertIn('commerce.inventory', knowledge.requests[0].question)
        self.assertEqual(result.metadata['task_trace'][0]['id'], 's')

    async def test_partial_failure_preserves_success_and_blocks_descendants(self):
        tasks = [task('k', 'knowledge', 'Policy'), task('s', 'sql', 'Count orders')]
        knowledge = FakeAgent(source_result('knowledge'))
        sql = FakeAgent(ValueError('unsupported schema'))
        result = await AgentRouter(None, knowledge, sql, llm=FakeProvider(tasks)).run(
            AgentRequest(question='Policy and orders', identity=IDENTITY))
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertFalse(result.metadata['ok'])
        self.assertTrue(result.evidence)
        self.assertLessEqual(len(sql.requests), 2)

    async def test_denial_never_invokes_agent_or_replans_to_another_identity(self):
        tasks = [task('s', 'sql', 'Count orders')]
        llm = FakeProvider(tasks)
        sql = FakeAgent(source_result('analytics'))
        with self.assertRaises(PermissionError):
            await AgentRouter(None, FakeAgent(source_result('knowledge')), sql, llm=llm).run(
                AgentRequest(question='orders', identity=VerifiedIdentity(subject='viewer', permissions={'documents:read'},
                                                                         document_roles={'employee'})))
        self.assertFalse(sql.requests)
        self.assertEqual(len(llm.prompts), 1)

    async def test_explicit_report_and_dashboard_remain_standalone(self):
        report = FakeAgent(AgentResult(answer='report', agent='report'))
        dashboard = FakeAgent(AgentResult(answer='dashboard', agent='dashboard'))
        llm = FakeProvider([])
        router = AgentRouter(None, None, None, report_agent=report, dashboard_agent=dashboard, llm=llm)
        for mode in ['report', 'dashboard']:
            result = await router.run_mode(AgentRequest(question='standalone'), mode)
            self.assertEqual(result.answer, mode)
        self.assertFalse(llm.prompts)

    async def test_new_plan_after_failure_can_recover_but_never_repeat_unchanged(self):
        initial = [task('s', 'sql', 'Unsupported ranking')]
        revised = [task('s2', 'sql', 'Supported product count')]
        class Repairable(FakeAgent):
            async def run(self, request):
                self.requests.append(request)
                return (AgentResult(answer='Unsupported field', agent='analytics', metadata={'ok': False})
                        if request.question == 'Unsupported ranking' else source_result('analytics', rows=[{'count': 3}]))
        sql = Repairable(None)
        result = await AgentRouter(None, FakeAgent(None), sql, llm=FakeProvider(initial, revised)).run(
            AgentRequest(question='Count products', identity=IDENTITY))
        self.assertEqual(len(sql.requests), 2)
        self.assertEqual(result.metadata['revisions'], 1)
        self.assertEqual(result.metadata['status'], 'complete')

    async def test_deadline_returns_without_waiting_for_slow_specialist(self):
        class Slow(FakeAgent):
            async def run(self, request):
                await asyncio.sleep(1)
                return source_result('analytics')
        router = AgentRouter(None, None, Slow(None), llm=FakeProvider([task('s', 'sql', 'Count orders')]),
                             request_timeout=0.03)
        result = await router.run(AgentRequest(question='Count orders', identity=IDENTITY))
        self.assertEqual(result.metadata['status'], 'failed')
        self.assertIn('deadline', result.answer.casefold())

    async def test_deadline_preserves_a_sibling_that_already_completed(self):
        class Slow(FakeAgent):
            async def run(self, request):
                await asyncio.sleep(5)
                return source_result('knowledge')
        tasks = [task('s', 'sql', 'Count orders'), task('k', 'knowledge', 'Order processing policy')]
        router = AgentRouter(None, Slow(None), FakeAgent(source_result('analytics', rows=[{'count': 3}])),
                             llm=FakeProvider(tasks), request_timeout=0.5)
        result = await router.run(AgentRequest(question='Orders and policy', identity=IDENTITY))
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertTrue(result.evidence)
        self.assertIn('3', result.answer)

    async def test_execution_never_exceeds_six_invocations_or_two_concurrent_tasks(self):
        class Transient(FakeAgent):
            active, peak = 0, 0
            async def run(self, request):
                self.requests.append(request)
                self.active += 1
                self.peak = max(self.peak, self.active)
                await asyncio.sleep(0)
                self.active -= 1
                raise ConnectionError('temporary')
        sql = Transient(None)
        tasks = [task('s'+str(i), 'sql', 'Count orders '+str(i)) for i in range(4)]
        result = await AgentRouter(None, None, sql, llm=FakeProvider(tasks)).run(
            AgentRequest(question='Four scoped counts', identity=IDENTITY))
        self.assertLessEqual(len(sql.requests), 6)
        self.assertEqual(result.metadata['specialist_invocations'], 6)
        self.assertEqual(sql.peak, 2)

    async def test_revision_keeps_completed_sql_and_revises_only_unfinished_lookup(self):
        initial = [task('s', 'sql', 'Count products'), task('k', 'knowledge', 'Inventory approval policy')]
        revised = [task('s', 'sql', 'Count the catalog products'),
                   task('k', 'knowledge', 'Stock adjustment approval procedure')]
        class Lookup(FakeAgent):
            async def run(self, request):
                self.requests.append(request)
                if request.question == initial[1]['question']:
                    return AgentResult(answer='No supporting evidence', agent='knowledge',
                                       metadata={'ok': False, 'insufficient_context': True})
                return source_result('knowledge')
        sql, knowledge = FakeAgent(source_result('analytics', rows=[{'count': 3}])), Lookup(None)
        result = await AgentRouter(None, knowledge, sql, llm=FakeProvider(initial, revised)).run(
            AgentRequest(question='Count products and explain approval', identity=IDENTITY))
        self.assertEqual(len(sql.requests), 1)
        self.assertEqual(sql.requests[0].question, 'Count products')
        self.assertEqual(len(knowledge.requests), 2)
        self.assertEqual(result.metadata['status'], 'complete')
