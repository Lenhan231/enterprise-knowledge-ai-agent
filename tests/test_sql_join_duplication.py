import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.analytics.text_to_sql import SQLValidationError, validate_commerce_sql
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest, VerifiedIdentity


JOIN = ('FROM commerce.orders AS o JOIN commerce.payments AS p ON o.order_id = p.order_id '
        'JOIN commerce.order_items AS i ON o.order_id = i.order_id ')


class JoinDuplicationTest(unittest.TestCase):
    def test_rejects_duplicated_payment_measures(self):
        for expression in ('SUM(p.payment_value)', 'AVG(p.payment_value)', 'COUNT(p.order_id)',
                           'SUM(DISTINCT p.payment_value)', 'SUM(p.payment_value * i.quantity)'):
            with self.subTest(expression=expression), self.assertRaisesRegex(SQLValidationError, 'duplicat'):
                validate_commerce_sql(f'SELECT {expression} AS total {JOIN} LIMIT 1')

    def test_accepts_detail_measure_and_duplicate_insensitive_aggregates(self):
        for expression in ('SUM(i.quantity)', 'COUNT(i.order_item_id)', 'COUNT(DISTINCT p.order_id)',
                           'MIN(p.payment_value)', 'MAX(p.payment_value)'):
            with self.subTest(expression=expression):
                validate_commerce_sql(f'SELECT {expression} AS total {JOIN} LIMIT 1')

    def test_rejects_many_to_many_detail_join(self):
        sql = (f'SELECT SUM(i.quantity) AS total {JOIN}'
               'LEFT JOIN commerce.returns AS r ON o.order_id = r.order_id LIMIT 1')
        with self.assertRaisesRegex(SQLValidationError, 'duplicat'):
            validate_commerce_sql(sql)

    def test_count_star_requires_unambiguous_grain(self):
        with self.assertRaisesRegex(SQLValidationError, 'duplicat'):
            validate_commerce_sql(f'SELECT COUNT(*) AS total {JOIN} LIMIT 1')

    def test_accepts_one_to_one_join(self):
        validate_commerce_sql('SELECT SUM(p.payment_value) AS total FROM commerce.payments AS p '
                              'JOIN commerce.orders AS o ON p.order_id = o.order_id '
                              'JOIN commerce.shipments AS sh ON o.order_id = sh.order_id LIMIT 1')

    def test_cte_does_not_hide_duplication(self):
        for projection in ('p.payment_value', 'p.payment_value * 2'):
            sql = (f'WITH detail AS (SELECT {projection} AS value {JOIN}) '
                   'SELECT SUM(d.value) AS total FROM detail AS d LIMIT 1')
            with self.assertRaisesRegex(SQLValidationError, 'duplicat'):
                validate_commerce_sql(sql)

    def test_distinct_cte_is_not_assumed_to_restore_measure_grain(self):
        sql = (f'WITH detail AS (SELECT DISTINCT p.payment_value AS value {JOIN}) '
               'SELECT SUM(d.value) AS total FROM detail AS d LIMIT 1')
        with self.assertRaisesRegex(SQLValidationError, 'duplicat'):
            validate_commerce_sql(sql)

    def test_nested_cte_and_row_counts_cannot_hide_duplication(self):
        for expression in ('SUM(x.value)', 'COUNT(*)', 'SUM(1)'):
            sql = (f'WITH detail AS (SELECT p.payment_value AS value {JOIN}), '
                   'renamed AS (SELECT d.value AS value FROM detail AS d) '
                   f'SELECT {expression} AS total FROM renamed AS x LIMIT 1')
            with self.subTest(expression=expression), self.assertRaisesRegex(SQLValidationError, 'duplicat'):
                validate_commerce_sql(sql)

    def test_safe_precomputed_aggregate_remains_safe(self):
        validate_commerce_sql(f'WITH counts AS (SELECT COUNT(DISTINCT p.order_id) AS total {JOIN}) '
                              'SELECT SUM(c.total) AS total FROM counts AS c LIMIT 1')

    def test_scalar_subquery_aggregate_cannot_hide_raw_duplicated_rows(self):
        for expression in ('SUM(d.value)', 'COUNT(*)'):
            sql = ('WITH detail AS (SELECT p.payment_value + '
                   f'(SELECT MAX(s.revenue) FROM commerce.sales AS s) AS value {JOIN}) '
                   f'SELECT {expression} AS total FROM detail AS d LIMIT 1')
            with self.subTest(expression=expression), self.assertRaisesRegex(SQLValidationError, 'duplicat'):
                validate_commerce_sql(sql)

    def test_join_order_does_not_change_measure_safety(self):
        join = ('FROM commerce.order_items AS i JOIN commerce.orders AS o ON i.order_id = o.order_id '
                'JOIN commerce.payments AS p ON p.order_id = o.order_id ')
        validate_commerce_sql('SELECT SUM(i.quantity) AS total ' + join + 'LIMIT 1')
        with self.assertRaisesRegex(SQLValidationError, 'duplicat'):
            validate_commerce_sql('SELECT SUM(p.payment_value) AS total ' + join + 'LIMIT 1')

    def test_inventory_to_products_is_safe_but_reverse_duplicates_products(self):
        join = ('FROM commerce.inventory AS i JOIN commerce.products AS p '
                'ON i.product_id = p.product_id ')
        validate_commerce_sql('SELECT AVG(i.days_of_supply) AS total ' + join + 'LIMIT 1')
        with self.assertRaisesRegex(SQLValidationError, 'duplicat'):
            validate_commerce_sql('SELECT SUM(p.price) AS total ' + join + 'LIMIT 1')

    def test_fixture_shows_why_sum_distinct_is_not_a_fix(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('CREATE TABLE payments (id INT, value INT); '
                             'CREATE TABLE items (order_id INT); '
                             'INSERT INTO payments VALUES (1, 100), (2, 100); '
                             'INSERT INTO items VALUES (1), (1), (2);')
            self.assertEqual(db.execute('SELECT SUM(value), SUM(DISTINCT value) FROM payments '
                                        'JOIN items ON id = order_id').fetchone(), (300, 100))
            self.assertEqual(db.execute('SELECT SUM(value) FROM payments').fetchone()[0], 200)


class JoinRepairTest(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_unsafe_plan_never_executes(self):
        class Provider:
            def generate(self, prompt):
                if prompt.startswith("Interpret the question BEFORE"):
                    return json.dumps({"domain":"other"})
                return json.dumps({'sql': f'SELECT SUM(p.payment_value) AS total {JOIN} LIMIT 1'})
        repository = AsyncMock()
        result = await SQLAnalyticsAgent(repository, llm=Provider()).run(AgentRequest(
            question='Total payment value', identity=VerifiedIdentity(subject='test', permissions={'analytics:read'})))
        self.assertFalse(result.metadata['ok'])
        repository.execute_approved_query.assert_not_awaited()

    async def test_unsafe_plan_is_repaired_before_repository_execution(self):
        unsafe = f'SELECT SUM(p.payment_value) AS total {JOIN} LIMIT 1'
        safe = 'SELECT SUM(p.payment_value) AS total FROM commerce.payments AS p LIMIT 1'
        responses = iter(json.dumps({'sql': sql}) for sql in (unsafe, safe))
        class Provider:
            def generate(self, prompt):
                if prompt.startswith("Interpret the question BEFORE"):
                    return json.dumps({"domain":"other"})
                return next(responses)
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{'total': 200}]
        result = await SQLAnalyticsAgent(repository, llm=Provider()).run(AgentRequest(
            question='Total payment value', identity=VerifiedIdentity(subject='test', permissions={'analytics:read'})))
        self.assertTrue(result.metadata['ok'])
        repository.execute_approved_query.assert_awaited_once_with(safe)


if __name__ == '__main__':
    unittest.main()
