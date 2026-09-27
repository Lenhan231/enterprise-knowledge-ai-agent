from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scripts.ingest_vietnam_enterprise_corpus import ingest_one_document


class SeedIngestionPipelineTest(unittest.TestCase):
    def setUp(self):
        self.item = {
            "document_id": "VNM-AR-2024-VI", "ticker": "VNM",
            "company": "Vinamilk JSC", "domain": "finance", "title": "Annual report",
            "document_type": "annual_report", "fiscal_year": 2024, "language": "vi",
            "year_or_version": "2024", "official_url": "https://example.test/report.pdf",
            "rbac": {"classification": "public", "allowed_roles": ["employee"]},
        }
        self.input_path = Path("report.pdf")
        self.chunk = SimpleNamespace(
            page_content="Net revenue 100",
            metadata={"chunk_index": 0, "page_number": 1},
        )
        self.ingestor = Mock()
        self.ingestor.ingestion.return_value = ([self.chunk], [{"page_number": 1, "table_index": 0}])
        self.embeddings = Mock(model_name="BAAI/bge-small-en-v1.5")
        self.embeddings.embed_documents.return_value = [[0.1, 0.2]]
        self.documents = Mock()
        self.chunk_repository = Mock()

    def test_ready_is_set_only_after_chunks_and_tables_persist(self):
        structured_store = MagicMock()
        structured_store.save_document_tables.return_value = (1, 2)
        timeline = Mock()
        timeline.attach_mock(self.documents, "documents")
        timeline.attach_mock(self.chunk_repository, "chunks")
        timeline.attach_mock(structured_store, "tables")
        with patch("scripts.ingest_vietnam_enterprise_corpus.StructuredDataStore", return_value=structured_store):
            counts = ingest_one_document(
                self.item, self.input_path, Path("processed"), self.ingestor,
                self.embeddings, self.documents, self.chunk_repository,
            )

        self.assertEqual(counts, (1, 1, 2))
        upsert = self.documents.upsert_document.call_args.args[0]
        self.assertEqual(upsert["processing_status"], "processing")
        calls = [call[0] for call in timeline.mock_calls]
        self.assertLess(calls.index("documents.upsert_document"), calls.index("chunks.replace_document"))
        self.assertLess(calls.index("chunks.replace_document"), calls.index("tables.save_document_tables"))
        self.assertLess(calls.index("tables.save_document_tables"), calls.index("documents.update_processing_status"))
        self.assertEqual(self.documents.update_processing_status.call_args.args, ("VNM-AR-2024-VI", "ready"))
        self.chunk_repository.replace_document.assert_called_once()
        structured_store.save_document_tables.assert_called_once()
        structured_store.close.assert_called_once()

    def test_failed_table_persistence_keeps_document_unsearchable(self):
        structured_store = MagicMock()
        structured_store.save_document_tables.side_effect = RuntimeError("table insert failed")
        with patch("scripts.ingest_vietnam_enterprise_corpus.StructuredDataStore", return_value=structured_store):
            with self.assertRaisesRegex(RuntimeError, "table insert failed"):
                ingest_one_document(
                    self.item, self.input_path, Path("processed"), self.ingestor,
                    self.embeddings, self.documents, self.chunk_repository,
                )

        self.assertEqual(
            [call.args for call in self.documents.update_processing_status.call_args_list],
            [("VNM-AR-2024-VI", "failed")],
        )
        self.assertEqual(self.documents.upsert_document.call_args.args[0]["processing_status"], "processing")
        self.assertNotIn("ready", [call.args[1] for call in self.documents.update_processing_status.call_args_list])
        structured_store.close.assert_called_once()

    def test_empty_extraction_is_marked_failed_without_embedding(self):
        self.ingestor.ingestion.return_value = ([], [])
        with self.assertRaisesRegex(ValueError, "No text chunks"):
            ingest_one_document(
                self.item, self.input_path, Path("processed"), self.ingestor,
                self.embeddings, self.documents, self.chunk_repository,
            )
        self.embeddings.embed_documents.assert_not_called()
        self.documents.update_processing_status.assert_called_once_with("VNM-AR-2024-VI", "failed")


if __name__ == "__main__":
    unittest.main()
