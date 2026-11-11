import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.models.agent_plan import AgentPlan
from core.agents.planning import plan_request
from core.models.agents import AgentRequest


class Provider:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return json.dumps(result) if isinstance(result, dict) else result


def plan(*tasks, objective='Compare 2021 and 2022 revenue with policy'):
    return {'objective': objective, 'tasks': list(tasks)}


class RequestPlanningTest(unittest.IsolatedAsyncioTestCase):
    def test_rejects_cycles_unknown_agents_and_forged_fields(self):
        invalid = [
            plan({'id': 'a', 'agent': 'sql', 'question': 'revenue', 'depends_on': ['a']}),
            plan({'id': 'a', 'agent': 'report', 'question': 'report'}),
            plan({'id': 'a', 'agent': 'sql', 'question': 'revenue', 'identity': 'admin'}),
            plan({'id': 'a', 'agent': 'sql', 'question': 'revenue', 'inputs': [{'task_id': 'b', 'kind': 'rows'}]}),
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                AgentPlan.model_validate(value)

    async def test_focused_bilingual_plan_preserves_context_and_does_not_use_rules(self):
        payload = plan({'id': 'k', 'agent': 'knowledge', 'question': 'Revenue recognition policy'},
                       {'id': 's', 'agent': 'sql', 'question': 'Compare revenue in 2021 and 2022'})
        llm = Provider(payload)
        result = await plan_request(AgentRequest(question='So sánh doanh thu với chính sách'), llm,
                                    history=[{'question': '2021 and 2022', 'scope': 'Revenue'}])
        self.assertEqual([t.question for t in result.tasks], [t['question'] for t in payload['tasks']])
        self.assertIn('2021 and 2022', llm.prompts[0])
        self.assertEqual(len(llm.prompts), 1)

    async def test_clear_mixed_request_does_not_broadcast_on_provider_failure(self):
        llm = Provider(RuntimeError('offline'), RuntimeError('offline'))
        with self.assertRaisesRegex(ValueError, 'planning'):
            await plan_request(AgentRequest(question='Compare revenue and policy documents'), llm)

    async def test_genuine_ambiguity_is_targeted_and_repair_is_bounded(self):
        llm = Provider('bad json', {'objective': 'Compare revenue', 'clarification': 'Which years?', 'tasks': []})
        result = await plan_request(AgentRequest(question='Compare revenue'), llm)
        self.assertEqual(result.clarification, 'Which years?')
        self.assertEqual(len(llm.prompts), 2)

    def test_dependency_can_reference_valid_predecessor_rows(self):
        result = AgentPlan.model_validate(plan(
            {'id': 's', 'agent': 'sql', 'question': 'Rank stockouts'},
            {'id': 'k', 'agent': 'knowledge', 'question': 'Policy for the returned categories',
             'depends_on': ['s'], 'inputs': [{'task_id': 's', 'kind': 'rows', 'field': 'category'}]}))
        self.assertEqual(result.tasks[1].inputs[0].field, 'category')
