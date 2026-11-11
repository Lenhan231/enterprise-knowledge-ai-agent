import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.agents.report_agent import ReportAgent
from core.agents.router import AgentRouter
from core.models.agents import AgentRequest, AgentResult, Evidence
from test_bounded_execution import FakeAgent, IDENTITY, source_result, task


class SourcePlanner:
    def __init__(self, tasks=None, clarification=None):
        self.tasks = tasks or [task('s', 'sql', 'Count catalog products'),
                               task('k', 'knowledge', 'Stock adjustment approval procedure')]
        self.clarification = clarification
        self.prompts = []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        if not prompt.startswith('You plan'):
            raise AssertionError('Source collection must not generate a combined chat answer')
        return json.dumps({'objective': 'Catalog count and approval evidence',
                           'tasks': [] if self.clarification else self.tasks,
                           'clarification': self.clarification})


class ReportOrchestrationTest(unittest.IsolatedAsyncioTestCase):
    def agents(self, *, missing_documents=False, clarification=None):
        knowledge = FakeAgent(ValueError('unavailable') if missing_documents else
                              source_result('knowledge', content='Approval requires an independent reviewer.'))
        knowledge.retrieve = AsyncMock(side_effect=AssertionError('Do not repeat retrieval per section'))
        sql = FakeAgent(source_result('analytics', rows=[{'count': 100}]))
        planner = SourcePlanner(clarification=clarification)
        router = AgentRouter(None, knowledge, sql, llm=planner)
        llm = Mock()
        def draft(prompt):
            heading = json.loads(prompt.split('Heading (data): ')[1].splitlines()[0])
            text = 'Count 100 [S1].' if missing_documents else 'Count 100 [S1]. Approval requires an independent reviewer [S2].'
            return json.dumps({'sections': {heading: text}, 'tables': []})
        llm.generate.side_effect = draft
        return ReportAgent(knowledge, sql, llm=llm, source_router=router), router, planner, knowledge, sql, llm

    async def test_orchestrated_collection_decomposes_once_and_reuses_raw_sources_for_sections(self):
        agent, router, planner, knowledge, sql, llm = self.agents()
        request = AgentRequest(question='Write a report on catalog count and approval policy', identity=IDENTITY)
        result, payload, _ = await agent.generate_from_template(
            request, 'report.md', b'# Summary\n# Findings', source_mode='orchestrated')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertIn(b'Count 100', payload)
        self.assertEqual(len(sql.requests), 1)
        self.assertEqual(len(knowledge.requests), 1)
        self.assertEqual(sql.requests[0].question, 'Count catalog products')
        self.assertEqual(knowledge.requests[0].question, 'Stock adjustment approval procedure')
        self.assertEqual(sql.requests[0].identity, IDENTITY)
        knowledge.retrieve.assert_not_awaited()
        self.assertEqual(len(planner.prompts), 1)
        self.assertIn('report_sources', planner.prompts[0])
        self.assertIn('Findings', planner.prompts[0])
        self.assertEqual(result.metadata['source_collection']['selected_route'], 'hybrid')
        self.assertEqual(result.metadata['row_coverage']['available_rows'], 1)

    async def test_combined_alias_uses_new_workflow_and_partial_sources_stay_partial(self):
        agent, _, _, knowledge, sql, _ = self.agents(missing_documents=True)
        result, payload, _ = await agent.generate_from_template(
            AgentRequest(question='Count catalog and find approval policy', identity=IDENTITY),
            'report.md', b'# Summary', source_mode='combined')
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertEqual(result.metadata['source_collection']['status'], 'partial')
        self.assertIn(b'Status: partial', payload)
        self.assertEqual(len(sql.requests), 1)
        knowledge.retrieve.assert_not_awaited()

    async def test_collection_clarification_stops_report_generation_and_keeps_its_question(self):
        agent, _, _, knowledge, sql, llm = self.agents(clarification='Which year should the report cover?')
        result, payload, _ = await agent.generate_from_template(
            AgentRequest(question='Report on that year', identity=IDENTITY), source_mode='orchestrated')
        self.assertEqual(result.metadata['status'], 'clarification_required')
        self.assertEqual(result.answer, 'Which year should the report cover?')
        self.assertEqual(payload, b'')
        self.assertFalse(sql.requests)
        self.assertFalse(knowledge.requests)
        llm.generate.assert_not_called()

    async def test_report_conversation_is_isolated_from_general_chat(self):
        _, router, _, _, _, _ = self.agents()
        request = AgentRequest(question='Count catalog', conversation_id='same-id', identity=IDENTITY)
        await router.collect_sources(request, ['Summary'])
        self.assertIn((IDENTITY.subject, 'report:same-id'), router.report_conversations.entries)
        self.assertNotIn((IDENTITY.subject, 'same-id'), router.conversations.entries)
        self.assertNotIn((IDENTITY.subject, 'report:same-id'), router.conversations.entries)

    async def test_partial_rows_without_database_excerpt_are_still_usable(self):
        agent, router, _, _, sql, _ = self.agents(missing_documents=True)
        sql.result = AgentResult(answer='Rows returned', agent='analytics', data={'rows': [{'count': 100}]},
                                 metadata={'ok': False, 'status': 'partial'})
        collected = await router.collect_sources(AgentRequest(question='Count and policy', identity=IDENTITY), ['Summary'])
        self.assertEqual(collected.metadata['status'], 'partial')
        self.assertEqual(collected.data['tasks']['s']['rows'], [{'count': 100}])

    async def test_no_usable_sources_does_not_invent_a_report(self):
        agent, _, _, knowledge, sql, llm = self.agents(missing_documents=True)
        sql.result = ValueError('invalid query')
        result, payload, _ = await agent.generate_from_template(
            AgentRequest(question='Count catalog and policy', identity=IDENTITY), source_mode='orchestrated')
        self.assertEqual(result.metadata['status'], 'failed')
        self.assertEqual(payload, b'')
        llm.generate.assert_not_called()
