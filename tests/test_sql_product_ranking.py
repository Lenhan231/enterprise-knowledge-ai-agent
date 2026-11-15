import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.analytics.metric_mapping import requested_ranking_limit
from core.analytics.metric_validation import MetricDefinitionError, validate_metric_definitions
from core.analytics.text_to_sql import APPROVED_COLUMNS, relevant_schema_tables


class ProductRankingContractTest(unittest.TestCase):
    def test_singular_bestseller_requests_one_winner(self):
        self.assertEqual(requested_ranking_limit('sản phẩm bán chạy nhất'), 1)
        self.assertEqual(requested_ranking_limit('best-selling product'), 1)
        self.assertIsNone(requested_ranking_limit('best-selling products'))

    def test_bestseller_cue_loads_transaction_tables_into_prompt_schema(self):
        for question in ('sản phẩm bán chạy nhất', 'best-selling product'):
            tables = relevant_schema_tables(question, {}, APPROVED_COLUMNS)
            self.assertTrue({'commerce.order_items', 'commerce.orders', 'commerce.products'} <= tables)

    def test_best_selling_query_requires_quantity_rank_and_stable_tie_break(self):
        question = 'sản phẩm bán chạy nhất'
        sql = (
            'SELECT p.product_id, p.product_name, SUM(oi.quantity) AS total_quantity '
            'FROM commerce.order_items AS oi '
            'JOIN commerce.orders AS o ON oi.order_id = o.order_id '
            'JOIN commerce.products AS p ON oi.product_id = p.product_id '
            'GROUP BY p.product_id, p.product_name '
            'ORDER BY total_quantity DESC, p.product_id ASC LIMIT 1'
        )
        validate_metric_definitions(sql, set(), (), APPROVED_COLUMNS, question=question)

        with self.assertRaisesRegex(MetricDefinitionError, 'stable product_id tie-break'):
            validate_metric_definitions(
                sql.replace(', p.product_id ASC', ''), set(), (), APPROVED_COLUMNS, question=question,
            )


if __name__ == '__main__':
    unittest.main()
