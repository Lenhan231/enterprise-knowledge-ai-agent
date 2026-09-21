import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
from pydantic import ValidationError


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.database.document_chunks_repository import DocumentChunkRepository
from core.retrieval.retrieval import RetrievedChunk


class DocumentChunkRepositorySearchTest(unittest.TestCase):
    def setUp(self):
        # Exercise the real search method without connecting to PostgreSQL.
        self.repository = DocumentChunkRepository.__new__(DocumentChunkRepository)
        self.repository.conn = MagicMock()
        self.cursor = self.repository.conn.cursor.return_value.__enter__.return_value

    def test_maps_rows_preserving_full_content_metadata_and_order(self):
        text = " Full content\n" * 3000
        metadata = {"document_id": "DOC-1", "custom": {"tags": ["policy"]}}
        self.cursor.fetchall.return_value = [
            ("policy.pdf", 7, text, metadata, 0.81234),
            ("other.pdf", 0, "Other content", {"document_id": "DOC-2"}, -0.25),
        ]

        results = self.repository.similarity_search([0.1, 0.2], 2)

        self.assertTrue(all(isinstance(item, RetrievedChunk) for item in results))
        self.assertEqual(results[0].document_name, "policy.pdf")
        self.assertEqual(results[0].chunk_index, 7)
        self.assertEqual(results[0].content, text)
        self.assertEqual(results[0].metadata, metadata)
        self.assertEqual(results[0].document_id, "DOC-1")
        self.assertEqual([item.similarity_score for item in results], [0.81234, -0.25])
        self.assertEqual([item.document_name for item in results], ["policy.pdf", "other.pdf"])

    def test_query_uses_cosine_order_and_bound_parameters(self):
        self.cursor.fetchall.return_value = []

        self.repository.similarity_search([0.1, 0.2], 3)

        self.cursor.execute.assert_called_once()
        sql, parameters = self.cursor.execute.call_args.args
        normalized = " ".join(sql.split())
        self.assertIn("SELECT document_name, chunk_index, content, metadata,", normalized)
        self.assertIn("1 - (embedding <=> %s) AS similarity_score", normalized)
        self.assertIn("ORDER BY embedding <=> %s ASC, id ASC LIMIT %s", normalized)
        self.assertEqual(len(parameters), 3)
        self.assertEqual(parameters[2], 3)
        for vector in parameters[:2]:
            np.testing.assert_array_equal(vector, np.array([0.1, 0.2], dtype=np.float32))
        self.repository.conn.commit.assert_not_called()

    def test_empty_search_returns_empty_list(self):
        self.cursor.fetchall.return_value = []
        self.assertEqual(self.repository.similarity_search([0.1, 0.2], 5), [])

    def test_equal_scores_preserve_cursor_order(self):
        self.cursor.fetchall.return_value = [
            ("z.pdf", 9, "first", {"document_id": "Z"}, 0.8),
            ("a.pdf", 1, "second", {"document_id": "A"}, 0.8),
        ]
        results = self.repository.similarity_search([0.1, 0.2], 2)
        self.assertEqual([item.document_name for item in results], ["z.pdf", "a.pdf"])

    def test_missing_document_id_fails_including_null_metadata(self):
        for metadata in (None, {}, {"document_id": ""}, {"document_id": " "}):
            with self.subTest(metadata=metadata):
                self.cursor.fetchall.return_value = [("no-fallback.pdf", 0, "text", metadata, 0.5)]
                with self.assertRaisesRegex(ValidationError, "metadata.document_id"):
                    self.repository.similarity_search([0.1, 0.2], 1)

    def test_invalid_row_is_not_silently_skipped(self):
        self.cursor.fetchall.return_value = [
            ("valid.pdf", 0, "text", {"document_id": "DOC"}, 0.8),
            ("invalid.pdf", 0, "text", {}, 0.7),
        ]
        with self.assertRaisesRegex(ValidationError, "metadata.document_id"):
            self.repository.similarity_search([0.1, 0.2], 2)


if __name__ == "__main__":
    unittest.main()
