import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.analytics.metric_mapping import decode_metric_mapping
from core.analytics.metric_validation import MetricDefinitionError, validate_metric_definitions
from core.analytics.text_to_sql import APPROVED_COLUMNS, SQLValidationError, decode_query_plan, validate_commerce_sql


class TemporalContractTest(unittest.TestCase):
    def mapping(self, time, question, metrics=None, **slots):
        return decode_metric_mapping(json.dumps({'metrics': metrics or ['stock_on_hand'],
            'time': time, **slots}), question)

    def test_redundant_snapshot_end_has_identical_meaning(self):
        mapping = self.mapping({'mode': 'snapshot', 'start': '2022-12-31', 'end': '2022-12-31'},
                               'Stock on hand on 2022-12-31')
        self.assertIsNone(mapping.time.end)

    def test_month_quarter_year_are_explicit_ranges_not_closing_balances(self):
        for phrase, start, end in [('December 2022', '2022-12-01', '2022-12-31'),
                                   ('tháng 12 năm 2022', '2022-12-01', '2022-12-31'),
                                   ('Q4 2022', '2022-10-01', '2022-12-31'),
                                   ('quý 4 năm 2022', '2022-10-01', '2022-12-31'),
                                   ('2022', '2022-01-01', '2022-12-31')]:
            with self.subTest(phrase=phrase):
                mapping = self.mapping({'mode': 'range', 'start': start, 'end': end},
                                       'Stock on hand observations in ' + phrase)
                self.assertEqual(mapping.time.start, start)
                with self.assertRaises(MetricDefinitionError):
                    self.mapping({'mode': 'snapshot', 'start': end}, 'Stock on hand in ' + phrase)

    def test_wrong_date_relative_time_and_unresolved_metric_still_rejected(self):
        for question, temporal, metrics in [
            ('Stock on hand on 2022-12-31', {'mode':'snapshot','start':'2022-11-30'}, None),
            ('Stock on hand last month', {'mode':'range','start':'2022-12-01','end':'2022-12-31'}, None),
            ('Safety stock at latest snapshot', {'mode':'latest'}, ['stock_on_hand']),
        ]:
            with self.subTest(question=question), self.assertRaises(MetricDefinitionError):
                self.mapping(temporal, question, metrics)

    def test_equivalent_date_cast_and_inclusive_bounds(self):
        sql = ('SELECT i.snapshot_date, AVG(i.fill_rate) AS fill_rate FROM commerce.inventory i '
               "WHERE i.snapshot_date >= CAST('2022-12-01' AS DATE) AND i.snapshot_date <= CAST('2022-12-31' AS DATE) "
               'GROUP BY i.snapshot_date LIMIT 200')
        validate_metric_definitions(sql, {'fill_rate'}, (), APPROVED_COLUMNS,
                                    question='Average fill rate in December 2022')

    def test_product_period_rows_keep_snapshot_identity_without_grouping_measures(self):
        from core.analytics.metric_mapping import compile_inventory_query
        mapping = self.mapping({'mode':'range','start':'2022-12-01','end':'2022-12-31'},
            'Highest stockout days in December 2022', ['stockout_days'],
            dimensions=['product_id'], representation='product',
            ranking={'metric':'stockout_days','direction':'desc','limit':200})
        sql, parameters = compile_inventory_query(mapping)
        self.assertNotIn('GROUP BY', sql)
        self.assertIn('snapshot_date', sql)
        self.assertEqual(parameters, (date(2022,12,1), date(2023,1,1)))


