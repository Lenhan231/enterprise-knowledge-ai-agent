import json
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.analytics.business_ontology import policy_context, validate_request_contract
from core.analytics.commerce_decision_support import (
    COMMERCE_DECISION_PROFILES, resolve_commerce_decision_domain, unavailable_commerce_dimensions,
)
from core.analytics.text_to_sql import SQLValidationError, build_sql_prompt, decode_query_plan
from unittest.mock import AsyncMock, Mock, patch
from core.sql_agent.agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest, VerifiedIdentity


class BusinessOntologyTest(unittest.TestCase):
    def test_schema_availability_question_reports_missing_logistics_dimensions(self):
        question = ('Chỉ dựa trên schema commerce hiện có, có thể xếp hạng hãng vận chuyển và chọn '
                    'tuyến giao hàng tốt nhất trên toàn quốc không?')
        missing = unavailable_commerce_dimensions(
            question, 'nationwide_logistics',
            {'order_id', 'ship_date', 'delivery_date', 'shipping_fee', 'zip', 'city', 'district', 'region'},
        )
        self.assertEqual(missing, ['carrier', 'route/lane'])

    def test_promotion_business_support_separates_observed_sales_from_causal_lift(self):
        question = 'Should we scale the promotion with the highest attributed revenue, and does that prove lift?'
        self.assertEqual(resolve_commerce_decision_domain(question), 'promotion_planning')
        profile = COMMERCE_DECISION_PROFILES['promotion_planning']
        self.assertIn('incrementality causal lift', profile['retrieval_query'])
        self.assertTrue(any('not a causal uplift estimate' in item for item in profile['limitations']))
        self.assertTrue(any('ROI and incremental profitability cannot be established' in item
                            for item in profile['limitations']))
        prompt = build_sql_prompt(question, schema_tables={
            'commerce.promotions', 'commerce.orders', 'commerce.order_items', 'commerce.products'})
        self.assertIn('commerce.promotions', prompt)

    def test_chart_contracts_are_bounded_and_reference_only_returned_fields(self):
        sql = 'SELECT category, SUM(amount) AS amount, SUM(quantity) AS quantity FROM commerce.items GROUP BY 1 LIMIT 200'
        contract = {'columns': ['category', 'amount', 'quantity'], 'dimensions': ['category'], 'chart_type': None,
                    'charts': [{'type': 'bar', 'dimension': 'category', 'measures': ['amount']},
                               {'type': 'donut', 'dimension': 'category', 'measures': ['quantity']}]}
        validate_request_contract(sql, contract)
        for defect in ('too_many', 'unknown_measure', 'dimension_measure', 'unknown_dimension', 'invalid_type', 'extra', 'conflict'):
            with self.subTest(defect=defect):
                value = json.loads(json.dumps(contract))
                if defect == 'too_many': value['charts'].append(value['charts'][0])
                elif defect == 'unknown_measure': value['charts'][0]['measures'] = ['invented']
                elif defect == 'dimension_measure': value['charts'][0]['measures'] = ['category']
                elif defect == 'unknown_dimension': value['charts'][0]['dimension'] = 'invented'
                elif defect == 'invalid_type': value['charts'][0]['type'] = ['bar']
                elif defect == 'extra': value['charts'][0]['sql'] = 'DELETE FROM commerce.items'
                else: value['chart_type'] = 'line'
                with self.assertRaises(SQLValidationError): validate_request_contract(sql, value)

    def test_sql_prompt_and_decoder_use_the_policy_contract(self):
        prompt = build_sql_prompt('Revenue by month during 2022')
        self.assertIn('VSC-OPS-POL-001', prompt)
        self.assertIn('request_contract', prompt)
        self.assertIn('independent fact tables', prompt)
        self.assertIn('complete grouped keys', prompt)
        plan = decode_query_plan(json.dumps({'sql': 'SELECT s.revenue AS revenue, s.cogs AS extra FROM commerce.sales s LIMIT 1',
            'parameters': [], 'explanation': 'Revenue only', 'request_contract': {'columns': ['revenue']}}))
        self.assertIn('requested output contract', plan.request_contract_warning)
        self.assertIsNone(plan.request_contract)
        self.assertIn('AS extra', plan.sql)

    def test_invalid_output_contract_does_not_bypass_sql_safety(self):
        with self.assertRaises(SQLValidationError):
            decode_query_plan(json.dumps({'sql': 'DELETE FROM commerce.sales', 'parameters': [],
                'explanation': 'Delete rows', 'request_contract': {'columns': ['revenue']}}))

    def test_context_is_policy_cited_and_schema_scoped(self):
        context = policy_context({'commerce.inventory', 'commerce.products'})
        self.assertEqual(context['policy']['document_id'], 'VSC-OPS-POL-001')
        self.assertEqual(context['policy']['version'], '1.0')
        self.assertEqual(set(context['entities']), {'commerce.inventory', 'commerce.products'})
        self.assertFalse(context['policy']['approves_metric_formulas'])
        self.assertTrue(context['policy']['sha256'])
        self.assertTrue(all(rule['pages'] for rule in context['rules']))
        self.assertTrue(all(set(rule['sources']) <= set(context['entities']) for rule in context['rules']))
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(hashlib.sha256((root / context['policy']['source']).read_bytes()).hexdigest(),
                         context['policy']['sha256'])

    def test_output_contract_rejects_extra_measure(self):
        contract = {'columns': ['month', 'growth'], 'dimensions': ['month']}
        sql = 'SELECT s.date AS month, s.revenue AS revenue, s.revenue AS growth FROM commerce.sales s LIMIT 200'
        with self.assertRaises(SQLValidationError):
            validate_request_contract(sql, contract)

    def test_independent_filters_cannot_be_a_shared_intersection(self):
        contract = {'columns': ['stockout_count', 'overstock_count'], 'measure_filters': {
            'stockout_count': {'column': 'stockout_flag', 'equals': True},
            'overstock_count': {'column': 'overstock_flag', 'equals': True}}}
        sql = 'SELECT COUNT(*) FILTER (WHERE i.stockout_flag = TRUE) AS stockout_count, COUNT(*) FILTER (WHERE i.overstock_flag = TRUE) AS overstock_count FROM commerce.inventory i LIMIT 1'
        validate_request_contract(sql, contract)
        validate_request_contract(sql.replace('= TRUE', '= $1'), contract, (True,))
        validate_request_contract(sql.replace('= TRUE', 'IS TRUE'), contract)
        with self.assertRaises(SQLValidationError):
            validate_request_contract(sql.replace('= TRUE', '= $1'), contract, (False,))
        wrong = 'SELECT COUNT(*) AS stockout_count, COUNT(*) AS overstock_count FROM commerce.inventory i WHERE i.stockout_flag = TRUE AND i.overstock_flag = TRUE LIMIT 1'
        with self.assertRaises(SQLValidationError):
            validate_request_contract(wrong, contract)

    def test_contract_cannot_supply_sql_or_arbitrary_fields(self):
        with self.assertRaises(SQLValidationError):
            validate_request_contract('SELECT s.revenue FROM commerce.sales s LIMIT 1',
                                      {'columns': ['revenue'], 'sql': 'DELETE FROM commerce.sales'})


class OntologyAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_repository_close_failure_still_closes_provider(self):
        repository = AsyncMock()
        repository.close.side_effect = RuntimeError('fixture close failure')
        provider = Mock()
        agent = SQLAnalyticsAgent(repository, llm=provider)
        with self.assertRaises(RuntimeError):
            await agent.close()
        provider.close.assert_called_once()

    async def test_invalid_contract_is_advisory_and_query_still_runs(self):
        repository = Mock()
        repository.get_schema = AsyncMock(return_value={})
        repository.execute_approved_query = AsyncMock(return_value=[{'sessions': 12}])
        provider = Mock()
        provider.generate.side_effect = [json.dumps({'intent': {
            'original_question': 'Total recorded sessions', 'operation': 'aggregate',
            'metrics': ['sessions'], 'dimensions': [], 'filters': [],
            'time_scope': {'mode': 'all', 'ranges': []}, 'requested_sources': [],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }}), json.dumps({
            'sql': 'SELECT SUM(w.sessions) AS sessions, SUM(w.page_views) AS extra FROM commerce.web_traffic w LIMIT 1',
            'parameters': [], 'explanation': 'sessions only', 'request_contract': {'columns': ['sessions']}})]
        agent = SQLAnalyticsAgent(repository, llm=provider)
        result = await agent.run_payload(AgentRequest(question='Total recorded sessions',
            identity=VerifiedIdentity(subject='test', permissions={'analytics:read'})))
        self.assertTrue(result['ok'], result)
        repository.execute_approved_query.assert_awaited_once()
        self.assertEqual(provider.generate.call_count, 2)
        self.assertEqual(result['metadata']['source'], ['commerce.web_traffic'])
        self.assertIn('extra', result['sql'])
        self.assertEqual(result['metadata']['request_contract_status'], 'ignored')
        self.assertIn('output mapping did not match', result['limitations'][-1])
