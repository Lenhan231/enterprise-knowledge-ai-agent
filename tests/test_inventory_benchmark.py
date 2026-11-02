import unittest
from evaluation.inventory_benchmark_metrics import compare_rows, numeric_equal, sql_numerical_accuracy, numeric_claim_score


class BenchmarkMetricsTests(unittest.TestCase):
    def test_numeric_tolerance_and_null(self):
        self.assertTrue(numeric_equal('0.3', '0.30000001'))
        self.assertFalse(numeric_equal(None, 0))
        self.assertFalse(numeric_equal(True, 1))

    def test_rows_ignore_order_but_preserve_scope_and_duplicates(self):
        gold = [{'product_id': 1, 'stock': 10}, {'product_id': 2, 'stock': 20}]
        self.assertTrue(compare_rows(list(reversed(gold)), gold))
        self.assertFalse(compare_rows([{'product_id': 2, 'stock': 10}, {'product_id': 1, 'stock': 20}], gold))
        self.assertFalse(compare_rows([gold[0], gold[0]], gold))
        self.assertFalse(compare_rows([{'product_id': 1, 'stock': 10}], gold))

    def test_numerical_scores_require_matching_entity_and_penalize_missing_rows(self):
        gold = [{'product_id': 1, 'stock': 10}, {'product_id': 2, 'stock': 20}]
        self.assertEqual(sql_numerical_accuracy([gold[0]], gold), 0.5)
        self.assertEqual(sql_numerical_accuracy([{'product_id': 2, 'stock': 10}, {'product_id': 1, 'stock': 20}], gold), 0)
        self.assertIsNone(sql_numerical_accuracy([], []))

    def test_parameter_binding_does_not_confuse_multidigit_placeholders(self):
        from evaluation.run_inventory_agents_benchmark import bind_sql
        sql = bind_sql('SELECT $1,$10,$2', ["a'b", None, 3, 4, 5, 6, 7, 8, 9, True])
        self.assertEqual(sql, "SELECT 'a''b',TRUE,NULL")

    def test_report_numeric_claims_reject_wrong_scope_and_unsupported_values(self):
        claims=[{'dimension_metric_date_unit_match':True,'response_value':'0.25','reference_value':'0.25'},
                {'dimension_metric_date_unit_match':False,'response_value':'100','reference_value':'100'},
                {'dimension_metric_date_unit_match':True,'response_value':'0','reference_value':None}]
        self.assertEqual(numeric_claim_score(claims),(1/3,1))
        self.assertEqual(numeric_claim_score([]),(None,0))

    def test_dataset_split_and_reference_coverage(self):
        import hashlib
        import json
        from evaluation.run_inventory_agents_benchmark import OUT, load_cases
        from evaluation.inventory_benchmark_references import SQL, REPORT_TASKS
        all_cases = [case for group in ('knowledge','sql_analytics','report') for case in load_cases(group)]
        self.assertEqual(len({r['id'] for r in all_cases}),90)
        manifest=json.loads((OUT/'manifest.json').read_text())
        self.assertEqual(hashlib.sha256((OUT/'source-dataset.jsonl').read_bytes()).hexdigest(),manifest['source_sha256'])
        self.assertEqual(set(SQL),{f'S{i:02d}' for i in range(1,29)})
        self.assertEqual(set(REPORT_TASKS),{r['id'] for r in load_cases('report')})


if __name__ == '__main__':
    unittest.main()
