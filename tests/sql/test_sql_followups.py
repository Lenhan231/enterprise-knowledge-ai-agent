import asyncio
import copy
from datetime import date
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from core.analytics.metric_mapping import build_metric_mapping_prompt, compile_inventory_query, decode_sql_turn
from core.analytics.metric_validation import MetricDefinitionError
from core.agents.execution import Execution, TaskOutcome
from core.agents.response import (_failure_answer, _month_over_month_sql_finding, _null_sql_findings,
                                  _scalar_sql_finding, assemble_response)
from core.agents.router import AgentRouter
from core.sql_agent.agent import SQLAnalyticsAgent, AnalyticsPermissionDenied
from core.models.agent_plan import AgentPlan, AgentTask
from core.models.agents import AgentRequest, AgentResult, Evidence, VerifiedIdentity, validate_chat_metadata

BASE = {'metrics':['stock_on_hand'],'dimensions':['category'],'time':{'mode':'snapshot','start':'2022-12-31'}}
STATE = {'accepted':BASE,'pending':None}
IDENTITY = VerifiedIdentity(subject='test',permissions={'analytics:read'})


class FailureMessageTest(unittest.TestCase):
    def test_failure_message_distinguishes_access_validation_and_safety(self):
        def outcome(error_type, detail=None):
            return SimpleNamespace(status='failed', error_type=error_type, error_detail=detail, result=None)

        question = 'xem doanh thu ở khu vực'
        self.assertIn('không có quyền', _failure_answer([outcome('AnalyticsPermissionDenied')], question))
        validation = _failure_answer(
            [outcome('SQLValidationError', 'JOIN does not match an approved relationship.')],
            'doanh thu theo khu vực')
        self.assertIn('không vượt qua kiểm tra SQL', validation)
        self.assertIn('JOIN does not match', validation)
        self.assertIn('an toàn SQL', _failure_answer([outcome('SQLSecurityError')], question))
        self.assertIn('hết thời gian', _failure_answer([outcome('TimeoutError')], question))


