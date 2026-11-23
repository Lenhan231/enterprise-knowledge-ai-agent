import copy
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))

from core.agents.sql.metric_mapping import build_metric_mapping_prompt, decode_metric_mapping, validate_mapped_sql
from core.agents.sql.metric_validation import MetricDefinitionError
from core.agents.sql.text_to_sql import decode_query_plan


MAPPING = {'domain':'inventory','metrics':['stock_on_hand'],'dimensions':['product_name'],
           'representation':'product','time':{'mode':'latest'},
           'filters':[{'field':'color','operator':'eq','value':'blue'}],
           'ranking':{'metric':'stock_on_hand','direction':'asc','limit':10}}
SQL = ('SELECT i.snapshot_date,p.product_name,i.stock_on_hand FROM commerce.inventory AS i '
       'JOIN commerce.products AS p ON i.product_id=p.product_id '
       'WHERE i.snapshot_date=(SELECT MAX(j.snapshot_date) FROM commerce.inventory AS j) '
       'AND p.color=$1 ORDER BY 3 ASC LIMIT 10')


class MetricMappingTest(unittest.TestCase):
    def decode(self, payload=None, question='Which top 10 blue styles have the fewest pieces left at the latest recorded observation?'):
        return decode_metric_mapping(json.dumps(payload or MAPPING),question)

    def test_unseen_wording_maps_to_catalog_ids_and_sql_constraints(self):
        mapping=self.decode()
        validate_mapped_sql(decode_query_plan(json.dumps({'sql':SQL,'parameters':['blue']})),mapping)

    def test_approved_product_key_join_preserves_product_identity(self):
        payload=copy.deepcopy(MAPPING);payload['dimensions'].append('product_id')
        sql=SQL.replace('p.product_name,','p.product_id,p.product_name,').replace('ORDER BY 3','ORDER BY 4')
        validate_mapped_sql(decode_query_plan(json.dumps({'sql':sql,'parameters':['blue']})),self.decode(payload))

    def test_generation_prompt_makes_stored_projection_explicit(self):
        from core.agents.sql.text_to_sql import build_sql_prompt
        prompt=build_sql_prompt('Fewest pieces left',metric_names={'stock_on_hand'},interpretation=MAPPING)
        self.assertIn('Do not aggregate or GROUP BY',prompt)
        self.assertIn('Stored projection fields',prompt)

    def test_clarifications_follow_the_question_language(self):
        prompt=build_metric_mapping_prompt('so sánh với năm ngoái')
        self.assertIn('ask a specific clarification in the same language as the user question',prompt)

    def test_mapping_prompt_lists_stored_field_aliases_with_catalog_ids(self):
        prompt=build_metric_mapping_prompt('Show stockout_flag for each product')
        candidates=json.loads(prompt.split('Catalog candidates (selection summaries only): ',1)[1].split('\n',1)[0])
        self.assertIn('stockout_flag',candidates['stockout_indicator']['source_fields'])
        self.assertIn('stockout flag',candidates['stockout_indicator']['aliases'])
        self.assertIn('not an unknown metric ID',prompt)

    def test_unknown_metric_dimension_and_filters_are_rejected(self):
        for field,value in [('metrics',['predicted_stock']),('dimensions',['region']),
                            ('filters',[{'field':'customer_id','operator':'eq','value':1}])]:
            bad=copy.deepcopy(MAPPING);bad[field]=value
            with self.subTest(field=field),self.assertRaises(MetricDefinitionError):self.decode(bad)

    def test_filter_values_match_source_types(self):
        for field,value in [('color',12),('product_id','12'),('stock_on_hand',True),('stockout_indicator','true')]:
            bad=copy.deepcopy(MAPPING);bad['filters']=[{'field':field,'operator':'eq','value':value}]
            with self.subTest(field=field),self.assertRaises(MetricDefinitionError):self.decode(bad)

    def test_unresolved_or_dropped_known_metric_cannot_be_approved_by_model(self):
        bad=copy.deepcopy(MAPPING);bad['metrics']=['reorder_quantity'];bad['ranking']=None
        with self.assertRaises(MetricDefinitionError):self.decode(bad)
        with self.assertRaises(MetricDefinitionError):self.decode(question='What safety stock should I hold at latest snapshot?')

    def test_missing_snapshot_and_ambiguous_meaning_clarify(self):
        bad=copy.deepcopy(MAPPING);bad.pop('time')
        with self.assertRaises(MetricDefinitionError):self.decode(bad)
        with self.assertRaises(MetricDefinitionError) as error:
            self.decode({'clarification':'Does low mean bottom-ranked or below a specified quantity?'})
        self.assertTrue(error.exception.clarification)

    def test_mapping_output_cannot_contain_sql_or_formulas(self):
        for extra in ('sql','formula'):
            with self.assertRaises(MetricDefinitionError):self.decode({**MAPPING,extra:'DROP TABLE commerce.inventory'})
        from core.agents.sql.text_to_sql import SQLValidationError
        with self.assertRaises(SQLValidationError):
            decode_query_plan(json.dumps({'sql':"SELECT i.product_id FROM commerce.inventory AS i WHERE i.product_id IN ($1,$2) LIMIT 200",'parameters':[1]}))

    def test_single_json_fence_does_not_bypass_validation(self):
        from core.agents.sql.text_to_sql import SQLValidationError
        raw=json.dumps({'sql':SQL,'parameters':['blue']})
        self.assertEqual(decode_query_plan('```json\n'+raw+'\n```').sql,SQL)
        self.assertEqual(decode_metric_mapping('```json\n'+json.dumps(MAPPING)+'\n```','Fewest pieces at latest observation').metrics,['stock_on_hand'])
        for raw in ('```json\n{"sql":"DELETE FROM commerce.inventory"}\n```',
                    '```json\n{}\n{}\n```'):
            with self.assertRaises(SQLValidationError):decode_query_plan(raw)
        with self.assertRaises(MetricDefinitionError):
            decode_metric_mapping('```json\n'+json.dumps({**MAPPING,'sql':'SELECT 1'})+'\n```','Fewest pieces at latest observation')

    def test_monthly_inventory_totals_are_separate_snapshot_groups(self):
        question = 'Trong từng tháng của năm 2026, 3 danh mục có tổng số ngày hết hàng cao nhất là gì?'
        payload = {'metrics':['stockout_days'], 'dimensions':['category'], 'representation':'aggregate',
                   'time':{'mode':'range','start':'2026-01-01','end':'2026-12-31'},
                   'ranking':{'metric':'stockout_days','direction':'desc','limit':3}}
        mapping = decode_metric_mapping(json.dumps(payload), question)
        self.assertEqual(mapping.time.mode, 'range')
        self.assertEqual(mapping.dimensions, ['category'])
        self.assertEqual(mapping.ranking.limit, 3)
        from core.agents.sql.text_to_sql import build_sql_prompt
        self.assertIn('rank independently inside each month',
                      build_sql_prompt(question, metric_names={'stockout_days'}))

    def test_inventory_rankings_preserve_requested_secondary_sort_keys(self):
        from core.agents.sql.metric_mapping import compile_inventory_query
        question = ('Với snapshot tồn kho ngày 2026-10-31, sản phẩm nào cần ưu tiên rà soát nguy cơ thiếu hàng? '
                    'Xếp theo stockout_days giảm dần, rồi days_of_supply tăng dần; hiển thị tồn kho, lượng bán '
                    'và các cờ tồn kho.')
        payload = {'metrics':['stockout_days','days_of_supply','stock_on_hand','inventory_units_sold',
                              'stockout_indicator','overstock_indicator','reorder_indicator'],
                   'dimensions':['product_id','product_name'], 'representation':'product',
                   'time':{'mode':'snapshot','start':'2026-10-31'},
                   'ranking':{'metric':'stockout_days','direction':'desc','limit':200,
                              'then':[{'field':'days_of_supply','direction':'asc'}]}}
        mapping = decode_metric_mapping(json.dumps(payload), question)
        sql, parameters = compile_inventory_query(mapping)
        self.assertLess(sql.index('stockout_days DESC'), sql.index('days_of_supply ASC'))
        encoded = json.dumps({'sql':sql,'parameters':parameters}, default=str)
        validate_mapped_sql(decode_query_plan(encoded), mapping, question=question)
        with self.assertRaises(MetricDefinitionError):
            validate_mapped_sql(decode_query_plan(json.dumps({
                'sql':sql.replace('days_of_supply ASC','days_of_supply DESC'), 'parameters':parameters}, default=str)),
                mapping, question=question)

    def test_dates_and_domain_cannot_bypass_inventory_rules(self):
        with self.assertRaises(MetricDefinitionError):self.decode({'domain':'other'},question='Stock on hand latest snapshot')
        with self.assertRaises(MetricDefinitionError):self.decode(question='Stock on hand latest snapshot in 2022')
        bad=copy.deepcopy(MAPPING);bad['time']={'mode':'range','start':'2022-12-31','end':'2022-01-01'}
        with self.assertRaises(MetricDefinitionError):self.decode(bad)
        plan=decode_query_plan(json.dumps({'sql':SQL,'parameters':['blue']}))
        with self.assertRaises(MetricDefinitionError):validate_mapped_sql(plan,self.decode({'domain':'other'},question='List products'))

    def test_inventory_context_does_not_force_stock_when_vietnamese_metric_is_paraphrased(self):
        payload={'metrics':['stored_fill_rate'],'dimensions':['product_name'],'representation':'product','time':{'mode':'latest'}}
        mapping=self.decode(payload,question='Cho xem mức đáp ứng từng mã hàng trong tồn kho mới nhất')
        self.assertEqual(mapping.metrics,['stored_fill_rate'])

    def test_range_and_in_filters_use_native_parameters(self):
        payload={'metrics':['stock_on_hand'],'dimensions':['category'],'time':{'mode':'range','start':'2022-01-01','end':'2022-12-31'},
                 'filters':[{'field':'color','operator':'in','value':['blue','black']}]}
        sql=('SELECT i.snapshot_date,p.category,SUM(i.stock_on_hand) FROM commerce.inventory AS i '
             'JOIN commerce.products AS p ON i.product_id=p.product_id '
             'WHERE i.snapshot_date >= $1 AND i.snapshot_date < $2 AND p.color IN ($3, $4) '
             'GROUP BY i.snapshot_date,p.category LIMIT 200')
        plan=decode_query_plan(json.dumps({'sql':sql,'parameters':['2022-01-01','2023-01-01','blue','black']}))
        validate_mapped_sql(plan,self.decode(payload,question='Stock on hand by category during 2022 for blue or black products'))

    def test_sql_must_keep_filter_dimension_ranking_limit_and_time(self):
        mapping=self.decode()
        for sql,parameters in [(SQL.replace('AND p.color=$1',''),[]),
                               (SQL,['red']), (SQL.replace('ORDER BY 3 ASC','ORDER BY 3 DESC'),['blue']),
                               (SQL.replace('LIMIT 10','LIMIT 5'),['blue']),
                               (SQL.replace('p.product_name,','').replace('ORDER BY 3 ASC','ORDER BY 2 ASC'),['blue']),
                               (SQL.replace('(SELECT MAX(j.snapshot_date) FROM commerce.inventory AS j)',"'2020-12-31'"),['blue']),
                               (SQL.replace('ORDER BY 3 ASC','ORDER BY 2 ASC'),['blue'])]:
            with self.subTest(sql=sql,parameters=parameters),self.assertRaises(MetricDefinitionError):
                validate_mapped_sql(decode_query_plan(json.dumps({'sql':sql,'parameters':parameters})),mapping)


