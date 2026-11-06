import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.analytics.metric_mapping import decode_metric_mapping, compile_inventory_query, validate_mapped_sql
from core.analytics.metric_validation import MetricDefinitionError
from core.analytics.text_to_sql import decode_query_plan


CHANGE = 'How did stock_on_hand change between November 30 and December 31, 2022, for products present on both dates?'
SNAPSHOT = 'Show the historical inventory snapshot metrics for DragonWear MA-08 (product_id 8) on 2022-12-31.'


class SnapshotContractsTest(unittest.TestCase):
    def comparison(self):
        return decode_metric_mapping(json.dumps(dict(metrics=['stock_on_hand'], dimensions=['product_id'],
            representation='product', time=dict(mode='comparison', start='2022-11-30', end='2022-12-31'))), CHANGE)

    def test_comparison_keeps_intersection_direction_and_null_observations(self):
        mapping = self.comparison()
        sql, params = compile_inventory_query(mapping)
        from datetime import date
        self.assertTrue(all(isinstance(value, date) for value in params[:-1]))
        connection = sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        connection.execute("ATTACH DATABASE ':memory:' AS commerce")
        connection.executescript('CREATE TABLE commerce.products(product_id INTEGER PRIMARY KEY);'
            'CREATE TABLE commerce.inventory(product_id INTEGER,snapshot_date TEXT,stock_on_hand INTEGER);'
            'INSERT INTO commerce.products VALUES(1),(2),(3),(4);'
            "INSERT INTO commerce.inventory VALUES(1,'2022-11-30',8),(1,'2022-12-31',3),"
            "(2,'2022-11-30',NULL),(2,'2022-12-31',9),(3,'2022-11-30',7),(4,'2022-12-31',5);")
        from sqlglot import parse_one
        query = parse_one(sql, read='postgres').sql(dialect='sqlite')
        rows = connection.execute(query, {str(i): v.isoformat() if hasattr(v, 'isoformat') else v
                                         for i, v in enumerate(params, 1)}).fetchall()
        self.assertEqual(rows, [(1, 8, 3, -5), (2, None, 9, None)])

    def test_comparison_rejects_changed_population_dates_and_operands(self):
        mapping = self.comparison()
        sql, params = compile_inventory_query(mapping)
        for changed in (sql.replace(' - ', ' + '), sql.replace('COUNT(DISTINCT', 'COUNT('), sql.replace('LIMIT 200', 'LIMIT 10')):
            with self.subTest(sql=changed), self.assertRaises(MetricDefinitionError):
                validate_mapped_sql(decode_query_plan(json.dumps({'sql': changed, 'parameters': params}, default=str)), mapping)

    def test_snapshot_bundle_contains_each_approved_stored_measure(self):
        mapping = decode_metric_mapping(json.dumps(dict(metrics=['stock_on_hand'], dimensions=['product_id'],
            representation='product', time=dict(mode='snapshot', start='2022-12-31'),
            filters=[dict(field='product_id', operator='eq', value=8)])), SNAPSHOT)
        sql, params = compile_inventory_query(mapping)
        from sqlglot import parse_one
        fields = {p.unalias().name for p in parse_one(sql, read='postgres').selects}
        self.assertEqual(fields, {'snapshot_date', 'product_id', 'stock_on_hand', 'units_received', 'units_sold',
            'stockout_days', 'days_of_supply', 'fill_rate', 'stockout_flag', 'overstock_flag', 'reorder_flag', 'sell_through_rate'})
        self.assertIn(8, params)
        self.assertNotIn('GROUP BY', sql)

    def test_snapshot_bundle_still_rejects_wrong_filter_types(self):
        for field, value in [('product_id', '8'), ('stockout_indicator', 'true')]:
            with self.subTest(field=field), self.assertRaises(MetricDefinitionError):
                decode_metric_mapping(json.dumps(dict(metrics=['stock_on_hand'], dimensions=['product_id'],
                    representation='product', time=dict(mode='snapshot', start='2022-12-31'),
                    filters=[dict(field=field, operator='eq', value=value)])), SNAPSHOT)


class ComparisonAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_comparison_runs_through_shared_agent(self):
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest, VerifiedIdentity
        provider, repository = Mock(), AsyncMock()
        provider.generate.return_value = json.dumps(dict(metrics=['stock_on_hand'], dimensions=['product_id'],
            representation='product', time=dict(mode='comparison', start='2022-11-30', end='2022-12-31')))
        repository.execute_approved_query.return_value = [{'product_id': 1, 'stock_before': 8, 'stock_after': 3, 'stock_delta': -5}]
        result = await SQLAnalyticsAgent(repository, llm=provider).run(AgentRequest(question=CHANGE,
            identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'})))
        self.assertEqual(result.metadata['execution_status'], 'executed', result.answer)
        self.assertEqual(result.data['rows'][0]['stock_delta'], -5)
        self.assertEqual(result.metadata['snapshot_dates'], ['2022-11-30', '2022-12-31'])
        self.assertNotIn('No matching inventory observations', str(result.metadata['limitations']))


class IncrementalBenchmarkTest(unittest.TestCase):
    def test_three_case_overlay_retains_other_27_and_records_revisions(self):
        from evaluation.summarize_sql_semantic_pair import merge_incremental, completed
        from evaluation import run_inventory_agents_benchmark as benchmark
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            base, updates, merged = [Path(folder)/name for name in ('base','updates','merged')]
            ids = [f'S{i:02}' for i in range(1,31)]
            replacements = ['S13','S15','S17']
            for directory, selected, revision in ((base,ids,'before'),(updates,replacements,'after')):
                (directory/'sql_analytics').mkdir(parents=True)
                benchmark.save(directory/'manifest.json', dict(sql_ids=selected, application_revision=revision, judge='unchanged'))
                for name, contents in (('references.json',json.dumps({key:{'supported':True} for key in ids})),
                                       ('questions.jsonl','frozen'), ('identity-counts.json','{}')):
                    (directory/'sql_analytics'/name).write_text(contents, encoding='utf-8')
                for key in selected:
                    benchmark.append(directory/'sql_analytics/generations.jsonl',dict(id=key, attempt=1, elapsed_seconds=1,
                        result=dict(metadata={},data=dict(query_status='executed',rows=[])), revision=revision))
                    for metric in benchmark.METRICS['sql_analytics']:
                        benchmark.append(directory/'sql_analytics/scores.jsonl',dict(id=key,metric=metric,score=int(revision=='after'),
                            error=None,scoring_revision=4,generation_attempt=1))
            original = (base/'sql_analytics/generations.jsonl').read_bytes()
            with patch('evaluation.run_sql_contract_benchmark.FROZEN',base):
                merge_incremental(base,updates,merged)
                rows,scores,summary = completed(merged)
            self.assertEqual(len(rows),30)
            self.assertEqual(len(scores),90)
            self.assertEqual(sum(row['revision']=='before' for row in rows.values()),27)
            self.assertEqual(summary['metrics']['execution_accuracy']['mean'],0.1)
            self.assertEqual((base/'sql_analytics/generations.jsonl').read_bytes(),original)
            manifest = json.loads((merged/'manifest.json').read_text())
            self.assertEqual(manifest['case_provenance']['S13']['application_revision'],'after')
            self.assertEqual(manifest['case_provenance']['S14']['application_revision'],'before')
            with self.assertRaisesRegex(AssertionError,'new directory'):
                merge_incremental(base,updates,merged)
