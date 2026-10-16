import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tools.ingestion.ingest_documents import Ingestion
from core.document_processing.processors.pdf.processor import PDFProcessor


class SeedIngestionTest(unittest.TestCase):
    def test_html_ingestion_drops_skip_links_and_anchor_table_of_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            html_path = Path(directory) / "guide.html"
            html_path.write_text(
                "<a>Skip to content</a><main><div id='anchor-menu'>"
                "<h2>On this page</h2><a>1. Choose a tracking system</a></div>"
                "<article><h1>Manage inventory</h1><p>Use reorder points.</p></article></main>",
                encoding="utf-8",
            )
            with patch("tools.ingestion.ingest_documents.TokenCounter") as counter, \
                 patch("tools.ingestion.ingest_documents.SemanticDocumentChunker"), \
                 patch("tools.ingestion.ingest_documents.split_text", side_effect=lambda text, **kwargs: [text]) as splitter:
                counter.return_value.count.side_effect = lambda text: len(text.split())
                counter.return_value.split_text.side_effect = lambda text, **kwargs: [text]
                ingestor = Ingestion(embedding_service=type("Embedding", (), {"model_name": "test"})())
                chunks = ingestor.ingestion(html_path, Path(directory) / "processed")

            extracted = splitter.call_args.args[0]
            self.assertIn("Manage inventory", extracted)
            self.assertIn("Use reorder points.", extracted)
            self.assertNotIn("Skip to content", extracted)
            self.assertNotIn("On this page", extracted)
            self.assertNotIn("Choose a tracking system", extracted)
            self.assertEqual(chunks[0].page_content, extracted)
            self.assertEqual(chunks[0].metadata["section_title"], "Manage inventory")

    def test_html_ingestion_keeps_chunks_within_their_heading_section(self):
        with tempfile.TemporaryDirectory() as directory:
            html_path = Path(directory) / "guide.html"
            html_path.write_text(
                "<article><h1>Guide</h1><h2>Choose options</h2>"
                "<p>Compare speed and cost.</p><h2>Evaluate providers</h2>"
                "<p>Check coverage.</p></article>",
                encoding="utf-8",
            )
            with patch("tools.ingestion.ingest_documents.TokenCounter") as counter, \
                 patch("tools.ingestion.ingest_documents.SemanticDocumentChunker"), \
                 patch(
                     "tools.ingestion.ingest_documents.split_text",
                     side_effect=lambda text, **kwargs: [text],
                 ):
                counter.return_value.count.side_effect = lambda text: len(text.split())
                counter.return_value.split_text.side_effect = lambda text, **kwargs: [text]
                ingestor = Ingestion(embedding_service=type("Embedding", (), {"model_name": "test"})())
                chunks = ingestor.ingestion(html_path, Path(directory) / "processed")

            self.assertEqual(
                [chunk.metadata["section_title"] for chunk in chunks],
                ["Choose options", "Evaluate providers"],
            )
            self.assertIn("Compare speed and cost.", chunks[0].page_content)
            self.assertIn("Check coverage.", chunks[1].page_content)
            self.assertNotIn("Check coverage.", chunks[0].page_content)

    def test_html_seed_ingestion_preserves_manifest_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            html_path = Path(directory) / "policy.html"
            html_path.write_text("<main><h1>Policy</h1><p>Requirements apply.</p></main>", encoding="utf-8")
            expected = {
                "company": "Example Retailer JSC", "document_type": "operating_policy",
                "source_type": "public_enterprise_document", "language": "en",
                "allowed_roles": ["operations"],
            }
            with patch("tools.ingestion.ingest_documents.TokenCounter") as counter, \
                 patch("tools.ingestion.ingest_documents.SemanticDocumentChunker") as chunker, \
                 patch("tools.ingestion.ingest_documents.split_text", return_value=["Policy Requirements apply."]) as splitter:
                counter.return_value.count.side_effect = lambda text: len(text.split())
                counter.return_value.split_text.side_effect = lambda text, **kwargs: [text]
                ingestor = Ingestion(embedding_service=type("Embedding", (), {"model_name": "test"})())
                chunks = ingestor.ingestion(
                    html_path, Path(directory) / "processed", extra_metadata=expected,
                )

            self.assertEqual(len(chunks), 1)
            for key, value in expected.items():
                self.assertEqual(chunks[0].metadata[key], value)
            chunker.return_value.chunk_text.assert_not_called()
            splitter.assert_called_once_with(
                "Policy\nRequirements apply.", size=1200, overlap=150, strategy="sentence",
            )

    def test_pdf_ingestion_can_return_extracted_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "report.pdf"
            pdf_path.write_bytes(b"pdf")
            tables = [{"page_number": 1, "table_index": 0, "columns": ["Revenue"], "rows": []}]
            parsed = {"chunks": [{"text": "Revenue 60", "metadata": {
                "page_number": 1, "section_title": "Financial performance", "layout_type": "text",
            }}], "tables": tables}

            with patch("tools.ingestion.ingest_documents.TokenCounter") as counter, \
                 patch("tools.ingestion.ingest_documents.SemanticDocumentChunker"), \
                 patch("tools.ingestion.ingest_documents.PDFProcessor") as processor:
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

    def test_pdf_seed_ingestion_uses_shared_ocr_scale_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "report.pdf"
            pdf_path.write_bytes(b"pdf")
            parsed = {"chunks": [{"text": "Scanned page", "metadata": {"page_number": 1}}], "tables": []}
            with (
                patch.dict("os.environ", {
                    "DOCUMENT_OCR_RENDER_SCALE": "3.5",
                    "DOCUMENT_OCR_TABLE_RENDER_SCALE": "3.5",
                }),
                patch("tools.ingestion.ingest_documents.TokenCounter") as counter,
                patch("tools.ingestion.ingest_documents.SemanticDocumentChunker"),
                patch.object(PDFProcessor, "process", autospec=True, return_value=parsed) as process_pdf,
            ):
                counter.return_value.count.return_value = 2
                counter.return_value.split_text.side_effect = lambda text, **kwargs: [text]
                ingestor = Ingestion(embedding_service=type("Embedding", (), {"model_name": "test"})())
                chunks = ingestor.ingestion(pdf_path, Path(directory) / "processed")

            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].page_content, "Scanned page")
            self.assertEqual(process_pdf.call_args.args[0].config["ocr_render_scale"], 3.5)
            self.assertEqual(process_pdf.call_args.args[0].config["ocr_table_render_scale"], 3.5)

    def test_existing_ingestion_callers_still_receive_chunks_only(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "report.pdf"
            pdf_path.write_bytes(b"pdf")
            parsed = {"chunks": [{"text": "Revenue 60", "metadata": {"page_number": 1}}], "tables": []}

            with patch("tools.ingestion.ingest_documents.TokenCounter") as counter, \
                 patch("tools.ingestion.ingest_documents.SemanticDocumentChunker"), \
                 patch("tools.ingestion.ingest_documents.PDFProcessor") as processor:
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

            with patch("tools.ingestion.ingest_documents.TokenCounter") as counter, \
                 patch("tools.ingestion.ingest_documents.SemanticDocumentChunker"), \
                 patch("tools.ingestion.ingest_documents.PDFProcessor") as processor:
                counter.return_value.count.return_value = 2
                counter.return_value.split_text.return_value = ["Revenue", "60"]
                processor.return_value.process.return_value = parsed
                ingestor = Ingestion(embedding_service=type("Embedding", (), {"model_name": "test"})())

                chunks = ingestor.ingestion(pdf_path, Path(directory) / "processed", document_id="DOC-1")

            self.assertEqual([chunk.metadata["chunk_index"] for chunk in chunks], [0, 1])
            self.assertEqual([chunk.page_content for chunk in chunks], ["Revenue", "60"])


if __name__ == "__main__":
    unittest.main()