class MappingAgentTest(unittest.IsolatedAsyncioTestCase):
    def test_relative_last_month_is_resolved_to_previous_month_snapshot(self):
        from core.agents.sql.metric_mapping import compile_inventory_query
        from core.agents.sql.metric_validation import inventory_time_scope
        question = 'sản phẩm bán chạy nhất tháng trước'
        today = date.today()
        last_month_end = (date(today.year, today.month, 1) - timedelta(days=1)).isoformat()
        self.assertEqual(inventory_time_scope(question, today=today), ('snapshot', last_month_end, None))
        payload = {
            'domain': 'inventory', 'metrics': ['inventory_units_sold'],
            'dimensions': ['product_id', 'product_name'], 'representation': 'product',
            'time': {'mode': 'latest'},
            'filters': [{'field': 'snapshot_date', 'operator': 'eq', 'value': last_month_end}],
            'ranking': {'metric': 'inventory_units_sold', 'direction': 'desc', 'limit': None},
        }
        mapping = decode_metric_mapping(json.dumps(payload), question)
        self.assertEqual(mapping.time.model_dump(), {
            'mode': 'snapshot', 'start': last_month_end, 'end': None})
        self.assertEqual(mapping.filters, [])
        sql, parameters = compile_inventory_query(mapping)
        self.assertIn('snapshot_date = $1', sql)
        self.assertEqual(parameters, (date.fromisoformat(last_month_end),))

    async def test_permission_is_checked_before_mapping(self):
        from core.agents.sql.agent import SQLAnalyticsAgent,AnalyticsPermissionDenied
        from core.models.agents import AgentRequest
        provider,repository=Mock(),AsyncMock()
        with self.assertRaises(AnalyticsPermissionDenied):
            await SQLAnalyticsAgent(repository,llm=provider).run(AgentRequest(question='Which styles need attention?'))
        provider.generate.assert_not_called()
        repository.execute_approved_query.assert_not_awaited()

    async def test_compiler_contract_violation_never_reaches_repository(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest,VerifiedIdentity
        provider,repository=Mock(),AsyncMock()
        question = 'Which blue styles have the fewest pieces left at latest snapshot?'
        intent = {'intent': {
            'original_question': question, 'operation': 'rank', 'metrics': ['stock_on_hand'],
            'unverified_metric_request': None, 'dimensions': ['product_id', 'product_name'],
            'filters': [{'field': 'commerce.products.color', 'operator': 'eq', 'value': 'blue'}],
            'time_scope': {'mode': 'latest', 'ranges': []},
            'requested_sources': [
                {'name': 'commerce.inventory', 'provenance': 'ontology_required'},
                {'name': 'commerce.products', 'provenance': 'ontology_required'}],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None,
            'ranking': {'metric': 'stock_on_hand', 'direction': 'asc', 'limit': None},
            'unresolved_slots': [],
        }}
        with patch('core.agents.sql.intent_resolution.generate',
                   new=AsyncMock(return_value=json.dumps(intent))) as interpret, \
                patch('core.agents.sql.agent.compile_inventory_query',
                      return_value=(SQL.replace('AND p.color=$1',''), ())):
            result=await SQLAnalyticsAgent(repository,llm=provider).run(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertFalse(result.metadata['ok'])
        self.assertEqual(result.metadata['metric_error_code'],'interpretation_mismatch')
        interpret.assert_awaited_once()
        provider.generate.assert_not_called()
        repository.execute_approved_query.assert_not_awaited()

    async def test_mapping_compiles_for_mixed_language_request(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest,VerifiedIdentity
        provider,repository=Mock(),AsyncMock()
        question='Top 10 styles màu blue còn ít pieces nhất ở kỳ ghi nhận mới nhất?'
        intent={'intent':{
            'original_question':question,'operation':'rank','metrics':['stock_on_hand'],
            'unverified_metric_request':None,'dimensions':['product_name'],
            'filters':[{'field':'commerce.products.color','operator':'eq','value':'blue'}],
            'time_scope':{'mode':'latest','ranges':[]},
            'requested_sources':[{'name':'commerce.inventory','provenance':'ontology_required'},
                                 {'name':'commerce.products','provenance':'ontology_required'}],
            'explicit_source_restriction':False,'geographic_basis':None,'geographic_coverage':None,
            'ranking':{'metric':'stock_on_hand','direction':'asc','limit':10},'unresolved_slots':[]}}
        repository.execute_approved_query.return_value=[{'snapshot_date':'2022-12-31','product_name':'A','stock_on_hand':3}]
        with patch('core.agents.sql.intent_resolution.generate',
                   new=AsyncMock(return_value=json.dumps(intent))) as interpret:
            result=await SQLAnalyticsAgent(repository,llm=provider).run(AgentRequest(
                question=question, identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertTrue(result.metadata['ok'],result.answer)
        self.assertIn('semantic_interpretation',result.metadata)
        interpret.assert_awaited_once()
        provider.generate.assert_not_called()
        repository.execute_approved_query.assert_awaited_once()

    async def test_invalid_general_intent_falls_back_to_sql_clarification(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest,VerifiedIdentity
        provider,repository=Mock(),AsyncMock()
        from core.agents.sql.text_to_sql import APPROVED_COLUMNS
        agent=SQLAnalyticsAgent(repository,llm=provider)
        agent._generate_sql=AsyncMock(return_value=json.dumps(
            {'clarification':'Which inventory measure and snapshot do you mean?'}))
        selection={'tables':set(APPROVED_COLUMNS),'required_tables':set(),
                   'candidate_tables':set(APPROVED_COLUMNS)}
        with patch('core.agents.sql.agent.interpret_query_intent',
                   new=AsyncMock(side_effect=ValueError('invalid intent response'))), \
             patch('core.agents.sql.agent.asyncio.to_thread',
                   new=AsyncMock(return_value=selection)):
            result=await agent.run(AgentRequest(
                question='Which styles need attention?',identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertEqual(result.answer,'Which inventory measure and snapshot do you mean?')
        agent._generate_sql.assert_awaited_once()
        repository.execute_approved_query.assert_not_awaited()

    async def test_metric_formula_mismatch_runs_safe_sql_as_unverified(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest,VerifiedIdentity
        provider,repository=Mock(),AsyncMock()
        sql=('SELECT p.category AS category, AVG(i.stock_on_hand) AS average_stock '
             'FROM commerce.inventory AS i JOIN commerce.products AS p ON p.product_id=i.product_id '
             'WHERE i.snapshot_date=(SELECT MAX(j.snapshot_date) FROM commerce.inventory AS j) '
             'GROUP BY 1 ORDER BY 1 LIMIT 200')
        provider.generate.side_effect=[
            json.dumps({'clarification':'Specify a product-level representation.'}),
            json.dumps({'sql':sql,'parameters':[]}),
            json.dumps({'sql':sql,'parameters':[]}),
        ]
        repository.execute_approved_query.return_value=[{'category':'Outerwear','average_stock':12.5}]
        result=await SQLAnalyticsAgent(repository,llm=provider).run(AgentRequest(
            question='What is average stock_on_hand by category at the latest snapshot?',
            identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))

        self.assertTrue(result.metadata['ok'],result.answer)
        self.assertEqual(result.metadata['metric_validation']['status'],'unverified')
        self.assertEqual(provider.generate.call_count,3)
        repository.execute_approved_query.assert_awaited_once_with(sql)