class SQLPatchTest(unittest.TestCase):
    def test_clear_segment_priority_followup_survives_malformed_model_interpretation(self):
        accepted = {
            'metrics': ['sell_through_rate', 'stockout_days'],
            'dimensions': ['segment'],
            'time': {'mode': 'snapshot', 'start': '2026-11-13'},
        }
        mapping, used = decode_sql_turn(
            'not valid SQLTurn JSON',
            'biết rồi nhưng nên đẩy mạnh segment nào nhỉ',
            {'accepted': accepted, 'pending': None},
        )

        self.assertTrue(used)
        self.assertEqual(mapping.metrics, accepted['metrics'])
        self.assertEqual(mapping.dimensions, ['segment'])
        self.assertEqual(mapping.time.start, '2026-11-13')
        self.assertEqual(mapping.ranking.metric, 'sell_through_rate')
        self.assertEqual(mapping.ranking.direction, 'desc')
        sql, parameters = compile_inventory_query(mapping)
        self.assertIn('ORDER BY AVG(commerce.inventory.sell_through_rate) DESC', sql)
        self.assertIn('2026-11-13', [str(value) for value in parameters])
        for context in (
            {'accepted': {**accepted, 'metrics': ['stockout_days']}, 'pending': None},
            {'accepted': accepted, 'pending': {'question': 'Which snapshot?', 'clarification': 'Choose a snapshot.'}},
        ):
            with self.subTest(context=context), self.assertRaises(MetricDefinitionError):
                decode_sql_turn('not valid SQLTurn JSON',
                                'biết rồi nhưng nên đẩy mạnh segment nào nhỉ', context)

    def test_segment_priority_followup_ranks_existing_sell_through_signal(self):
        accepted = {
            'metrics': ['sell_through_rate', 'stockout_days'],
            'dimensions': ['segment'],
            'time': {'mode': 'snapshot', 'start': '2026-11-13'},
        }
        state = {'accepted': accepted, 'pending': None}
        mapping, used = decode_sql_turn(json.dumps({
            'action': 'followup',
            'changes': {'ranking': {'metric': 'sell_through_rate', 'direction': 'desc'}},
        }), 'biết rồi nhưng nên đẩy mạnh segment nào', state)

        self.assertTrue(used)
        self.assertEqual(mapping.metrics, accepted['metrics'])
        self.assertEqual(mapping.dimensions, ['segment'])
        self.assertEqual(mapping.time.start, '2026-11-13')
        self.assertEqual(mapping.ranking.metric, 'sell_through_rate')
        prompt = build_metric_mapping_prompt('biết rồi nhưng nên đẩy mạnh segment nào', context=state)
        self.assertIn('sell_through_rate descending as a demand proxy', prompt)
        self.assertIn('Do not claim this proves revenue, margin or profit', prompt)

    def test_mixed_language_filter_patch_and_snapshot_refresh(self):
        mapping,used=self.decode({'action':'followup','changes':{'filters':[{'field':'color','operator':'eq','value':'blue'}]}},
                                 question='Chỉ lấy blue products thôi')
        self.assertTrue(used)
        refreshed,_=self.decode({'action':'followup','changes':{'time':{'mode':'latest'}}},
                                {'accepted':mapping.model_dump(),'pending':None},'Refresh to latest snapshot')
        self.assertEqual(refreshed.time.mode,'latest')
        self.assertEqual(refreshed.filters[0].value,'blue')

    def test_context_injection_is_rejected_at_client_boundary(self):
        with self.assertRaises(ValueError):validate_chat_metadata({'_sql_context':STATE})

    def decode(self,payload,state=None,question='Only blue products'):
        return decode_sql_turn(json.dumps(payload),question,state or STATE)

    def test_followup_merges_filters_and_ranking_without_dropping_scope(self):
        mapping,used=self.decode({'action':'followup','changes':{'filters':[{'field':'color','operator':'eq','value':'blue'}]}})
        self.assertTrue(used)
        self.assertEqual(mapping.time.start,'2022-12-31')
        mapping,used=self.decode({'action':'followup','changes':{'ranking':{'limit':3,'direction':'desc'}}},
                                 {'accepted':mapping.model_dump(),'pending':None},'Now show the top three categories')
        self.assertEqual(mapping.metrics,['stock_on_hand'])
        self.assertEqual(mapping.dimensions,['category'])
        self.assertEqual(mapping.filters[0].value,'blue')
        self.assertEqual(mapping.ranking.metric,'stock_on_hand')
        self.assertEqual(mapping.ranking.limit,3)

    def test_ranking_direction_followup_keeps_existing_secondary_order(self):
        accepted = {'metrics':['stockout_days','days_of_supply'],
                    'dimensions':['product_id','product_name'], 'representation':'product',
                    'time':{'mode':'snapshot','start':'2026-10-31'},
                    'ranking':{'metric':'stockout_days','direction':'desc','limit':None,
                               'then':[{'field':'days_of_supply','direction':'asc'}]}}
        mapping, used = decode_sql_turn(json.dumps({'action':'followup',
            'changes':{'ranking':{'direction':'asc'}}}), 'Reverse the primary ordering',
            {'accepted':accepted,'pending':None})
        self.assertTrue(used)
        self.assertEqual(mapping.ranking.direction,'asc')
        self.assertEqual([item.model_dump() for item in mapping.ranking.then],
                         [{'field':'days_of_supply','direction':'asc'}])

    def test_filter_replacement_removal_clear_and_ranking_removal(self):
        state=copy.deepcopy(STATE)
        state['accepted']['filters']=[{'field':'color','operator':'eq','value':'blue'},{'field':'size','operator':'eq','value':'M'}]
        state['accepted']['ranking']={'metric':'stock_on_hand','direction':'desc','limit':3}
        mapping,_=self.decode({'action':'followup','changes':{'filters':[{'field':'color','operator':'eq','value':'black'}],
                                                           'ranking':None}},state)
        self.assertEqual({f.field:f.value for f in mapping.filters},{'color':'black','size':'M'})
        self.assertIsNone(mapping.ranking)
        mapping,_=self.decode({'action':'followup','changes':{'remove_filters':['color']}},state)
        self.assertEqual([f.field for f in mapping.filters],['size'])
        mapping,_=self.decode({'action':'followup','changes':{'clear_filters':True}},state)
        self.assertEqual(mapping.filters,[])

    def test_fresh_question_has_no_inherited_filters_or_date(self):
        mapping,used=self.decode({'action':'new','mapping':{'metrics':['fill_rate'],'time':{'mode':'latest'}}},question='Average fill rate at latest snapshot')
        self.assertFalse(used)
        self.assertEqual(mapping.metrics,['fill_rate'])
        self.assertEqual(mapping.time.mode,'latest')
        self.assertEqual(mapping.filters,[])
        with self.assertRaises(MetricDefinitionError):
            self.decode({'action':'new','mapping':{'metrics':['stock_on_hand']}},question='Show stock by category')

    def test_missing_context_unknown_metric_and_ambiguous_ranking_fail_closed(self):
        for payload,state in [({'action':'followup','changes':{'ranking':{'limit':3}}},{'accepted':None,'pending':None}),
                              ({'action':'followup','changes':{'metrics':['reorder_quantity']}},STATE),
                              ({'action':'followup','changes':{'ranking':{'limit':3}}},
                               {'accepted':{**BASE,'metrics':['stock_on_hand','fill_rate']},'pending':None})]:
            with self.assertRaises(MetricDefinitionError):self.decode(payload,state)

    def test_pending_reply_resolves_original_question_without_reusing_old_scope(self):
        state={'accepted':BASE,'pending':{'question':'Show mean fill rate by category','clarification':'Which snapshot?'}}
        mapping,used=self.decode({'action':'answer','mapping':{'metrics':['fill_rate'],'dimensions':['category'],'time':{'mode':'latest'}}},state,'Latest available snapshot')
        self.assertEqual(mapping.metrics,['fill_rate'])
        self.assertTrue(used)
        with self.assertRaises(MetricDefinitionError):self.decode({'action':'followup','changes':{'ranking':{'limit':3}}},state)


