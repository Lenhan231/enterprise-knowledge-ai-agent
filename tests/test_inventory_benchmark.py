import unittest
from evaluation.inventory_benchmark_metrics import compare_rows, numeric_equal, sql_numerical_accuracy, numeric_claim_score


class BenchmarkMetricsTests(unittest.TestCase):
    def test_numeric_tolerance_and_null(self):
        self.assertTrue(numeric_equal('0.3', '0.30000001'))
        self.assertFalse(numeric_equal(None, 0))
        self.assertFalse(numeric_equal(True, 1))
        self.assertFalse(numeric_equal('100000000', '100000001'))

    def test_rows_ignore_order_but_preserve_scope_and_duplicates(self):
        gold = [{'product_id': 1, 'stock': 10}, {'product_id': 2, 'stock': 20}]
        self.assertTrue(compare_rows(list(reversed(gold)), gold))
        self.assertFalse(compare_rows([{'product_id': 2, 'stock': 10}, {'product_id': 1, 'stock': 20}], gold))
        self.assertFalse(compare_rows([gold[0], gold[0]], gold))
        self.assertFalse(compare_rows([{'product_id': 1, 'stock': 10}], gold))
        self.assertTrue(compare_rows([],[]))
        self.assertFalse(compare_rows([],[{'product_count':0}]))

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
        self.assertEqual(numeric_claim_score([{'reference_covered':False}]),(None,0))

    def test_execution_normalization_accepts_names_and_month_labels(self):
        from evaluation.inventory_benchmark_metrics import normalize_execution_rows
        actual,gold=normalize_execution_rows([{'product_name':'A','quantity':10}],
            [{'product_id':1,'product_name':'A','quantity':10}],{1:'A'})
        self.assertTrue(compare_rows(actual,gold))
        actual,gold=normalize_execution_rows([{'product_name':'A','quantity':10}],
            [{'product_id':1,'quantity':10}],{1:'A',2:'B',3:'B'})
        self.assertTrue(compare_rows(actual,gold))
        actual,gold=normalize_execution_rows([{'product_name':'A','quantity':10}],
            [{'product_id':1,'quantity':10}],{1:'A',2:'A'})
        self.assertFalse(compare_rows(actual,gold))
        actual,gold=normalize_execution_rows([{'snapshot_date':'2022-01-31','units':10}],
            [{'month':'2022-01-01','units':10}],{})
        self.assertTrue(compare_rows(actual,gold))

    def test_semantic_reference_uses_same_ceiling_and_preserves_top_n(self):
        from evaluation.run_inventory_agents_benchmark import bounded_reference_sql
        self.assertTrue(bounded_reference_sql('SELECT COUNT(*) FROM commerce.inventory').endswith('LIMIT 200'))
        self.assertTrue(bounded_reference_sql('SELECT product_id FROM commerce.inventory LIMIT 20').endswith('LIMIT 20'))

    def test_report_provider_quota_response_is_retryable_but_validation_is_not(self):
        from evaluation.run_inventory_agents_benchmark import rate_limited
        self.assertTrue(rate_limited({'result':{'metadata':{'error_code':'provider_rate_limited'}}}))
        self.assertFalse(rate_limited({'result':{'metadata':{'error_code':'invalid_plan'}}}))
        self.assertTrue(rate_limited({'result':{'metadata':{'status':'failed',
            'source_collection':{'task_trace':[{'error_type':'RateLimitError'}]}}}}))
        self.assertFalse(rate_limited({'result':{'metadata':{'status':'partial',
            'source_collection':{'task_trace':[{'error_type':'RateLimitError'}]}}}}))

    def test_resumed_scores_must_match_the_generation_attempt(self):
        from evaluation.run_inventory_agents_benchmark import current_score
        record={'metric':'faithfulness','generation_attempt':1}
        self.assertFalse(current_score(record,{'attempt':2},'report'))
        self.assertTrue(current_score(record,{'attempt':1},'report'))
        self.assertFalse(current_score({'metric':'numerical_accuracy','numeric_revision':1},{},'report'))
        self.assertFalse(current_score({'metric':'execution_accuracy','scoring_revision':3},{},'sql_analytics'))

    def test_quota_delay_uses_groq_message_when_retry_header_is_absent(self):
        from evaluation.run_inventory_agents_benchmark import quota_retry_delay
        self.assertAlmostEqual(quota_retry_delay({},'Please try again in 19m31.152s.'),1171.152)
        self.assertAlmostEqual(quota_retry_delay({},'Please try again in 4.26s.'),4.26)
        self.assertEqual(quota_retry_delay({'retry-after':'12'},'Please try again in 4s.'),12)
        self.assertEqual(quota_retry_delay({},'Rate limited'),60)

    def test_summary_excludes_scores_for_superseded_responses(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        import evaluation.run_inventory_agents_benchmark as runner
        with TemporaryDirectory() as directory:
            root=Path(directory)
            for group in ('sql_analytics','report'):
                (root/group).mkdir()
            runner.append(root/'report/generations.jsonl',{'id':'R01','attempt':2})
            runner.append(root/'report/scores.jsonl',{'id':'R01','metric':'faithfulness',
                'generation_attempt':1,'score':1.0,'error':None})
            with patch.object(runner,'OUT',root):
                runner.summarize()
            summary=json.loads((root/'report/summary.json').read_text())
            self.assertEqual(summary['metrics']['faithfulness']['scored'],0)
            self.assertEqual(summary['metrics']['faithfulness']['pending'],30)

    def test_tertiary_key_follows_primary_and_numbered_backups_without_duplicates(self):
        from evaluation.run_inventory_agents_benchmark import benchmark_keys
        self.assertEqual(benchmark_keys({'GROQ_API_KEY':'primary','GROQ_API_KEY_2':'backup',
            'GROQ_API_KEY_RAGAS':'tertiary'}),['primary','backup','tertiary'])
        self.assertEqual(benchmark_keys({'GROQ_API_KEY':'same','GROQ_API_KEY_RAGAS':'same'}),['same'])

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
