import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.agents.decision_support.intent_classifier import select_jev_schema_tables
from core.agents.sql.join_validation import PRIMARY_KEYS
from core.agents.sql.sql_validation import APPROVED_COLUMNS, APPROVED_JOINS


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

        with patch('core.agents.decision_support.intent_classifier.os.getenv', return_value='test-key'), patch(
                'core.agents.decision_support.intent_classifier.urllib.request.urlopen', return_value=io.BytesIO(payload)) as urlopen:
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

    def test_supporting_inventory_candidate_is_not_in_sql_schema(self):
        required = {'commerce.order_items', 'commerce.orders', 'commerce.products'}
        supporting = {'commerce.inventory', 'commerce.customers'}
        scores = {**{table: 2 for table in required}, **{table: 1 for table in supporting}}
        answers = {
            f'table_{index}': {
                'type': 'score', 'score': scores.get(table, 0), 'confidence': 1,
            }
            for index, table in enumerate(sorted(APPROVED_COLUMNS))
        }
        payload = json.dumps({'answers': answers}).encode()

        with patch('core.agents.decision_support.intent_classifier.os.getenv', return_value='test-key'), patch(
                'core.agents.decision_support.intent_classifier.urllib.request.urlopen', return_value=io.BytesIO(payload)):
            selection = select_jev_schema_tables(
                'sản phẩm bán chạy nhất tháng trước', APPROVED_COLUMNS,
                primary_keys=PRIMARY_KEYS, approved_joins=APPROVED_JOINS,
            )

        self.assertTrue(supporting <= selection['candidate_tables'])
        self.assertEqual(selection['required_tables'], required)
        self.assertEqual(selection['tables'], required)

    def test_invalid_or_missing_score_is_rejected_for_full_schema_fallback(self):
        answers = {
            f'table_{index}': {'type': 'score', 'score': 0, 'confidence': 1}
            for index, _ in enumerate(sorted(APPROVED_COLUMNS))
        }
        payload = json.dumps({'answers': answers}).encode()
        with patch('core.agents.decision_support.intent_classifier.os.getenv', return_value='test-key'), patch(
                'core.agents.decision_support.intent_classifier.urllib.request.urlopen', return_value=io.BytesIO(payload)):
            with self.assertRaisesRegex(ValueError, 'did not identify'):
                select_jev_schema_tables('unknown question', APPROVED_COLUMNS)


if __name__ == '__main__':
    unittest.main()
