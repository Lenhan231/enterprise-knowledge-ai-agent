import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.intent_classifier import select_jev_schema_tables
from core.analytics.join_validation import PRIMARY_KEYS
from core.analytics.sql_validation import APPROVED_COLUMNS, APPROVED_JOINS


class JevSchemaSelectionTest(unittest.TestCase):
    def test_selects_top_five_and_expands_approved_join_bridges(self):
        primary = {
            'commerce.inventory', 'commerce.order_items', 'commerce.orders',
            'commerce.returns', 'commerce.reviews',
        }
        answers = {}
        for index, table in enumerate(sorted(APPROVED_COLUMNS)):
            answers[f'table_{index}'] = {
                'type': 'score', 'score': 2 if table in primary else 0,
                'confidence': 1,
            }
        payload = json.dumps({'answers': answers}).encode()

        with patch('core.agents.intent_classifier.os.getenv', return_value='test-key'), patch(
                'core.agents.intent_classifier.urllib.request.urlopen', return_value=io.BytesIO(payload)) as urlopen:
            selection = select_jev_schema_tables(
                'compare returned and sold quantities by product', APPROVED_COLUMNS,
                primary_keys=PRIMARY_KEYS, approved_joins=APPROVED_JOINS,
            )

        self.assertEqual(len(selection['tables'] - {'commerce.products'}), 5)
        self.assertTrue(primary <= selection['tables'])
        self.assertIn('commerce.products', selection['tables'])
        self.assertEqual(selection['required_tables'], primary)
        request = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(request['model'], 'typesafe/jev-1.14')
        self.assertEqual(len(request['questions']), len(APPROVED_COLUMNS))

    def test_invalid_or_missing_score_is_rejected_for_full_schema_fallback(self):
        answers = {
            f'table_{index}': {'type': 'score', 'score': 0, 'confidence': 1}
            for index, _ in enumerate(sorted(APPROVED_COLUMNS))
        }
        payload = json.dumps({'answers': answers}).encode()
        with patch('core.agents.intent_classifier.os.getenv', return_value='test-key'), patch(
                'core.agents.intent_classifier.urllib.request.urlopen', return_value=io.BytesIO(payload)):
            with self.assertRaisesRegex(ValueError, 'did not identify'):
                select_jev_schema_tables('unknown question', APPROVED_COLUMNS)


if __name__ == '__main__':
    unittest.main()