class SQLConversationTest(unittest.IsolatedAsyncioTestCase):
    async def test_sql_debug_is_one_shot_and_auto_reuses_its_confirmed_scope(self):
        class Planner:
            def __init__(self): self.prompts=[]
            async def generate(self,prompt):
                self.prompts.append(prompt)
                if prompt.startswith('You plan'):
                    return json.dumps({'objective':'Compare stock with last year','tasks':[
                        {'id':'s','agent':'sql','question':'Compare stock with last year'}]})
                return json.dumps({'answer':'Stock comparison is supported [S1].','used_tasks':['s']})

        agent=Mock();seen=[]
        async def run(request):
            seen.append(request.metadata.get('_sql_context'))
            return AgentResult(answer='done [S1]',agent='analytics',
                evidence=[Evidence(citation_id='S1',source_type='database',source='commerce.inventory',content='stock')],
                data={'query_status':'executed','rows':[{'stock_on_hand':3}]},
                metadata={'ok':True,'semantic_interpretation':BASE})
        agent.run=run
        planner=Planner();router=AgentRouter(None,None,agent,llm=planner)

        await router.run_mode(self.request('Show stock at latest snapshot'),'sql')
        self.assertIsNone(seen[0])  # SQL mode never carries a prior SQL turn into the next debug query.

        await router.run_mode(self.request('Compare with last year'),'auto')
        self.assertEqual(seen[1]['accepted']['metrics'],BASE['metrics'])
        self.assertEqual(seen[1]['accepted']['time']['start'],BASE['time']['start'])
        self.assertIsNone(seen[1]['pending'])
        self.assertIn('Show stock at latest snapshot',planner.prompts[0])
        self.assertIn('"sql_context"',planner.prompts[0])
        self.assertNotIn('sql_conversations',vars(router))

    def request(self,question,subject='test',conversation='session',permissions=None):
        return AgentRequest(question=question,conversation_id=conversation,
                            identity=VerifiedIdentity(subject=subject,permissions=permissions or {'analytics:read'},document_roles={'admin'}))


