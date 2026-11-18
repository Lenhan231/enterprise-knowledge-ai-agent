import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

    async def test_confirmed_schema_retry_keeps_the_original_metric_and_scope(self):
        payload = plan({'id': 's', 'agent': 'sql',
                        'question': 'Total revenue for the previous month using commerce.sales'})
        llm = Provider(payload)
        history = [{'question': 'tháng trước thì sao', 'scope': 'doanh thu tháng gần nhất',
                    'clarification': 'Schema mismatch: available columns are date and revenue. Retry?'}]
        result = await plan_request(AgentRequest(question='Có, thử lại theo schema vừa nêu'), llm, history=history)
        self.assertEqual(result.tasks[0].question, payload['tasks'][0]['question'])
        self.assertIn('schema-mismatch confirmation', llm.prompts[0].lower())

    async def test_clear_mixed_request_does_not_broadcast_on_provider_failure(self):
        llm = Provider(RuntimeError('offline'), RuntimeError('offline'))
        with patch('core.agents.planning.generate_with_local_codex', side_effect=RuntimeError('offline')):
            with self.assertRaisesRegex(ValueError, 'planning'):
                await plan_request(AgentRequest(question='Compare revenue and policy documents'), llm)

    async def test_jev_selected_tools_get_bounded_fallback_when_planner_is_unavailable(self):
        question = 'Which products should be campaign candidates based on sales, margin, stock, and returns?'
        llm = Provider(RuntimeError('offline'), RuntimeError('offline'))
        with patch('core.agents.planning.generate_with_local_codex', side_effect=RuntimeError('offline')):
            result = await plan_request(AgentRequest(question=question), llm,
                                        selected_tools=['knowledge', 'sql'])

        self.assertTrue(result.fallback)
        self.assertEqual({task.agent for task in result.tasks}, {'knowledge', 'sql'})
        self.assertIn(question, result.tasks[0].question)
        self.assertTrue(all('Focus on' in task.question for task in result.tasks))

    async def test_single_analytics_request_skips_the_planner_model(self):
        llm = Provider(RuntimeError('offline'))
        question = 'doanh thu tháng này sao'
        result = await plan_request(AgentRequest(question=question), llm)
        self.assertTrue(result.fallback)
        self.assertEqual([task.agent for task in result.tasks], ['sql'])
        self.assertEqual(result.tasks[0].question, question)
        self.assertFalse(llm.prompts)

    async def test_jev_selected_tools_survive_the_analytics_shortcut_and_plan(self):
        question = 'Which products should be candidates for the next campaign based on sales and stock?'
        llm = Provider(
            plan({'id': 's', 'agent': 'sql', 'question': 'Rank campaign candidates from sales and stock'}),
            {'tasks':[{'id':'k','agent':'knowledge',
                       'question':'What documented criteria and guardrails guide campaign selection?',
                       'depends_on':[],'inputs':[]}]})

        result = await plan_request(AgentRequest(question=question), llm, selected_tools=['knowledge', 'sql'])

        self.assertEqual({task.agent for task in result.tasks}, {'knowledge', 'sql'})
        self.assertIn('jev_selected_tools', llm.prompts[0])
        self.assertIn('Do not ask it to calculate', llm.prompts[1])
        self.assertEqual(next(t.question for t in result.tasks if t.agent == 'knowledge'),
                         'What documented criteria and guardrails guide campaign selection?')

    async def test_product_profit_recommendation_keeps_both_evidence_sources(self):
        question = 'Doanh nghiệp nên ưu tiên nhập thêm, quảng bá hoặc ngừng bán những sản phẩm nào để cải thiện lợi nhuận?'
        from core.agents.intent_classifier import IntentClassifier
        intent = IntentClassifier.fallback(question)
        self.assertTrue(intent.needs_knowledge)
        self.assertTrue(intent.needs_sql)
        llm = Provider(plan({'id': 'k', 'agent': 'knowledge', 'question': question}),
                       {'tasks':[{'id':'s','agent':'sql','question':'Calculate product profitability and returns',
                                  'depends_on':[],'inputs':[]}]})

        result = await plan_request(AgentRequest(question=question), llm)

        self.assertEqual({task.agent for task in result.tasks}, {'knowledge', 'sql'})
        self.assertEqual(len(result.tasks), 2)
        self.assertEqual(next(task.question for task in result.tasks if task.agent == 'knowledge'), question)
        self.assertEqual(next(task.question for task in result.tasks if task.agent == 'sql'),
                         'Calculate product profitability and returns')
        self.assertEqual(len(llm.prompts), 2)

    async def test_business_decision_followup_keeps_sql_and_policy_tasks(self):
        question = 'nên ngừng bán sản phẩm nào để cải thiện lợi nhuận?'
        llm = Provider(plan(
            {'id': 's', 'agent': 'sql', 'question': 'Rank products by recent net revenue and gross profit'},
            {'id': 'k', 'agent': 'knowledge', 'question': 'Find policy for replenishment, promotion, and discontinuation'},
            objective=question,
        ))
        history = [{'question': 'current product profitability', 'scope': 'product revenue and gross profit'}]

        result = await plan_request(AgentRequest(question=question), llm, history=history)

        self.assertEqual({task.agent for task in result.tasks}, {'knowledge', 'sql'})
        self.assertIn('product revenue and gross profit', llm.prompts[0])

    async def test_followup_planning_uses_history_for_any_tool(self):
        cases = [
            ({'question': 'doanh thu tháng 3', 'scope': 'doanh thu tháng 3'},
             'tháng trước thì sao', 'sql', 'doanh thu tháng 2 năm 2026'),
            ({'question': 'annual leave policy', 'scope': 'annual leave policy'},
             'what about parental leave?', 'knowledge', 'parental leave policy'),
        ]
        for turn, question, agent, resolved_question in cases:
            with self.subTest(agent=agent):
                llm = Provider(plan({'id': 'followup', 'agent': agent,
                                     'question': resolved_question}, objective=resolved_question))
                result = await plan_request(AgentRequest(question=question), llm, history=[turn])

                self.assertEqual(result.tasks[0].agent, agent)
                self.assertEqual(result.tasks[0].question, resolved_question)
                self.assertIn(turn['scope'], llm.prompts[0])
                self.assertEqual(len(llm.prompts), 1)

    async def test_sql_followup_receives_prior_resolved_scope_and_confirmed_metric(self):
        llm = Provider(plan({'id': 's', 'agent': 'sql',
                             'question': 'So sánh doanh thu năm nay với năm ngoái'},
                            objective='So sánh doanh thu năm nay với năm ngoái'))
        history = [{'question': 'doanh thu năm nay', 'scope': 'doanh thu năm nay',
                    'clarification': '', 'metrics': 'revenue'}]
        result = await plan_request(AgentRequest(question='so với năm ngoái'), llm, history=history)
        data = json.loads(llm.prompts[0].split('DATA:\n', 1)[1].split('\n\nInvalid', 1)[0])
        self.assertEqual(data['follow_up_context']['prior_resolved_scope'], 'doanh thu năm nay')
        self.assertEqual(data['follow_up_context']['prior_confirmed_sql_metrics'], 'revenue')
        self.assertIn('Do not ask which metric', llm.prompts[0])
        self.assertEqual(result.tasks[0].question, 'So sánh doanh thu năm nay với năm ngoái')

    async def test_date_clarification_answer_keeps_business_question_and_confirmation(self):
        resolved = 'Compare product revenue by segment for the last 30 days'
        llm = Provider(plan({'id': 's', 'agent': 'sql', 'question': resolved}, objective=resolved))
        history = [{'question': 'giờ nên đẩy mạnh segment sản phẩm nào nhỉ',
                    'scope': 'Recommend a product segment from the previous sales analysis',
                    'clarification': 'Confirm that the requested period is the most recent 30 days.'}]

        result = await plan_request(AgentRequest(question='last 30 days'), llm, history=history)

        self.assertEqual(result.tasks[0].question, resolved)
        self.assertIn('giờ nên đẩy mạnh segment sản phẩm nào nhỉ', llm.prompts[0])
        self.assertIn('Confirm that the requested period is the most recent 30 days.', llm.prompts[0])

    async def test_clarification_without_objective_is_normalized_instead_of_failing(self):
        llm = Provider({'clarification': 'Bạn muốn so sánh khoảng thời gian nào?'})
        result = await plan_request(AgentRequest(question='so sánh thêm'), llm,
                                    history=[{'question': 'doanh thu năm nay', 'scope': 'doanh thu năm nay'}])
        self.assertEqual(result.objective, 'doanh thu năm nay')
        self.assertEqual(result.tasks, [])
        self.assertEqual(result.clarification, 'Bạn muốn so sánh khoảng thời gian nào?')
        self.assertEqual(len(llm.prompts), 1)

    async def test_genuine_ambiguity_is_targeted_and_repair_is_bounded(self):
        llm = Provider('bad json', {'objective': 'Compare revenue', 'clarification': 'Which years?', 'tasks': []})
        result = await plan_request(AgentRequest(question='Compare revenue and explain policy'), llm)
        self.assertEqual(result.clarification, 'Which years?')
        self.assertEqual(len(llm.prompts), 2)

    def test_dependency_can_reference_valid_predecessor_rows(self):
        result = AgentPlan.model_validate(plan(
            {'id': 's', 'agent': 'sql', 'question': 'Rank stockouts'},
            {'id': 'k', 'agent': 'knowledge', 'question': 'Policy for the returned categories',
             'depends_on': ['s'], 'inputs': [{'task_id': 's', 'kind': 'rows', 'field': 'category'}]}))
        self.assertEqual(result.tasks[1].inputs[0].field, 'category')
