import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.reports.planning import ReportPlan, build_task_sql, validate_plan
from core.analytics.text_to_sql import validate_commerce_sql


def inventory_plan():
    return ReportPlan.model_validate({
        'purpose': 'Category inventory',
        'tasks': [{'id': 'stock', 'question': 'stock on hand latest snapshot by category',
                   'mapping': {'metrics': ['stock_on_hand'], 'dimensions': ['category'],
                               'time': {'mode': 'latest'}}}],
        'sections': [{'heading': 'Category stock', 'tasks': ['stock']}],
    })


class ReportPlanningTest(unittest.TestCase):
    def test_identical_snapshot_end_is_normalized_without_widening_dates(self):
        plan = inventory_plan()
        task = plan.tasks[0]
        task.question = 'stock on hand snapshot 2022-12-31 by category'
        task.mapping.time.mode = 'snapshot'
        task.mapping.time.start = task.mapping.time.end = '2022-12-31'
        validated = validate_plan(plan, task.question)
        self.assertIsNone(validated.tasks[0].mapping.time.end)
        _, parameters = build_task_sql(validated.tasks[0])
        self.assertEqual(parameters, (date(2022, 12, 31),))
        task.mapping.time.end = '2023-01-31'
        with self.assertRaises(ValueError):
            validate_plan(plan, task.question)

    def test_exact_snapshot_is_bound_as_date_for_the_database_driver(self):
        plan = inventory_plan()
        plan.tasks[0].question = 'stock on hand snapshot 2022-01-31 by category'
        plan.tasks[0].mapping.time.mode = 'snapshot'
        plan.tasks[0].mapping.time.start = '2022-01-31'
        sql, parameters = build_task_sql(validate_plan(plan, plan.tasks[0].question).tasks[0])
        self.assertEqual(parameters, (date(2022, 1, 31),))
        self.assertIn('$1', sql)

    def test_invented_filter_threshold_is_rejected(self):
        plan = inventory_plan()
        from core.analytics.metric_mapping import MetricFilter
        plan.tasks[0].mapping.filters.append(MetricFilter(field='stock_on_hand', operator='lt', value=10))
        with self.assertRaises(ValueError):
            validate_plan(plan, 'Report stock on hand latest snapshot by category')

    def test_report_sql_rejects_unapproved_tables(self):
        with self.assertRaises(ValueError):
            validate_commerce_sql('SELECT u.password FROM auth.users u LIMIT 200')

    def test_vietnamese_request_keeps_catalog_scope(self):
        plan = validate_plan(inventory_plan(), 'Báo cáo tồn kho mới nhất theo category')
        self.assertEqual(plan.tasks[0].mapping.metrics, ['stock_on_hand'])

    def test_unavailable_dimension_requires_scoped_confirmation(self):
        plan = validate_plan(inventory_plan(), 'stock on hand latest snapshot by warehouse')
        self.assertTrue(any('warehouse' in note for note in plan.unsupported_requirements))

    def test_missing_original_snapshot_is_not_silently_replaced(self):
        with self.assertRaises(ValueError):
            validate_plan(inventory_plan(), 'stock on hand by category')

    def test_catalog_aggregate_is_computed_before_limit(self):
        plan = validate_plan(inventory_plan(), 'stock on hand latest snapshot by category')
        sql, parameters = build_task_sql(plan.tasks[0])
        self.assertIn('SUM(', sql)
        self.assertIn('GROUP BY', sql)
        self.assertIn('ORDER BY', sql)
        self.assertIn('LIMIT 200', sql)
        self.assertEqual(parameters, ())

    def test_unresolved_metric_cannot_become_executable(self):
        plan = inventory_plan()
        plan.tasks[0].mapping.metrics = ['safety_stock']
        with self.assertRaises(ValueError):
            validate_plan(plan, 'safety stock latest snapshot')

    def test_unknown_task_and_omitted_metric_rejected(self):
        plan = inventory_plan()
        plan.sections[0].tasks = ['missing']
        with self.assertRaises(ValueError):
            validate_plan(plan, 'stock on hand latest snapshot')

    def test_product_query_is_restricted_and_parameterized(self):
        plan = ReportPlan.model_validate({'purpose': 'Products', 'tasks': [{
            'id': 'products', 'question': 'List products', 'product_columns': ['product_id', 'product_name'],
            'product_filters': [{'field': 'category', 'operator': 'eq', 'value': "x'; DROP TABLE products;--"}],
        }], 'sections': [{'heading': 'Products', 'tasks': ['products']}]})
        sql, parameters = build_task_sql(validate_plan(plan, "List products in category x'; DROP TABLE products;--").tasks[0])
        self.assertNotIn('DROP', sql)
        self.assertIn('$1', sql)
        self.assertEqual(len(parameters), 1)


if __name__ == '__main__':
    unittest.main()