class OriginalQuestionContextTest(unittest.IsolatedAsyncioTestCase):
    async def test_auto_returns_query_rows_without_extra_synthesis_when_metric_is_unverified(self):
        question = 'sản phẩm bán chạy nhất tháng trước'
        task = AgentTask(id='sql', agent='sql', question=question)
        plan = AgentPlan(objective=question, tasks=[task])
        result = AgentResult(answer='Query completed.', agent='sql_analytics',
            evidence=[Evidence(citation_id='S1', source_type='database', source='commerce.order_items')],
            data={'rows': [{'product_name': 'Grid Runner', 'total_quantity_sold': 152}]},
            metadata={'ok': True, 'metric_validation': {
                'status': 'unverified', 'code': 'incompatible_grain',
                'reason': 'No approved metric definition was found in Knowledge.',
            }})
        execution = SimpleNamespace(
            outcomes={'sql': TaskOutcome(task, 'complete', result)}, trace=[], invocations=1)

        class Provider:
            called = False

            async def generate(self, prompt, **_kwargs):
                self.called = True
                self.prompt = prompt
                return json.dumps({'answer':
                    'Theo truy vấn, Grid Runner có 152 đơn vị được ghi nhận [S1]; '
                    'định nghĩa metric bán chạy chưa được xác minh.', 'used_tasks': ['sql']})

        provider = Provider()
        answer = await assemble_response(
            AgentRequest(question=question, identity=IDENTITY), plan, execution, provider)

        self.assertFalse(provider.called)
        self.assertIn('| product_name | total_quantity_sold |', answer.answer)
        self.assertIn('Grid Runner', answer.answer)
        self.assertIn('chưa được xác minh', answer.answer)
        self.assertFalse(answer.metadata['fallback'])

    async def test_single_sql_task_synthesizes_the_structured_sql_result_in_auto(self):
        question = 'so sánh 2 năm 2026 với 2025'
        plan = AgentPlan(objective=question, tasks=[AgentTask(id='sql', agent='sql', question=question)])
        result = AgentResult(answer='Query completed.', agent='sql_analytics',
            evidence=[Evidence(citation_id='S1', source_type='database', source='commerce.sales')],
            data={'query_status':'executed','rows':[
                {'year': 2025, 'revenue': 3_369_646.71},
                {'year': 2026, 'revenue': 18_881_151.90},
            ]}, metadata={'ok':True})
        execution = SimpleNamespace(
            outcomes={'sql':TaskOutcome(plan.tasks[0], 'complete', result)}, trace=[], invocations=1)

        class Provider:
            called = False
            async def generate(self, prompt, **_kwargs):
                self.called = True
                self.prompt = prompt
                return json.dumps({'answer':
                    'Doanh thu năm 2025 là 3 369 646,71 và năm 2026 là 18 881 151,90 [S1].',
                    'used_tasks':['sql']})

        provider = Provider()
        answer = await assemble_response(AgentRequest(question=question, identity=IDENTITY), plan, execution, provider)

        self.assertTrue(provider.called)
        self.assertIn('so sánh 2 năm 2026 với 2025', provider.prompt)
        self.assertIn('Doanh thu năm 2025', answer.answer)
        self.assertFalse(answer.metadata['fallback'])

    async def test_auto_repairs_one_invalid_numeric_synthesis(self):
        question = 'so sánh doanh thu 2026 với 2025'
        task = AgentTask(id='sql', agent='sql', question=question)
        plan = AgentPlan(objective=question, tasks=[task])
        result = AgentResult(answer='Query completed.', agent='sql_analytics',
            evidence=[Evidence(citation_id='S1', source_type='database', source='commerce.sales')],
            data={'rows': [{'year': 2025, 'revenue': 100}, {'year': 2026, 'revenue': 200}]},
            metadata={'ok': True})
        execution = SimpleNamespace(
            outcomes={'sql': TaskOutcome(task, 'complete', result)}, trace=[], invocations=1)

        class Provider:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, **_kwargs):
                self.prompts.append(prompt)
                answer = ('Doanh thu năm 2026 tăng 150% [S1].' if len(self.prompts) == 1
                          else 'Doanh thu năm 2026 cao hơn năm 2025 [S1].')
                return json.dumps({'answer': answer, 'used_tasks': ['sql']})

        provider = Provider()
        answer = await assemble_response(
            AgentRequest(question=question, identity=IDENTITY), plan, execution, provider)

        self.assertEqual(len(provider.prompts), 2)
        self.assertIn('Correction:', provider.prompts[1])
        self.assertIn('cao hơn', answer.answer)
        self.assertFalse(answer.metadata['fallback'])

    async def test_codex_cli_synthesis_accepts_case_insensitive_citation_ids(self):
        question = 'Ứng viên sản phẩm theo doanh thu tùy chỉnh là gì?'
        task = AgentTask(id='sql', agent='sql', question=question)
        plan = AgentPlan(objective=question, tasks=[task])
        result = AgentResult(answer='Query completed.', agent='sql_analytics',
            evidence=[Evidence(citation_id='S1', source_type='database', source='commerce.order_items')],
            data={'rows': [{'product_id': 609, 'revenue_after_discount': '191848.89'}]},
            metadata={'ok': True, 'metric_validation': {'status': 'unverified'}})
        execution = SimpleNamespace(
            outcomes={'sql': TaskOutcome(task, 'complete', result)}, trace=[], invocations=1)
        with patch('core.agents.decision_support.response.generate_with_codex_cli', new=AsyncMock(
                return_value=json.dumps({'answer': 'Sản phẩm 609 có doanh thu 191848.89 [s1].',
                                         'used_tasks': ['sql']}))):
            answer = await assemble_response(
                AgentRequest(question=question, identity=IDENTITY), plan, execution, 'codex_cli')

        self.assertIn('[S1]', answer.answer)
        self.assertIn('191848.89', answer.answer)
        self.assertFalse(answer.metadata['fallback'])

    async def test_year_comparison_uses_grounded_answer_if_synthesis_stays_invalid(self):
        question = 'compare the revenue of 2025 and 2026'
        task = AgentTask(id='fallback', agent='sql', question=question)
        plan = AgentPlan(objective=question, tasks=[task])
        result = AgentResult(answer='Query completed.', agent='sql_analytics',
            evidence=[Evidence(citation_id='S1', source_type='database', source='commerce.sales')],
            data={'rows': [
                {'year': '2025', 'revenue': '3369646.71'},
                {'year': '2026', 'revenue': '18881151.90'},
            ]}, metadata={'ok': True})
        execution = SimpleNamespace(
            outcomes={'fallback': TaskOutcome(task, 'complete', result)}, trace=[], invocations=1)

        class Provider:
            async def generate(self, _prompt, **_kwargs):
                return 'not valid JSON'

        answer = await assemble_response(
            AgentRequest(question=question, identity=IDENTITY), plan, execution, Provider())

        self.assertIn('Revenue was higher in 2026', answer.answer)
        self.assertIn('18,881,151.90', answer.answer)
        self.assertIn('3,369,646.71', answer.answer)
        self.assertFalse(answer.metadata['fallback'])

    def test_null_fallback_recognizes_common_vietnamese_accent_in_followup(self):
        item = {'agent':'sql', 'data':{'rows':[{'revenue':None}]},
                'evidence':[{'citation_id':'S1'}]}
        answer = _null_sql_findings([item], '2023 thì sao')
        self.assertTrue(answer.startswith('Truy vấn đã chạy'))

    async def test_sql_task_keeps_root_question_for_relative_date_validation(self):
        question = 'Doanh thu tháng 3 năm nay là bao nhiêu?'
        request = AgentRequest(question=question, identity=IDENTITY)
        sql_agent = Mock()
        sql_agent.run = AsyncMock(return_value=AgentResult(
            answer='Query completed', agent='analytics',
            evidence=[Evidence(source_type='sql', source='commerce.sales')],
            data={'rows': [{'revenue': 1}]},
        ))
        plan = AgentPlan(objective='March revenue', tasks=[
            AgentTask(id='sql', agent='sql', question='Revenue in March')
        ])

        await Execution(request, {'sql': sql_agent}).run(plan)

        sql_request = sql_agent.run.await_args.args[0]
        self.assertEqual(sql_request.question, 'Revenue in March')
        self.assertEqual(sql_request.metadata['_original_question'], question)

    async def test_scalar_month_result_overrides_unsupported_model_period_claim(self):
        question = 'doanh thu tháng này sao'
        plan = AgentPlan(objective=question, tasks=[AgentTask(id='sql', agent='sql', question=question)])
        result = AgentResult(
            answer='The result has no date, so the month is unknown.', agent='analytics',
            evidence=[Evidence(citation_id='S1', source_type='database', source='commerce.sales')],
            data={'rows': [{'revenue': 1000968.55}],
                  'parameters': ['2026-11-01', '2026-12-01']},
            metadata={'ok': True},
        )
        execution = SimpleNamespace(
            outcomes={'sql': TaskOutcome(plan.tasks[0], 'complete', result)},
            trace=[], invocations=1,
        )

        answer = await assemble_response(
            AgentRequest(question=question, identity=IDENTITY), plan, execution, provider=None)

        self.assertEqual(answer.answer, 'Doanh thu tháng 11 năm 2026: 1,000,968.55 [S1].')

    def test_scalar_fallback_formats_value_and_uses_bound_year(self):
        item = {
            'agent': 'sql',
            'data': {'rows': [{'revenue': 2248522.83}],
                     'parameters': ['2025-01-01', '2026-01-01']},
            'evidence': [{'citation_id': 'S1'}],
        }
        self.assertEqual(
            _scalar_sql_finding(item, 'doanh thu năm 2025'),
            'Doanh thu năm 2025: 2,248,522.83 [S1].',
        )

    async def test_month_over_month_result_is_summarized_in_auto_answer(self):
        question = 'so sánh với tháng trước'
        plan = AgentPlan(objective=question, tasks=[AgentTask(id='sql', agent='sql', question='Compare current revenue with previous month')])
        row = {'month': '2026-11-01', 'previous_month': '2026-10-01', 'revenue': '1000968.55',
               'previous_month_revenue': '1754342.36', 'revenue_change': '-753373.81',
               'revenue_change_fraction': '-0.42943374518984994468'}
        result = AgentResult(answer='Evidence fallback', agent='analytics',
            evidence=[Evidence(citation_id='S1', source_type='database', source='commerce.sales')],
            data={'rows': [row]}, metadata={'ok': True})
        execution = SimpleNamespace(
            outcomes={'sql': TaskOutcome(plan.tasks[0], 'complete', result)}, trace=[], invocations=1)

        answer = await assemble_response(AgentRequest(question=question, identity=IDENTITY), plan, execution, provider=None)

        self.assertEqual(answer.answer,
            'Doanh thu tháng 11 năm 2026: 1,000,968.55; tháng 10 năm 2026: 1,754,342.36, giảm 753,373.81 so với tháng trước [S1].')

    def test_scalar_fallback_formats_value_and_uses_bound_month(self):
        item = {
            'agent': 'sql',
            'data': {'rows': [{'revenue': 2248522.83}],
                     'parameters': ['2026-03-01', '2026-04-01']},
            'evidence': [{'citation_id': 'S1'}],
        }
        self.assertEqual(
            _scalar_sql_finding(item, 'doanh thu tháng 3'),
            'Doanh thu tháng 3 năm 2026: 2,248,522.83 [S1].',
        )

    def test_scalar_fallback_uses_month_returned_by_query(self):
        item = {
            'agent': 'sql',
            'data': {'rows': [{'month': '2026-03-01T00:00:00Z', 'revenue': 2248522.83}]},
            'evidence': [{'citation_id': 'S1'}],
        }
        self.assertEqual(
            _scalar_sql_finding(item, 'doanh thu của tháng nào cao nhất để đưa ra chiến lược'),
            'Doanh thu tháng 3 năm 2026: 2,248,522.83 [S1].',
        )


