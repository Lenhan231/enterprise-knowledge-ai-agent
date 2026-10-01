import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.database.processed_chunks_repository import ProcessedChunksRepository


class ProcessedChunksRepositoryTest(unittest.TestCase):
    def test_replace_document_keeps_model_specific_fields_out_of_parsed_chunks(self):
        repository = ProcessedChunksRepository.__new__(ProcessedChunksRepository)
        repository.connection = MagicMock()

        repository.replace_document("UP-1", [{
            "text": "Revenue was 100 VND.",
            "metadata": {
                "page_number": 2,
                "embedding_model": "model-a",
                "token_count": 12,
            },
        }])

        rows = repository.connection.cursor.return_value.__enter__.return_value.executemany.call_args.args[1]
        self.assertEqual(rows[0][3].obj, {"page_number": 2})

    def test_get_document_is_paginated_and_company_scoped(self):
        repository = ProcessedChunksRepository.__new__(ProcessedChunksRepository)
        repository.connection = MagicMock()
        cursor = repository.connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{"chunk_index": 3, "content": "parsed text", "metadata": {}}]

        result = repository.get_document("UP-1", limit=10, offset=20, company="Vinamilk")

        repository.connection.transaction.assert_called_once_with()
        query, parameters = cursor.execute.call_args.args
        self.assertIn("join public.documents d using(document_id)", " ".join(query.lower().split()))
        self.assertEqual(parameters, ("UP-1", "Vinamilk", "Vinamilk", 10, 20))
        self.assertEqual(result[0]["content"], "parsed text")

    def test_status_is_validated_before_database_write(self):
        repository = ProcessedChunksRepository.__new__(ProcessedChunksRepository)
        repository.connection = MagicMock()

        with self.assertRaises(ValueError):
            repository.set_status("UP-1", "ready")

        repository.connection.cursor.assert_not_called()

    def test_page_size_is_bounded(self):
        repository = ProcessedChunksRepository.__new__(ProcessedChunksRepository)
        repository.connection = MagicMock()

        with self.assertRaises(ValueError):
            repository.get_document("UP-1", limit=101)

        repository.connection.cursor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
