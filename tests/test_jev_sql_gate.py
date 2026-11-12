from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.agents.execution import TaskOutcome
from core.agents.response import assemble_response
from core.models.agent_plan import AgentPlan
from core.models.agents import AgentRequest, AgentResult, Evidence, VerifiedIdentity


class JevSqlGateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.agent = SQLAnalyticsAgent(Mock())
        self.request = AgentRequest(
            question='Which customer bought the most?',
            identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}),
        )

    async def test_ambiguous_question_returns_clarification_without_running_sql(self):
        with patch.object(self.agent, '_check_ambiguity', return_value={
            'choice': 'ambiguous', 'probabilities': {'clear': 0.13, 'ambiguous': 0.87},
            'confidence': 0.87, 'model': 'typesafe/jev-1.14',
        }), patch.object(self.agent, '_run_payload') as run_sql:
            result = await self.agent.run_payload(self.request)

        self.assertEqual(result['metadata']['status'], 'clarification_required')
        self.assertEqual(result['query_status'], 'clarification_required')
        self.assertEqual(result['metadata']['jev']['probabilities']['ambiguous'], 0.87)
        run_sql.assert_not_awaited()

    async def test_pending_clarification_reply_skips_jev_and_continues_sql_flow(self):
        request = self.request.model_copy(update={'metadata': {'_sql_context': {'pending': {'question': 'prior'}}}})
        with patch.object(self.agent, '_check_ambiguity') as jev, patch.object(
            self.agent, '_run_payload', return_value={'ok': True, 'rows': [], 'metadata': {}, 'query_status': 'executed'}
        ) as run_sql:
            await self.agent.run_payload(request)

        jev.assert_not_called()
        run_sql.assert_awaited_once()

    def test_database_timeout_has_actionable_vietnamese_error(self):
        result = self.agent._database_error(TimeoutError(), 'SELECT 1', ())

        self.assertEqual(result['metadata']['failure_code'], 'sql_timeout')
        self.assertEqual(result['query_status'], 'error')
        self.assertIn('thu hẹp', result['answer'])

    async def test_sql_execution_error_survives_response_assembly(self):
        plan = AgentPlan(objective='Answer the request', tasks=[
            {'id': 'query', 'agent': 'sql', 'question': 'Count purchases'},
        ])
        task = plan.tasks[0]
        outcomes = {'query': TaskOutcome(task, 'failed', AgentResult(
            answer='Truy vấn dữ liệu mất quá lâu.', agent='analytics',
            data={'query_status': 'error', 'attempted_sql': 'SELECT 1'},
            metadata={'failure_code': 'sql_timeout', 'status': 'failed'},
        ))}
        execution = SimpleNamespace(outcomes=outcomes, trace=[], invocations=1)

        result = await assemble_response(self.request, plan, execution, provider=None)

        self.assertEqual(result.answer, 'Truy vấn dữ liệu mất quá lâu.')
        self.assertEqual(result.metadata['failure_code'], 'sql_timeout')
        self.assertEqual(result.metadata['limitations'], [])

    async def test_router_keeps_sql_clarification_when_knowledge_has_evidence(self):
        plan = AgentPlan(objective='Answer the request', tasks=[
            {'id': 'docs', 'agent': 'knowledge', 'question': 'Find related policy'},
            {'id': 'query', 'agent': 'sql', 'question': 'Count purchases'},
        ])
        knowledge_task, sql_task = plan.tasks
        outcomes = {
            'docs': TaskOutcome(knowledge_task, 'complete', AgentResult(
                answer='The policy applies.', agent='knowledge',
                evidence=[Evidence(citation_id='S1', source_type='document', source='policy.pdf')],
            )),
            'query': TaskOutcome(sql_task, 'clarification_required', AgentResult(
                answer='Which purchase metric should I use?', agent='analytics',
                metadata={'clarification_required': True, 'status': 'clarification_required'},
            )),
        }
        execution = SimpleNamespace(outcomes=outcomes, trace=[], invocations=2)

        result = await assemble_response(self.request, plan, execution, provider=None)

        self.assertEqual(result.answer, 'Which purchase metric should I use?')
        self.assertEqual(result.metadata['status'], 'clarification_required')


if __name__ == '__main__':
    unittest.main()