class ResponseSynthesisBudgetTest(unittest.IsolatedAsyncioTestCase):
    async def test_sql_evidence_fallback_formats_rows_as_markdown_table(self):
        question = 'Trong năm 2026, danh mục nào có doanh thu cao nhất?'
        task = AgentTask(id='s', agent='sql', question=question)
        plan = AgentPlan(objective=question, tasks=[task])
        rows = [{'category': 'Streetwear', 'total_quantity_sold': 1557,
                 'revenue_after_discount': '12829075.42'},
                {'category': 'Outdoor', 'total_quantity_sold': 2685,
                 'revenue_after_discount': '4991227.46'}]
        result = AgentResult(answer='Query completed.', agent='analytics',
            evidence=[Evidence(citation_id='S1', source_type='database', source='commerce.sales')],
            data={'rows': rows, 'query_status': 'executed'}, metadata={'ok': True})
        execution = SimpleNamespace(
            outcomes={'s': TaskOutcome(task, 'complete', result)}, trace=[], invocations=1)

        with patch('core.agents.response.generate', new=AsyncMock(side_effect=TimeoutError)):
            response = await assemble_response(
                AgentRequest(question=question, identity=IDENTITY), plan, execution, provider=object())

        self.assertIn('| category | total_quantity_sold | revenue_after_discount |', response.answer)
        self.assertIn('| Streetwear | 1557 | 12829075.42 |', response.answer)
        self.assertIn('SQL findings [S1]:', response.answer)
        self.assertNotIn('[{"category"', response.answer)
        self.assertTrue(response.metadata['fallback'])

    async def test_large_sql_results_are_compacted_only_for_synthesis(self):
        question = 'Which products have the most stockout days at the latest snapshot?'
        task = AgentTask(id='s', agent='sql', question=question)
        plan = AgentPlan(objective=question, tasks=[task])
        rows = [{'snapshot_date':'2026-10-31','product_id':i+1,'product_name':f'Product-{i}',
                 'stock_on_hand':i,'inventory_units_sold':i+2,'stockout_days':20-i%20,
                 'days_of_supply':f'{i}.00','stockout_indicator':True,'overstock_indicator':False,
                 'reorder_indicator':False} for i in range(97)]
        result = AgentResult(answer='Query completed.', agent='analytics',
            evidence=[Evidence(citation_id='S1', source_type='database', source='commerce.inventory',
                               metadata={'metrics':{'stock_on_hand':{'definition':'m'*40_000}}})],
            data={'rows':rows,'sql':'SELECT '+('x'*2000),'parameters':[],'query_status':'executed'},
            metadata={'ok':True})
        execution = SimpleNamespace(outcomes={'s':TaskOutcome(task,'complete',result)},trace=[],invocations=1)
        provider = Mock()
        provider.generate.return_value = json.dumps({
            'answer':'Product-0 is listed first with 20 recorded stockout days [S1].',
            'used_tasks':['s'],
        })

        response = await assemble_response(AgentRequest(question=question,identity=IDENTITY),plan,execution,provider)

        self.assertFalse(response.metadata['fallback'])
        self.assertEqual(len(response.data['sql']['rows']),97)
        prompt = provider.generate.call_args.args[0]
        self.assertIn('"rows_truncated": true',prompt)
        self.assertIn('Product-19',prompt)
        self.assertNotIn('Product-20',prompt)
        self.assertIn('commerce.inventory',prompt)
        self.assertNotIn('m'*100,prompt)
        self.assertNotIn('x'*2000,prompt)
