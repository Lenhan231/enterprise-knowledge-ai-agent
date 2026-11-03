import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.analytics.metric_mapping import build_metric_mapping_prompt, decode_metric_mapping
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.text_to_sql import build_sql_prompt, validate_commerce_sql, SQLValidationError, decode_query_plan
from core.analytics.metric_validation import validate_metric_definitions, MetricDefinitionError
from core.analytics.text_to_sql import APPROVED_COLUMNS


class InterpretationRegressionTest(unittest.TestCase):
    def test_duplicate_conventions_differ_on_nonempty_fixture(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('CREATE TABLE observations (snapshot_date TEXT, product_id INT); '
                "INSERT INTO observations VALUES ('2022-12-31',1),('2022-12-31',1),('2022-12-31',1),"
                "('2022-12-31',2),('2022-12-31',2),('2022-11-30',1);")
            row = db.execute('SELECT COUNT(*),SUM(n-1),SUM(n) FROM (SELECT COUNT(*) n FROM observations '
                             'GROUP BY snapshot_date,product_id HAVING COUNT(*)>1)').fetchone()
            self.assertEqual(row, (2,3,5))

    def test_overloaded_date_function_parameter_is_typed(self):
        plan = decode_query_plan(json.dumps({'sql':
            "SELECT r.product_id FROM commerce.returns r WHERE DATE_TRUNC('year',r.return_date)=DATE_TRUNC('year',$1) LIMIT 10",
            'parameters':['2022-01-01']}))
        self.assertIn('CAST($1 AS DATE)', plan.sql)

    def test_duplicate_group_count_is_not_excess_row_count(self):
        sql = ('SELECT COUNT(*) AS duplicate_rows FROM (SELECT i.snapshot_date,i.product_id,COUNT(*) AS n '
               'FROM commerce.inventory i GROUP BY i.snapshot_date,i.product_id HAVING COUNT(*)>1) d LIMIT 200')
        with self.assertRaises(MetricDefinitionError):
            validate_metric_definitions(sql, set(), (), APPROVED_COLUMNS,
                question='How many inventory rows have duplicate (snapshot_date,product_id) keys?')
        validate_metric_definitions(sql.replace('COUNT(*) AS duplicate_rows', 'COALESCE(SUM(d.n-1),0) AS duplicate_rows'),
            set(), (), APPROVED_COLUMNS,
            question='How many inventory rows have duplicate (snapshot_date,product_id) keys?')

    def test_catalog_ids_are_recognized_before_schema_pruning(self):
        self.assertEqual(resolve_metric_names('Average fill_rate by category in December 2022'), {'fill_rate'})
        self.assertIn('commerce.inventory:', build_sql_prompt(
            'Average fill_rate by category in December 2022'))

    def test_unspecified_ranking_does_not_invent_top_ten(self):
        payload = {'metrics':['stockout_days'], 'dimensions':['product_id'],
                   'representation':'product', 'time':{'mode':'range','start':'2022-12-01','end':'2022-12-31'},
                   'ranking':{'metric':'stockout_days','direction':'desc','limit':10}}
        mapping = decode_metric_mapping(json.dumps(payload), 'Products with highest stockout_days in December 2022')
        self.assertEqual(mapping.ranking.limit, 200)
        mapping = decode_metric_mapping(json.dumps(payload), 'Top 7 products by stockout_days in December 2022')
        self.assertEqual(mapping.ranking.limit, 7)
        mapping = decode_metric_mapping(json.dumps(payload), 'Top seven products by stockout_days in December 2022')
        self.assertEqual(mapping.ranking.limit, 7)

    def test_cross_domain_definitions_do_not_require_invented_kpis(self):
        prompt = build_sql_prompt('Returned units divided by ordered units per product in 2022')
        self.assertIn('independently', prompt)
        self.assertIn('NULLIF', prompt)


class DerivedJoinContractTest(unittest.TestCase):
    def test_independent_operands_avoid_fanout_and_keep_undefined_ratio_null(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('CREATE TABLE ret (pid INT, units INT); CREATE TABLE ord (pid INT, units INT); '
                'INSERT INTO ret VALUES (1,1),(1,2),(2,3); INSERT INTO ord VALUES (1,4),(1,4),(1,4),(2,0);')
            actual = db.execute('WITH r AS (SELECT pid,SUM(units) n FROM ret GROUP BY pid), '
                'o AS (SELECT pid,SUM(units) n FROM ord GROUP BY pid) '
                'SELECT r.pid,1.0*r.n/NULLIF(o.n,0) FROM r JOIN o ON r.pid=o.pid ORDER BY r.pid').fetchall()
            self.assertEqual(actual, [(1,.25),(2,None)])
            multiplied = db.execute('SELECT 1.0*SUM(ret.units)/SUM(ord.units) FROM ret '
                'JOIN ord ON ret.pid=ord.pid WHERE ret.pid=1').fetchone()[0]
            self.assertEqual(multiplied, .375)

    ratio = ('WITH ret AS (SELECT r.product_id,SUM(r.return_quantity) AS n FROM commerce.returns r GROUP BY r.product_id), '
             'ord AS (SELECT oi.product_id,SUM(oi.quantity) AS n FROM commerce.order_items oi GROUP BY oi.product_id) '
             'SELECT ret.product_id,ret.n / NULLIF(ord.n,0) AS ratio FROM ret JOIN ord ON ret.product_id=ord.product_id LIMIT 200')

    def test_independent_product_aggregates_are_safe(self):
        validate_commerce_sql(self.ratio)

    def test_inner_limit_does_not_hide_incomplete_operands(self):
        with self.assertRaises(SQLValidationError):
            validate_commerce_sql(self.ratio.replace('GROUP BY r.product_id)', 'GROUP BY r.product_id LIMIT 10)'))

    def test_unit_ratio_formula_and_each_period_are_verified(self):
        sql = ("WITH ret AS (SELECT r.product_id,SUM(r.return_quantity) AS returned_units FROM commerce.returns r "
               "WHERE r.return_date >= DATE '2022-01-01' AND r.return_date < DATE '2023-01-01' GROUP BY r.product_id), "
               'ord AS (SELECT oi.product_id,SUM(oi.quantity) AS ordered_units FROM commerce.orders o '
               "JOIN commerce.order_items oi ON o.order_id=oi.order_id WHERE o.order_date >= DATE '2022-01-01' "
               "AND o.order_date < DATE '2023-01-01' GROUP BY oi.product_id) "
               'SELECT ret.product_id,ret.returned_units,ord.ordered_units,'
               'CAST(ret.returned_units AS NUMERIC)/NULLIF(ord.ordered_units,0) AS ratio '
               'FROM ret JOIN ord ON ret.product_id=ord.product_id LIMIT 200')
        validate_commerce_sql(sql)
        validate_metric_definitions(sql,set(),(),APPROVED_COLUMNS,
            question='Products with highest ratio of returned units in 2022 to ordered units in 2022')
        for bad in [sql.replace('NULLIF(ord.ordered_units,0)','NULLIF(ret.returned_units,0)'),
                    sql.replace("o.order_date >= DATE '2022-01-01'", "o.order_date >= DATE '2021-01-01'")]:
            with self.subTest(sql=bad), self.assertRaises(MetricDefinitionError):
                validate_metric_definitions(bad,set(),(),APPROVED_COLUMNS,
                    question='Products with highest ratio of returned units in 2022 to ordered units in 2022')

    def test_raw_fact_join_still_rejected(self):
        sql = ('SELECT SUM(r.return_quantity) AS n FROM commerce.returns r '
               'JOIN commerce.order_items oi ON r.product_id=oi.product_id LIMIT 200')
        with self.assertRaises(SQLValidationError):
            validate_commerce_sql(sql)

    def test_ungrouped_or_incomplete_derived_key_is_rejected(self):
        for sql in [self.ratio.replace('SUM(oi.quantity)', 'oi.quantity').replace(' GROUP BY oi.product_id', ''),
                    self.ratio.replace('GROUP BY oi.product_id', 'GROUP BY oi.product_id,oi.order_id')]:
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                validate_commerce_sql(sql)

    def test_join_cannot_hide_a_cross_product_using_other_relations_keys(self):
        with self.assertRaises(SQLValidationError):
            validate_commerce_sql(self.ratio.replace(' LIMIT 200',
                ' JOIN commerce.orders extra ON ret.product_id=ord.product_id LIMIT 200'))

    def test_same_category_lineage_is_safe_but_unrelated_attributes_are_not(self):
        sql = ('WITH inv AS (SELECT p.category,SUM(i.units_sold) AS n FROM commerce.inventory i '
               'JOIN commerce.products p ON i.product_id=p.product_id GROUP BY p.category), '
               'ord AS (SELECT q.category,SUM(oi.quantity) AS n FROM commerce.order_items oi '
               'JOIN commerce.products q ON oi.product_id=q.product_id GROUP BY q.category) '
               'SELECT COALESCE(inv.category,ord.category) AS category,inv.n,ord.n AS ordered_units '
               'FROM inv FULL JOIN ord ON inv.category=ord.category LIMIT 200')
        validate_commerce_sql(sql)
        with self.assertRaises(SQLValidationError):
            validate_commerce_sql(sql.replace('q.category', 'q.color'))


class CrossDomainInventoryTest(unittest.TestCase):
    comparison = ('WITH inv AS (SELECT p.category,SUM(i.units_sold) AS inventory_units_sold '
                  'FROM commerce.inventory i JOIN commerce.products p ON i.product_id=p.product_id '
                  "WHERE i.snapshot_date >= DATE '2022-12-01' AND i.snapshot_date < DATE '2023-01-01' GROUP BY p.category), "
                  'ord AS (SELECT q.category,SUM(oi.quantity) AS ordered_units FROM commerce.order_items oi '
                  'JOIN commerce.orders o ON oi.order_id=o.order_id JOIN commerce.products q ON oi.product_id=q.product_id '
                  "WHERE o.order_date >= DATE '2022-12-01' AND o.order_date < DATE '2023-01-01' GROUP BY q.category) "
                  'SELECT COALESCE(inv.category,ord.category) AS category,inv.inventory_units_sold,ord.ordered_units '
                  'FROM inv FULL JOIN ord ON inv.category=ord.category LIMIT 200')

    def test_explicit_period_flow_comparison_keeps_sources_independent(self):
        validate_commerce_sql(self.comparison)
        result = validate_metric_definitions(self.comparison, {'inventory_units_sold'}, (), APPROVED_COLUMNS,
            question='For each category compare summed December 2022 inventory units_sold with ordered quantities')
        self.assertEqual(result['inventory_units_sold']['representation'], 'period_observation_sum')

    def test_comparison_cannot_roll_up_stock_balances_or_change_formula(self):
        for value in ['stock_on_hand', 'units_sold * 2']:
            sql = self.comparison.replace('SUM(i.units_sold)', 'SUM(i.'+value+')')
            with self.subTest(value=value), self.assertRaises(MetricDefinitionError):
                validate_metric_definitions(sql, {'inventory_units_sold'}, (), APPROVED_COLUMNS,
                    question='Compare summed December 2022 inventory units_sold with ordered quantities by category')

    def test_stockout_presence_uses_exists_without_multiplication(self):
        sql = ('SELECT i.snapshot_date,i.product_id,p.product_name FROM commerce.inventory i '
               'JOIN commerce.products p ON i.product_id=p.product_id '
               "WHERE i.snapshot_date >= DATE '2022-12-01' AND i.snapshot_date < DATE '2023-01-01' "
               'AND i.stockout_flag=TRUE AND EXISTS (SELECT 1 FROM commerce.order_items oi '
               'JOIN commerce.orders o ON oi.order_id=o.order_id WHERE oi.product_id=p.product_id '
               "AND o.order_date >= DATE '2022-12-01' AND o.order_date < DATE '2023-01-01') LIMIT 200")
        validate_commerce_sql(sql)
        with self.assertRaises(SQLValidationError):
            validate_commerce_sql(sql.replace('oi.product_id=p.product_id', 'oi.quantity=p.product_id'))
        with self.assertRaises(SQLValidationError):
            validate_commerce_sql(sql.replace('oi.product_id=p.product_id', '(oi.product_id=p.product_id OR oi.quantity=1)'))
        validate_metric_definitions(sql, {'stockout_indicator'}, (), APPROVED_COLUMNS,
            question='Products with stockout_flag=true in December 2022 and any customer orders that month')
        with self.assertRaises(MetricDefinitionError):
            validate_metric_definitions(sql.replace('i.stockout_flag=TRUE', 'i.stockout_flag=FALSE'),
                {'stockout_indicator'}, (), APPROVED_COLUMNS,
                question='Products with stockout_flag=true in December 2022 and any customer orders that month')


class CrossDomainAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_comparison_reaches_shared_sql_path_and_readonly_repository(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent, AnalyticsPermissionDenied
        from core.models.agents import AgentRequest, VerifiedIdentity
        provider, repository = Mock(), AsyncMock()
        provider.generate.return_value = json.dumps({'sql':CrossDomainInventoryTest.comparison})
        repository.execute_approved_query.return_value = [{'category':'A','inventory_units_sold':3,'ordered_units':4}]
        agent = SQLAnalyticsAgent(repository,llm=provider)
        question = 'For each category compare summed December 2022 inventory units_sold with ordered quantities'
        with self.assertRaises(AnalyticsPermissionDenied):
            await agent.run(AgentRequest(question=question,identity=VerifiedIdentity(subject='denied')))
        provider.generate.assert_not_called()
        repository.execute_approved_query.assert_not_awaited()
        result = await agent.run(AgentRequest(question=question,
            identity=VerifiedIdentity(subject='analyst',permissions={'analytics:read'})))
        self.assertEqual(result.metadata['execution_status'],'executed',result.answer)
        self.assertEqual(provider.generate.call_count,1)
        self.assertIn('period_observation_sum',str(result.metadata['metrics']))

    async def test_dropped_order_operand_cannot_execute(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest, VerifiedIdentity
        provider, repository = Mock(), AsyncMock()
        provider.generate.return_value = json.dumps({'sql':
            "SELECT i.snapshot_date,i.product_id,i.stockout_flag AS stockout_indicator FROM commerce.inventory i "
            "WHERE i.snapshot_date >= DATE '2022-12-01' AND i.snapshot_date < DATE '2023-01-01' LIMIT 200"})
        result = await SQLAnalyticsAgent(repository,llm=provider).run(AgentRequest(
            question='Products with stockout_flag=true in December 2022 and any customer orders that month',
            identity=VerifiedIdentity(subject='analyst',permissions={'analytics:read'})))
        self.assertEqual(result.metadata.get('error_type'),'SQLValidationError')
        self.assertEqual(provider.generate.call_count,2)
        repository.execute_approved_query.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
