import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))

from core.analytics.metric_mapping import decode_metric_mapping, validate_mapped_sql
from core.analytics.metric_validation import MetricDefinitionError
from core.analytics.text_to_sql import decode_query_plan


MAPPING = {'domain':'inventory','metrics':['stock_on_hand'],'dimensions':['product_name'],
           'representation':'product','time':{'mode':'latest'},
           'filters':[{'field':'color','operator':'eq','value':'blue'}],
           'ranking':{'metric':'stock_on_hand','direction':'asc','limit':10}}
SQL = ('SELECT i.snapshot_date,p.product_name,i.stock_on_hand FROM commerce.inventory AS i '
       'JOIN commerce.products AS p ON i.product_id=p.product_id '
       'WHERE i.snapshot_date=(SELECT MAX(j.snapshot_date) FROM commerce.inventory AS j) '
       'AND p.color=$1 ORDER BY 3 ASC LIMIT 10')


class MetricMappingTest(unittest.TestCase):
    def decode(self, payload=None, question='Which blue styles have the fewest pieces left at the latest recorded observation?'):
        return decode_metric_mapping(json.dumps(payload or MAPPING),question)

    def test_unseen_wording_maps_to_catalog_ids_and_sql_constraints(self):
        mapping=self.decode()
        validate_mapped_sql(decode_query_plan(json.dumps({'sql':SQL,'parameters':['blue']})),mapping)

    def test_unknown_metric_dimension_and_filters_are_rejected(self):
        for field,value in [('metrics',['predicted_stock']),('dimensions',['region']),
                            ('filters',[{'field':'customer_id','operator':'eq','value':1}])]:
            bad=copy.deepcopy(MAPPING);bad[field]=value
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
        from core.analytics.text_to_sql import SQLValidationError
        with self.assertRaises(SQLValidationError):
            decode_query_plan(json.dumps({'sql':"SELECT i.product_id FROM commerce.inventory AS i WHERE i.product_id IN ($1,$2) LIMIT 200",'parameters':[1,2]}))

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
        validate_mapped_sql(plan,self.decode(payload))

    def test_sql_must_keep_filter_dimension_ranking_limit_and_time(self):
        mapping=self.decode()
        for sql,parameters in [(SQL.replace('AND p.color=$1',''),[]),
                               (SQL,['red']), (SQL.replace('ORDER BY 3 ASC','ORDER BY 3 DESC'),['blue']),
                               (SQL.replace('LIMIT 10','LIMIT 5'),['blue']),
                               (SQL.replace('p.product_name,',''),['blue']),
                               (SQL.replace('(SELECT MAX(j.snapshot_date) FROM commerce.inventory AS j)',"'2020-12-31'"),['blue'])]:
            with self.subTest(sql=sql,parameters=parameters),self.assertRaises(MetricDefinitionError):
                validate_mapped_sql(decode_query_plan(json.dumps({'sql':sql,'parameters':parameters})),mapping)


class MappingAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_permission_is_checked_before_mapping(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent,AnalyticsPermissionDenied
        from core.models.agents import AgentRequest
        provider,repository=Mock(),AsyncMock()
        with self.assertRaises(AnalyticsPermissionDenied):
            await SQLAnalyticsAgent(repository,llm=provider).run(AgentRequest(question='Which styles need attention?'))
        provider.generate.assert_not_called()
        repository.execute_approved_query.assert_not_awaited()

    async def test_repeated_contract_violation_never_reaches_repository(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest,VerifiedIdentity
        provider,repository=Mock(),AsyncMock()
        bad=json.dumps({'sql':SQL.replace('AND p.color=$1',''),'parameters':[]})
        provider.generate.side_effect=[json.dumps(MAPPING),bad,bad]
        result=await SQLAnalyticsAgent(repository,llm=provider).run(AgentRequest(
            question='Which blue styles have the fewest pieces left at latest snapshot?',
            identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertFalse(result.metadata['ok'])
        self.assertEqual(result.metadata['metric_error_code'],'interpretation_mismatch')
        self.assertEqual(provider.generate.call_count,3)
        repository.execute_approved_query.assert_not_awaited()

    async def test_mapping_precedes_sql_for_mixed_language_request(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest,VerifiedIdentity
        provider,repository=Mock(),AsyncMock()
        provider.generate.side_effect=[json.dumps(MAPPING),json.dumps({'sql':SQL,'parameters':['blue']})]
        repository.execute_approved_query.return_value=[{'snapshot_date':'2022-12-31','product_name':'A','stock_on_hand':3}]
        result=await SQLAnalyticsAgent(repository,llm=provider).run(AgentRequest(
            question='Top 10 styles màu blue còn ít pieces nhất ở kỳ ghi nhận mới nhất?',
            identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertTrue(result.metadata['ok'],result.answer)
        self.assertIn('semantic_interpretation',result.metadata)
        self.assertEqual(provider.generate.call_count,2)
        repository.execute_approved_query.assert_awaited_once()

    async def test_bad_interpretation_stops_before_sql_and_execution(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest,VerifiedIdentity
        provider,repository=Mock(),AsyncMock()
        provider.generate.return_value=json.dumps({'clarification':'Which snapshot and low-stock threshold do you mean?'})
        result=await SQLAnalyticsAgent(repository,llm=provider).run(AgentRequest(
            question='Which styles need attention?',identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertTrue(result.metadata['clarification_required'])
        self.assertEqual(provider.generate.call_count,1)
        repository.execute_approved_query.assert_not_awaited()
