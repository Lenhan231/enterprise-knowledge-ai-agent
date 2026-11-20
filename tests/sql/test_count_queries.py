import json
import sqlite3
import unittest
from datetime import date

from sqlglot import parse_one

from core.agents.sql.counting import compile_count_query, validate_count_period
from core.agents.sql.metric_validation import MetricDefinitionError, validate_independent_query_period
from core.agents.sql.sql_validation import APPROVED_COLUMNS


def count_query(**changes):
    return {'source': 'commerce.inventory', 'counts': [
        {'alias': 'sku_count', 'kind': 'distinct', 'field': 'product_id'},
        {'alias': 'out_count', 'kind': 'distinct', 'field': 'product_id',
         'filters': [{'field': 'stockout_flag', 'operator': 'eq', 'value': True}]},
        {'alias': 'over_count', 'kind': 'distinct', 'field': 'product_id',
         'filters': [{'field': 'overstock_flag', 'operator': 'eq', 'value': True}]}],
        'time': {'mode': 'latest', 'field': 'snapshot_date'}, **changes}


class CountQueriesTest(unittest.TestCase):
    def run_count(self, value, rows, question='latest available inventory snapshot'):
        plan, definitions, _ = compile_count_query(value, APPROVED_COLUMNS, question)
        with sqlite3.connect(':memory:') as db:
            db.execute("ATTACH DATABASE ':memory:' AS commerce")
            db.execute('CREATE TABLE commerce.inventory(snapshot_date TEXT, product_id INT, stockout_flag BOOL, overstock_flag BOOL, category TEXT)')
            db.executemany('INSERT INTO commerce.inventory VALUES (?,?,?,?,?)', rows)
            cursor = db.execute(parse_one(plan.sql, read='postgres').sql(dialect='sqlite'),
                                [str(p) if isinstance(p, date) else p for p in plan.parameters])
            result = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor]
        return result, plan, definitions

    def test_three_distinct_counts_keep_overlap_nulls_duplicates_and_unfiltered_latest(self):
        rows = [('2026-04-30', 8, 1, 1, 'A'),
                ('2026-05-31', 1, 1, 0, 'A'), ('2026-05-31', 1, 1, 0, 'A'),
                ('2026-05-31', 2, 1, 1, 'B'), ('2026-05-31', 3, None, 1, 'B'),
                ('2026-05-31', None, 1, 1, 'B')]
        result, plan, definitions = self.run_count(count_query(), rows)
        self.assertEqual([{'snapshot_date': '2026-05-31', 'sku_count': 3, 'out_count': 2, 'over_count': 2}], result)
        self.assertNotIn('JOIN', plan.sql)
        self.assertEqual({'sku_count', 'out_count', 'over_count'}, set(definitions))

    def test_rows_nonnull_and_distinct_have_different_null_duplicate_semantics(self):
        counts = [{'alias': 'records', 'kind': 'rows'}, {'alias': 'known_ids', 'kind': 'nonnull', 'field': 'product_id'},
                  {'alias': 'identities', 'kind': 'distinct', 'field': 'product_id'},
                  {'alias': 'unknown_flags', 'kind': 'rows', 'filters': [{'field': 'stockout_flag', 'operator': 'is_null'}]}]
        rows = [('2026-05-31', 1, None, 0, 'A'), ('2026-05-31', 1, 0, 1, 'A'), ('2026-05-31', None, 1, 1, 'B')]
        result, _, _ = self.run_count(count_query(counts=counts), rows)
        self.assertEqual([{'snapshot_date': '2026-05-31', 'records': 3, 'known_ids': 2, 'identities': 1, 'unknown_flags': 1}], result)

    def test_empty_scalar_counts_are_zero_and_latest_is_not_filtered(self):
        result, _, _ = self.run_count(count_query(filters=[{'field': 'category', 'operator': 'eq', 'value': 'A'}]),
            [('2026-04-30', 1, 1, 1, 'A'), ('2026-05-31', 2, 0, 0, 'B')])
        self.assertEqual('2026-05-31', result[0]['snapshot_date'])
        self.assertEqual((0, 0, 0), tuple(result[0][k] for k in ('sku_count', 'out_count', 'over_count')))

    def test_grouped_range_keeps_snapshot_boundaries(self):
        value = count_query(dimensions=['category'], time={'mode': 'range', 'field': 'snapshot_date', 'start': '2026-04-01', 'end': '2026-05-31'})
        rows = [('2026-03-31', 9, 1, 1, 'A'), ('2026-04-30', 1, 1, 0, 'A'), ('2026-05-31', 2, 0, 1, 'A'), ('2026-06-01', 3, 1, 1, 'A')]
        result, _, _ = self.run_count(value, rows, 'inventory counts from 2026-04-01 through 2026-05-31 by category')
        self.assertEqual(['2026-04-30', '2026-05-31'], [r['snapshot_date'] for r in result])
        self.assertEqual([1, 1], [r['sku_count'] for r in result])

    def test_unsafe_or_ambiguous_count_contracts_are_rejected(self):
        for change in ({'joins': []}, {'source': 'private.users'}, {'counts': [{'alias': 'n', 'kind': 'distinct'}]},
                       {'counts': [{'alias': 'n', 'kind': 'rows', 'field': 'product_id'}]},
                       {'counts': [{'alias': 'n', 'kind': 'distinct', 'field': 'password'}]},
                       {'counts': [{'alias': 'n', 'kind': 'rows', 'filters': [{'field': 'stockout_flag', 'operator': 'eq', 'value': None}]}]},
                       {'counts': [{'alias': 'n', 'kind': 'rows'}] * 2},
                       {'time': {'mode': 'all'}}, {'time': {'mode': 'latest', 'field': 'product_id'}}):
            with self.subTest(change=change), self.assertRaises(MetricDefinitionError):
                compile_count_query(count_query(**change), APPROVED_COLUMNS, 'latest available inventory snapshot')

    def test_generic_counts_use_any_approved_source_not_specific_flag_names(self):
        value = {'source': 'commerce.orders', 'counts': [{'alias': 'identities', 'kind': 'distinct', 'field': 'order_id'},
                 {'alias': 'matches', 'kind': 'rows', 'filters': [{'field': 'order_status', 'operator': 'in', 'value': ['paid', 'complete']}]}],
                 'time': {'mode': 'range', 'field': 'order_date', 'start': '2026-01-01', 'end': '2026-12-31'}}
        plan, _, _ = compile_count_query(value, APPROVED_COLUMNS, 'count orders in 2026')
        self.assertIn('COUNT(DISTINCT', plan.sql)
        self.assertIn('FILTER', plan.sql)
        self.assertNotIn('stockout', plan.sql)

    def test_count_alias_cannot_redefine_an_existing_business_metric(self):
        for count in ({'alias': 'revenue', 'kind': 'rows'},
                      {'alias': 'order_count', 'kind': 'rows'},
                      {'alias': 'observed_product_count', 'kind': 'nonnull', 'field': 'product_id'}):
            with self.subTest(count=count), self.assertRaises(MetricDefinitionError):
                compile_count_query(count_query(counts=[count]), APPROVED_COLUMNS, 'latest inventory snapshot')

    def test_generic_date_range_includes_the_entire_last_day(self):
        spec = {'source': 'commerce.orders', 'counts': [{'alias': 'n', 'kind': 'rows'}],
                'time': {'mode': 'range', 'field': 'order_date', 'start': '2026-05-01', 'end': '2026-05-31'}}
        plan, _, _ = compile_count_query(spec, APPROVED_COLUMNS, 'Count rows in commerce.orders from 2026-05-01 through 2026-05-31')
        with sqlite3.connect(':memory:') as db:
            db.execute("ATTACH DATABASE ':memory:' AS commerce")
            db.execute('CREATE TABLE commerce.orders(order_date TEXT)')
            db.executemany('INSERT INTO commerce.orders VALUES (?)', [('2026-05-01 00:00:00',), ('2026-05-31 23:59:59',), ('2026-06-01 00:00:00',)])
            count = db.execute(parse_one(plan.sql, read='postgres').sql(dialect='sqlite'), [str(p) for p in plan.parameters]).fetchone()[0]
        self.assertEqual(2, count)

    def test_unique_source_date_is_resolved_without_asking_user(self):
        value = count_query(time={'mode': 'latest'})
        _, _, spec = compile_count_query(value, APPROVED_COLUMNS, 'latest available inventory snapshot')
        self.assertEqual('snapshot_date', spec.time.field)
        generic = {'source': 'commerce.web_traffic', 'counts': [{'alias': 'n', 'kind': 'rows'}], 'time': {'mode': 'latest'}}
        _, _, spec = compile_count_query(generic, APPROVED_COLUMNS, 'latest available traffic observation')
        self.assertEqual('date', spec.time.field)

    def test_multiple_source_dates_ask_an_actionable_choice(self):
        spec = {'source': 'commerce.shipments', 'counts': [{'alias': 'n', 'kind': 'rows'}], 'time': {'mode': 'latest'}}
        with self.assertRaises(MetricDefinitionError) as raised:
            compile_count_query(spec, APPROVED_COLUMNS, 'latest available shipment observations')
        self.assertTrue(raised.exception.clarification)
        self.assertIn('ship_date', str(raised.exception))
        self.assertIn('delivery_date', str(raised.exception))

    def test_latest_within_requested_period_keeps_latest_semantics(self):
        value = count_query(time={'mode': 'latest', 'start': '2026-01-01', 'end': '2026-12-31'})
        result, _, _ = self.run_count(value, [('2026-05-31', 1, 1, 0, 'A'),
            ('2026-11-13', 2, 0, 1, 'B'), ('2027-01-31', 3, 1, 1, 'A')],
            'Count SKUs and flags at the latest available inventory snapshot. User clarification: Jan to Dec 2026')
        self.assertEqual([{'snapshot_date': '2026-11-13', 'sku_count': 1, 'out_count': 0, 'over_count': 1}], result)

    def test_latest_period_cannot_be_silently_changed_or_dropped(self):
        for temporal in ({'mode': 'latest', 'field': 'snapshot_date'},
                         {'mode': 'range', 'field': 'snapshot_date', 'start': '2026-01-01', 'end': '2026-12-31'},
                         {'mode': 'latest', 'field': 'snapshot_date', 'start': '2025-01-01', 'end': '2025-12-31'}):
            with self.subTest(temporal=temporal), self.assertRaises(MetricDefinitionError):
                compile_count_query(count_query(time=temporal), APPROVED_COLUMNS, 'latest available inventory snapshot in 2026')

    def test_period_validation_checks_outer_and_latest_subquery_bounds(self):
        question = 'latest available inventory snapshot in 2026'
        plan, _, _ = compile_count_query(count_query(time={'mode': 'latest', 'start': '2026-01-01', 'end': '2026-12-31'}), APPROVED_COLUMNS, question)
        from core.agents.sql.sql_validation import APPROVED_DATE_COLUMNS
        validate_count_period(plan, question, {'commerce.inventory'}, APPROVED_DATE_COLUMNS)
        from sqlglot import exp
        tree = parse_one(plan.sql, read='postgres')
        equality = next(item for item in tree.args['where'].find_all(exp.EQ) if item.find(exp.Subquery))
        tree.set('where', exp.Where(this=equality.copy()))
        with self.assertRaises(MetricDefinitionError):
            validate_count_period(type(plan)(sql=tree.sql(dialect='postgres'), parameters=plan.parameters), question, {'commerce.inventory'}, APPROVED_DATE_COLUMNS)
