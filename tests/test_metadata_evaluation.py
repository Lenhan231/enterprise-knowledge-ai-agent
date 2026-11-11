import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analytics.evaluate_corpus_metadata import (  # noqa: E402
    expected_chunk_metadata,
    expected_document_metadata,
    mismatches,
)


class CorpusMetadataEvaluationTest(unittest.TestCase):
    def setUp(self):
        self.item = {
            "document_id": "VNM-POL-1", "company": "Vinamilk JSC", "ticker": "VNM",
            "domain": "operations", "title": "Policy", "year_or_version": "2025",
            "format": "HTML", "source_url": "https://example.test",
            "verification": "Official source",
            "document_type": "operating_policy", "fiscal_year": "2025", "language": "en",
            "rbac": {"allowed_roles": ["operations"]},
        }

    def test_document_and_chunk_expected_metadata_map_manifest_fields(self):
        document = expected_document_metadata(self.item)
        chunk = expected_chunk_metadata(self.item)
        self.assertEqual(document["source_url"], "https://example.test")
        self.assertEqual(document["allowed_roles"], ["operations"])
        self.assertEqual(chunk["source_type"], "public_enterprise_document")
        self.assertEqual(chunk["language"], "en")

    def test_mismatches_detect_missing_and_wrong_values(self):
        expected = expected_chunk_metadata(self.item)
        actual = {**expected, "document_type": "html"}
        actual.pop("language")
        result = mismatches(expected, actual, ("document_type", "language"))
        self.assertEqual(result["document_type"], {"expected": "operating_policy", "actual": "html"})
        self.assertEqual(result["language"], {"expected": "en", "actual": None})


if __name__ == "__main__":
    unittest.main()
