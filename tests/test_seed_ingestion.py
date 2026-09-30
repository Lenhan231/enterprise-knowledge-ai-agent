import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.document_processing.ingest_documents import Ingestion


class SeedIngestionTest(unittest.TestCase):
    def test_html_seed_ingestion_preserves_manifest_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            html_path = Path(directory) / "policy.html"
            html_path.write_text("<main><h1>Policy</h1><p>Requirements apply.</p></main>", encoding="utf-8")
            expected = {
                "company": "Vinamilk JSC", "document_type": "operating_policy",
                "source_type": "public_enterprise_document", "language": "en",
                "allowed_roles": ["operations"],
            }
            with patch("core.document_processing.ingest_documents.TokenCounter") as counter, \
                 patch("core.document_processing.ingest_documents.SemanticDocumentChunker") as chunker:
                counter.return_value.count.side_effect = lambda text: len(text.split())
                counter.return_value.split_text.side_effect = lambda text, **kwargs: [text]
                chunker.return_value.chunk_text.return_value = [
                    type("Chunk", (), {"page_content": "Policy Requirements apply."})()
                ]
                ingestor = Ingestion(embedding_service=type("Embedding", (), {"model_name": "test"})())
                chunks = ingestor.ingestion(
                    html_path, Path(directory) / "processed", extra_metadata=expected,
                )

            self.assertEqual(len(chunks), 1)
            for key, value in expected.items():
                self.assertEqual(chunks[0].metadata[key], value)

    def test_pdf_ingestion_can_return_extracted_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "report.pdf"
            pdf_path.write_bytes(b"pdf")
            tables = [{"page_number": 1, "table_index": 0, "columns": ["Revenue"], "rows": []}]
            parsed = {"chunks": [{"text": "Revenue 60", "metadata": {
                "page_number": 1, "section_title": "Financial performance", "layout_type": "text",
            }}], "tables": tables}

            with patch("core.document_processing.ingest_documents.TokenCounter") as counter, \
                 patch("core.document_processing.ingest_documents.SemanticDocumentChunker"), \
                 patch("core.document_processing.ingest_documents.PDFProcessor") as processor:
                counter.return_value.count.return_value = 2
                counter.return_value.split_text.side_effect = lambda text, **kwargs: [text]
                processor.return_value.process.return_value = parsed
                ingestor = Ingestion(embedding_service=type("Embedding", (), {"model_name": "test"})())

                chunks, extracted_tables = ingestor.ingestion(
                    pdf_path, Path(directory) / "processed", document_id="DOC-1", include_tables=True
                )

            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].page_content, "Revenue 60")
            self.assertEqual(chunks[0].metadata["section_title"], "Financial performance")
            self.assertEqual(chunks[0].metadata["layout_type"], "text")
            self.assertEqual(extracted_tables, tables)
            processor.assert_called_once()
            self.assertTrue(processor.call_args.args[0]["extract_tables"])
            self.assertEqual(processor.call_args.args[0]["chunking_strategy"], "sentence")

    def test_existing_ingestion_callers_still_receive_chunks_only(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "report.pdf"
            pdf_path.write_bytes(b"pdf")
            parsed = {"chunks": [{"text": "Revenue 60", "metadata": {"page_number": 1}}], "tables": []}

            with patch("core.document_processing.ingest_documents.TokenCounter") as counter, \
                 patch("core.document_processing.ingest_documents.SemanticDocumentChunker"), \
                 patch("core.document_processing.ingest_documents.PDFProcessor") as processor:
                counter.return_value.count.return_value = 2
                counter.return_value.split_text.side_effect = lambda text, **kwargs: [text]
                processor.return_value.process.return_value = parsed
                ingestor = Ingestion(embedding_service=type("Embedding", (), {"model_name": "test"})())

                result = ingestor.ingestion(pdf_path, Path(directory) / "processed", document_id="DOC-1")

            self.assertIsInstance(result, list)
            self.assertEqual(result[0].page_content, "Revenue 60")

    def test_token_split_assigns_unique_chunk_indices_after_page_metadata_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "report.pdf"
            pdf_path.write_bytes(b"pdf")
            parsed = {
                "chunks": [{"text": "Revenue 60", "metadata": {"page_number": 1, "chunk_index": 0}}],
                "tables": [],
            }

            with patch("core.document_processing.ingest_documents.TokenCounter") as counter, \
                 patch("core.document_processing.ingest_documents.SemanticDocumentChunker"), \
                 patch("core.document_processing.ingest_documents.PDFProcessor") as processor:
                counter.return_value.count.return_value = 2
                counter.return_value.split_text.return_value = ["Revenue", "60"]
                processor.return_value.process.return_value = parsed
                ingestor = Ingestion(embedding_service=type("Embedding", (), {"model_name": "test"})())

                chunks = ingestor.ingestion(pdf_path, Path(directory) / "processed", document_id="DOC-1")

            self.assertEqual([chunk.metadata["chunk_index"] for chunk in chunks], [0, 1])
            self.assertEqual([chunk.page_content for chunk in chunks], ["Revenue", "60"])


if __name__ == "__main__":
    unittest.main()