class SafeJoinPredicateTest(unittest.TestCase):
    def test_snapshot_anti_join_uses_approved_key_and_parameter_date(self):
        sql = ('SELECT p.product_id FROM commerce.products p LEFT JOIN commerce.inventory i '
               'ON p.product_id=i.product_id AND i.snapshot_date=$1 '
               'WHERE i.product_id IS NULL ORDER BY 1 LIMIT 200')
        plan = decode_query_plan(json.dumps({'sql':sql, 'parameters':['2022-12-31']}))
        self.assertEqual(plan.parameters, (date(2022,12,31),))

    def test_side_predicate_cannot_replace_key_or_add_unapproved_relationship(self):
        for condition in ['i.snapshot_date=$1', 'p.product_id=i.stock_on_hand',
                          'p.product_id=i.product_id OR i.snapshot_date=$1',
                          'p.product_id=i.product_id AND p.price=i.stock_on_hand']:
            with self.subTest(condition=condition), self.assertRaises(SQLValidationError):
                validate_commerce_sql('SELECT p.product_id FROM commerce.products p LEFT JOIN commerce.inventory i ON '
                                      + condition + ' LIMIT 200')

    def test_structural_inventory_queries_do_not_require_business_kpi(self):
        from core.analytics.metric_mapping import validate_mapped_sql
        mapping = decode_metric_mapping('{"domain":"other"}', 'Check inventory observation keys')
        for sql in [
            'SELECT MAX(i.snapshot_date) AS latest_snapshot FROM commerce.inventory i LIMIT 1',
            "SELECT COUNT(DISTINCT i.product_id) AS product_count FROM commerce.inventory i WHERE i.snapshot_date='2022-12-31' LIMIT 200",
            'SELECT COALESCE(SUM(d.n-1),0) AS duplicate_rows FROM (SELECT COUNT(*) AS n FROM commerce.inventory i GROUP BY i.snapshot_date,i.product_id HAVING COUNT(*)>1) d LIMIT 200',
        ]:
            with self.subTest(sql=sql):
                plan = decode_query_plan(json.dumps({'sql':sql, 'parameters':[]}))
                validate_metric_definitions(sql, set(), (), APPROVED_COLUMNS)
                validate_mapped_sql(plan, mapping)

    def test_structural_path_cannot_bypass_inventory_measures(self):
        from core.analytics.metric_mapping import validate_mapped_sql
        mapping = decode_metric_mapping('{"domain":"other"}', 'Check observation keys')
        for value in ['SUM(i.stock_on_hand)', 'SUM(i.product_id)', 'AVG(i.fill_rate)', 'i.stock_on_hand']:
            sql='SELECT '+value+' AS value FROM commerce.inventory i LIMIT 200'
            with self.subTest(value=value), self.assertRaises(ValueError):
                plan = decode_query_plan(json.dumps({'sql':sql,'parameters':[]}))
                validate_mapped_sql(plan, mapping)

    def test_observation_path_cannot_hide_a_business_threshold_in_where(self):
        from core.analytics.metric_mapping import validate_mapped_sql
        mapping = decode_metric_mapping('{"domain":"other"}', 'Check observation keys')
        plan = decode_query_plan(json.dumps({'sql':
            'SELECT i.product_id FROM commerce.inventory i WHERE i.stock_on_hand<5 LIMIT 200',
            'parameters':[]}))
        with self.assertRaises(MetricDefinitionError):
            validate_mapped_sql(plan, mapping)


class SchemaContextTest(unittest.TestCase):
    def test_return_context_keeps_keys_grain_and_excludes_web_traffic(self):
        from core.analytics.text_to_sql import build_sql_prompt
        prompt = build_sql_prompt('Returned units by product during 2022', metric_names=set())
        self.assertIn('commerce.returns:', prompt)
        self.assertIn('commerce.products:', prompt)
        self.assertIn('return_id', prompt)
        self.assertIn('Primary keys', prompt)
        self.assertNotIn('commerce.web_traffic:', prompt)

    def test_context_for_inventory_and_orders_preserves_both_sources(self):
        from core.analytics.text_to_sql import build_sql_prompt
        prompt = build_sql_prompt('Inventory units_sold versus ordered quantities', metric_names=set())
        for name in ('inventory', 'orders', 'order_items', 'products'):
            self.assertIn('commerce.'+name+':', prompt)


class CanonicalAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_dimension_uses_full_schema_and_offers_supported_scope(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest, VerifiedIdentity
        for question in ['Which suppliers delivered stock late in December 2022?',
                         'Tổng hợp tồn kho theo nhà cung cấp tại snapshot 2022-12-31']:
            provider, repo = Mock(), AsyncMock()
            result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question=question,
                identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
            self.assertEqual(result.metadata.get('metric_error_code'), 'unsupported_dimension')
            self.assertIn('supplier',result.answer)
            self.assertIn('alternative',result.answer)
            provider.generate.assert_not_called()
            repo.execute_approved_query.assert_not_awaited()

    async def test_unreviewed_alias_cannot_be_replaced_with_an_approved_metric(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.analytics.metric_ontology import METRIC_ONTOLOGY
        from core.models.agents import AgentRequest, VerifiedIdentity
        provider, repo = Mock(), AsyncMock()
        provider.generate.return_value=json.dumps({'metrics':['stock_on_hand'], 'time':{'mode':'latest'}})
        repo.execute_approved_query.return_value=[]
        with patch.dict(METRIC_ONTOLOGY, {'stored_fill_rate':{**METRIC_ONTOLOGY['stored_fill_rate'],
                                                             'approval_status':'unreviewed'}}):
            result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(
                question='Stored fill rate at latest snapshot',
                identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertEqual(result.metadata.get('metric_error_code'), 'metric_unapproved')
        provider.generate.assert_not_called()
        repo.execute_approved_query.assert_not_awaited()

    async def test_transaction_question_does_not_pass_through_inventory_interpreter(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest, VerifiedIdentity
        provider, repo = Mock(), AsyncMock()
        provider.generate.return_value = json.dumps({'sql':
            'SELECT r.product_id,SUM(r.return_quantity) AS returned_units FROM commerce.returns r '
            'WHERE r.return_date >= $1 AND r.return_date < $2 GROUP BY r.product_id ORDER BY 2 DESC LIMIT 10',
            'parameters':['2022-01-01','2023-01-01']})
        repo.execute_approved_query.return_value = [{'product_id':1,'returned_units':7}]
        result = await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(
            question='Which 10 products had the most units returned in 2022?',
            identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertTrue(result.metadata['ok'],result.answer)
        self.assertEqual(provider.generate.call_count,1)

    async def test_provider_failure_is_not_a_validation_failure(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest, VerifiedIdentity
        provider, repo = Mock(), AsyncMock()
        provider.generate.side_effect = ConnectionError('provider unavailable')
        result = await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(
            question='Stock on hand at latest snapshot',
            identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertEqual(result.metadata['execution_status'], 'planning_failed')
        repo.execute_approved_query.assert_not_awaited()

    async def test_valid_mapping_compiles_without_second_llm_interpretation(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest, VerifiedIdentity
        provider, repo = Mock(), AsyncMock()
        provider.generate.return_value = json.dumps({'metrics':['stock_on_hand'],
            'dimensions':['product_id','product_name'], 'representation':'product',
            'time':{'mode':'snapshot','start':'2022-12-31','end':'2022-12-31'},
            'ranking':{'metric':'stock_on_hand','direction':'desc','limit':20}})
        repo.execute_approved_query.return_value = [{'snapshot_date': date(2022,12,31),
            'product_id':1, 'product_name':'A', 'stock_on_hand':12}]
        result = await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(
            question='List the 20 products with highest stock_on_hand on 2022-12-31',
            identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertTrue(result.metadata['ok'], result.answer)
        self.assertEqual(provider.generate.call_count, 1)
        self.assertEqual(result.data['query_status'], 'executed')
        self.assertIn('metrics', result.metadata)
        self.assertEqual(result.metadata['execution_status'], 'executed')
        self.assertEqual(result.metadata['time_scope']['start'], '2022-12-31')
        self.assertEqual(next(c['unit'] for c in result.metadata['columns'] if c['name']=='stock_on_hand'), 'units')


if __name__ == '__main__':
    unittest.main()
