import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation import run_sql_contract_benchmark as runner


class FrozenContractBenchmarkTest(unittest.TestCase):
    def test_provider_retry_does_not_include_database_or_semantic_failures(self):
        from evaluation.run_inventory_agents_benchmark import provider_failed
        def row(status,error):
            return {'result':{'metadata':{'execution_status':status,'error_type':error}}}
        self.assertTrue(provider_failed(row('planning_failed','APIConnectionError')))
        self.assertTrue(provider_failed(row('planning_failed','RateLimitError')))
        self.assertFalse(provider_failed(row('source_failed','ConnectionError')))
        self.assertFalse(provider_failed(row('validation_failed','SQLValidationError')))
        self.assertFalse(provider_failed(row('executed',None)))
        from evaluation.run_inventory_agents_benchmark import metric_provider_failed
        self.assertTrue(metric_provider_failed({'error':'Codex judge: hit your usage limit'}))
        self.assertTrue(metric_provider_failed({'error':'APIConnectionError'}))
        self.assertFalse(metric_provider_failed({'error':'ValueError: missing column'}))
        self.assertFalse(metric_provider_failed({'error':None}))

    def test_prepare_reuses_exact_frozen_inputs_and_rejects_changes(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runner,'OUTPUT',Path(folder)), patch.object(
                runner.benchmark,'OUT',runner.benchmark.OUT):
            runner.prepare()
            runner.prepare()
            manifest=json.loads((Path(folder)/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(len(manifest['sql_ids']),30)
            self.assertEqual(set(manifest['report_ids']),runner.REPORT_IDS)
            self.assertTrue({'R16','R28'} <= runner.REPORT_IDS)
            changed={**manifest,'application_source_sha256':{}}
            (Path(folder)/'manifest.json').write_text(json.dumps(changed),encoding='utf-8')
            runner.prepare(check_application=False)
            with self.assertRaisesRegex(ValueError,'Application changed'):
                runner.prepare()
            target=Path(folder)/'sql_analytics/references.json'
            self.assertEqual(target.read_bytes(),(runner.FROZEN/'sql_analytics/references.json').read_bytes())
            target.write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Frozen input mismatch'):
                runner.prepare()
