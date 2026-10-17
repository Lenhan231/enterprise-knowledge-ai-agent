import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.database.upload_test_repository import UploadTestRepository


class UploadTestRepositoryTest(unittest.TestCase):
    def test_save_run_persists_pipeline_outputs_atomically(self):
        repository = UploadTestRepository.__new__(UploadTestRepository)
        repository.connection = MagicMock()
        run_id = uuid.uuid4()

        repository.save_run(
            run_id,
            source_filename="scan.pdf",
            source_sha256="a" * 64,
            uploaded_by="tester",
            processor_config={"tesseract_psm": 11},
            runtime_info={"tesseract": "5.5"},
            page_previews=[b"png-page-1"],
            chunks=[{"text": "OCR content", "metadata": {"page_number": 1, "section_title": "Assets"}}],
            tables=[{
                "page_number": 1, "columns": ["label"], "rows": [{"label": "Cash"}],
                "context": {"table_title": "Consolidated balance sheet"},
                "metadata": {"filename": "scan.pdf", "source_sha256": "a" * 64, "table_extraction_method": "test"},
            }],
            token_bounded_chunks=[{"text": "Final text", "metadata": {"page_number": 1, "token_count": 2}}],
            embeddings=[[0.1, 0.2]],
            embedding_status="embedded",
        )

        repository.connection.transaction.assert_called_once_with()
        cursor = repository.connection.cursor.return_value.__enter__.return_value
        self.assertEqual(cursor.execute.call_args.args[1][0], run_id)
        self.assertEqual(len(cursor.executemany.call_args_list), 5)
        preview_rows = cursor.executemany.call_args_list[0].args[1]
        chunk_rows = cursor.executemany.call_args_list[1].args[1]
        table_rows = cursor.executemany.call_args_list[2].args[1]
        record_rows = cursor.executemany.call_args_list[3].args[1]
        token_rows = cursor.executemany.call_args_list[4].args[1]
        self.assertEqual(preview_rows, [(run_id, 1, b"png-page-1")])
        self.assertEqual(chunk_rows[0][2], "OCR content")
        self.assertEqual(chunk_rows[0][3].obj, {"page_number": 1, "section_title": "Assets"})
        self.assertEqual(table_rows[0][3].obj, ["label"])
        self.assertEqual(table_rows[0][4].obj["source_filename"], "scan.pdf")
        self.assertEqual(table_rows[0][4].obj["section_title"], "Assets")
        self.assertEqual(table_rows[0][4].obj["table_title"], "Consolidated balance sheet")
        self.assertEqual(table_rows[0][5].obj, {"table_extraction_method": "test"})
        self.assertEqual(record_rows[0][:3], (run_id, 0, 0))
        self.assertEqual(record_rows[0][3].obj, {"label": "Cash"})
        self.assertEqual(token_rows[0][2], "Final text")
        self.assertEqual(token_rows[0][3].obj, {"page_number": 1, "token_count": 2})

    def test_save_pre_embedding_chunks_without_vectors(self):
        repository = UploadTestRepository.__new__(UploadTestRepository)
        repository.connection = MagicMock()
        repository.save_run(
            uuid.uuid4(), source_filename="scan.pdf", source_sha256="b" * 64,
            uploaded_by="tester", processor_config={}, runtime_info={},
            page_previews=[b"page"], chunks=[], tables=[],
            token_bounded_chunks=[{"text": "Ready for embedding", "metadata": {}}],
            embeddings=[], embedding_status="not_run",
        )
        cursor = repository.connection.cursor.return_value.__enter__.return_value
        token_rows = cursor.executemany.call_args_list[-1].args[1]
        self.assertEqual(token_rows[0][2], "Ready for embedding")
        self.assertIsNone(token_rows[0][4])


if __name__ == "__main__":
    unittest.main()
