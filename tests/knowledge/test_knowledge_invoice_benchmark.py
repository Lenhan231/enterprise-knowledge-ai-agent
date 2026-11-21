import json
from pathlib import Path
import tempfile
import unittest

from evaluation.knowledge_invoice_cases import KNOWLEDGE, INVOICES
from evaluation.run_knowledge_invoice_benchmark import immutable_json, append_once, citation_audit


class BenchmarkIntegrityTest(unittest.TestCase):
    def test_frozen_cases_cover_exactly_thirty_and_ten_questions(self):
        self.assertEqual((len(KNOWLEDGE), len(INVOICES)), (30, 10))
        self.assertEqual(len({case[0] for case in KNOWLEDGE}), 30)
        self.assertTrue(all(reference and pages for _, reference, pages in KNOWLEDGE))

    def test_frozen_file_and_failed_record_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            immutable_json(path, {'version': 1})
            immutable_json(path, {'version': 1})
            with self.assertRaises(ValueError):
                immutable_json(path, {'version': 2})
            records = path.with_suffix('.jsonl')
            append_once(records, {'id': 'K01', 'error': 'timeout'}, ('id',))
            with self.assertRaises(ValueError):
                append_once(records, {'id': 'K01', 'score': 1}, ('id',))
            self.assertEqual(json.loads(records.read_text())['error'], 'timeout')

    def test_citation_locations_are_not_confused_with_entailment(self):
        contexts = [{'source_id': 'S1', 'metadata': {'page_number': 27}}]
        audit = citation_audit('Answer [S1] [S9]', contexts, [25], False)
        self.assertEqual(audit['citation_validity'], .5)
        self.assertEqual(audit['expected_page_precision'], 1)
        self.assertEqual(audit['unknown_citations'], ['S9'])
        self.assertIsNone(citation_audit('No evidence', [], [], True)['citation_validity'])
