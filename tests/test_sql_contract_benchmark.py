import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation import run_sql_contract_benchmark as runner


class FrozenContractBenchmarkTest(unittest.TestCase):
    def test_prepare_reuses_exact_frozen_inputs_and_rejects_changes(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runner,'OUTPUT',Path(folder)), patch.object(
                runner.benchmark,'OUT',runner.benchmark.OUT):
            runner.prepare()
            runner.prepare()
            manifest=json.loads((Path(folder)/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(len(manifest['sql_ids']),30)
            self.assertEqual(set(manifest['report_ids']),runner.REPORT_IDS)
            self.assertTrue({'R16','R28'} <= runner.REPORT_IDS)
            target=Path(folder)/'sql_analytics/references.json'
            self.assertEqual(target.read_bytes(),(runner.FROZEN/'sql_analytics/references.json').read_bytes())
            target.write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Frozen input mismatch'):
                runner.prepare()
