import asyncio
import io
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz

from fastapi import UploadFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app import main as app_main  # noqa: E402
from core.database.structured_store import StructuredDataStore  # noqa: E402
from core.document_processing.processors.document_processor import DocumentProcessor  # noqa: E402
from core.document_processing.processors.pdf_processor import PDFProcessor  # noqa: E402


def xlsx_with_formula() -> bytes:
    package = io.BytesIO()
    files = {
        "xl/workbook.xml": """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Finance" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        "xl/_rels/workbook.xml.rels": """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>""",
        "xl/worksheets/sheet1.xml": """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Metric</t></is></c><c r="B1" t="inlineStr"><is><t>Value</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Total</t></is></c><c r="B2"><f>SUM(B1:B1)</f><v>100</v></c></row></sheetData></worksheet>""",
    }
    with zipfile.ZipFile(package, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return package.getvalue()


def pptx_with_table() -> bytes:
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", """<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Annual results</a:t></a:r></a:p></p:txBody></p:sp>
          <a:graphicFrame><a:graphic><a:graphicData><a:tbl>
            <a:tr><a:tc><a:txBody><a:p><a:r><a:t>Year</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>Revenue</a:t></a:r></a:p></a:txBody></a:tc></a:tr>
            <a:tr><a:tc><a:txBody><a:p><a:r><a:t>2024</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>100 VND</a:t></a:r></a:p></a:txBody></a:tc></a:tr>
          </a:tbl></a:graphicData></a:graphic></a:graphicFrame></p:spTree></p:sld>""")
    return package.getvalue()


def borderless_financial_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=600, height=400)
    for text, x, y in (
        ("31/12/2024", 360, 100), ("31/12/2023", 480, 100),
        ("Revenue", 40, 140), ("100", 360, 140), ("90", 480, 140),
        ("Cash", 40, 170), ("25", 360, 170), ("20", 480, 170),
        ("Assets", 40, 200), ("500", 360, 200), ("450", 480, 200),
    ):
        page.insert_text((x, y), text, fontsize=10)
    source = document.tobytes()
    document.close()
    return source


def blank_table_image() -> bytes:
    document = fitz.open()
    page = document.new_page(width=300, height=200)
    source = page.get_pixmap(alpha=False).tobytes("png")
    document.close()
    return source


class UploadProcessingFlowTest(unittest.TestCase):
    def test_embedding_failure_keeps_parsed_upload_for_retry_and_marks_document_failed(self):
        document_repo = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        parsed_repository = MagicMock()

        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch("core.embeddings.embedding_service.EmbeddingService", side_effect=RuntimeError("model unavailable")),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository") as chunks_cls,
            patch("core.database.structured_store.StructuredDataStore") as structured_cls,
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository", return_value=parsed_repository),
        ):
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 4
            with self.assertRaises(app_main.HTTPException) as error:
                asyncio.run(app_main.upload_document(
                    request=None,
                    file=UploadFile(filename="notes.txt", file=io.BytesIO(b"Revenue was 100 VND.")),
                    title="Finance notes",
                    document_type="internal_report",
                    domain="finance",
                    fiscal_year=None,
                    allowed_roles=["finance_analyst"],
                    user={"sub": "uploader-1"},
                ))

        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(parsed_repository.set_status.call_args_list[-1].args[1], "failed")
        self.assertEqual(parsed_repository.set_status.call_args_list[-1].args[2], "model unavailable")
        document_repo.update_processing_status.assert_called_with(
            document_repo.register_upload.call_args.args[0]["document_id"], "failed",
        )
        document_repo.save_metric_candidates.assert_not_called()
        chunks_cls.return_value.replace_document.assert_not_called()
        structured_cls.return_value.save_document_tables.assert_called_once()
        storage.storage.from_.return_value.remove.assert_not_called()

    def test_scanned_image_table_flows_through_upload_to_structured_store(self):
        source = blank_table_image()
        words = []
        for row, (label, current, previous) in enumerate((
            ("Revenue", "100", "90"),
            ("Cash", "25", "20"),
            ("Assets", "500", "450"),
        )):
            y = 40 + row * 20
            words.extend([
                (10, y, 85, y + 8, label, 1, row, 1),
                (110, y, 140, y + 8, current, 1, row, 2),
                (210, y, 240, y + 8, previous, 1, row, 3),
            ])
        document_repo = MagicMock()
        structured_store = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.return_value = [[0.1, 0.2]]

        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch.object(DocumentProcessor, "_ocr", return_value="Revenue 100 90\nCash 25 20\nAssets 500 450"),
            patch.object(PDFProcessor, "_ocr_page_words", return_value=words),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository") as chunks_cls,
            patch("core.database.structured_store.StructuredDataStore", return_value=structured_store),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository") as parsed_cls,
        ):
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 4
            response = asyncio.run(app_main.upload_document(
                request=None,
                file=UploadFile(filename="scan.png", file=io.BytesIO(source)),
                title="Scanned balance sheet",
                document_type="annual_report",
                domain="finance",
                fiscal_year=2024,
                allowed_roles=["finance_analyst"],
                user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["processing_status"], "ready")
        parsed_chunks = parsed_cls.return_value.replace_document.call_args.args[1]
        self.assertTrue(parsed_chunks)
        self.assertIn("Revenue", parsed_chunks[0]["text"])
        self.assertEqual(parsed_chunks[0]["metadata"]["embedding_model"], "test-embedding")
        self.assertEqual(parsed_cls.return_value.set_status.call_args.args[1], "embedded")
        saved_tables = structured_store.save_document_tables.call_args.args[2]
        self.assertEqual(len(saved_tables), 1)
        self.assertEqual(saved_tables[0]["rows"][-1], {
            "label": "Assets", "value_1": "500", "value_2": "450",
        })
        chunks_cls.return_value.replace_document.assert_called_once()

    def test_borderless_pdf_table_flows_through_upload_to_structured_store(self):
        source = borderless_financial_pdf()
        document_repo = MagicMock()
        structured_store = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.return_value = [[0.1, 0.2]]

        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository") as chunks_cls,
            patch("core.database.structured_store.StructuredDataStore", return_value=structured_store),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository") as parsed_cls,
        ):
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 4
            response = asyncio.run(app_main.upload_document(
                request=None,
                file=UploadFile(filename="balance.pdf", file=io.BytesIO(source)),
                title="Balance sheet",
                document_type="annual_report",
                domain="finance",
                fiscal_year=2024,
                allowed_roles=["finance_analyst"],
                user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["processing_status"], "ready")
        saved_tables = structured_store.save_document_tables.call_args.args[2]
        self.assertEqual(len(saved_tables), 1)
        self.assertEqual(saved_tables[0]["columns"], ["label", "31/12/2024", "31/12/2023"])
        self.assertEqual(saved_tables[0]["rows"][-1], {
            "label": "Assets", "31/12/2024": "500", "31/12/2023": "450",
        })
        self.assertEqual(saved_tables[0]["metadata"]["table_extraction_method"], "pymupdf.find_tables_text_aligned_columns")
        chunks_cls.return_value.replace_document.assert_called_once()

    def test_pptx_table_flows_from_upload_to_structured_store(self):
        source = pptx_with_table()
        document_repo = MagicMock()
        structured_store = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.return_value = [[0.1, 0.2]]

        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository") as chunks_cls,
            patch("core.database.structured_store.StructuredDataStore", return_value=structured_store),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository") as parsed_cls,
        ):
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 4
            request_file = UploadFile(filename="finance.pptx", file=io.BytesIO(source))
            response = asyncio.run(app_main.upload_document(
                request=None,
                file=request_file,
                title="Finance presentation",
                document_type="annual_report",
                domain="finance",
                fiscal_year=None,
                allowed_roles=["finance_analyst"],
                user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["processing_status"], "ready")
        saved_tables = structured_store.save_document_tables.call_args.args[2]
        self.assertEqual(saved_tables[0]["page_number"], 1)
        self.assertEqual(saved_tables[0]["columns"], ["Year", "Revenue"])
        self.assertEqual(saved_tables[0]["rows"], [{"Year": "2024", "Revenue": "100 VND"}])
        self.assertEqual(saved_tables[0]["metadata"]["slide_number"], 1)
        document_repo.update_processing_status.assert_called_with(response["document_id"], "ready")
        chunks_cls.return_value.replace_document.assert_called_once()

    def test_xlsx_formula_metadata_flows_from_upload_to_structured_store(self):
        source = xlsx_with_formula()
        document_repo = MagicMock()
        structured_store = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.return_value = [[0.1, 0.2]]

        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository") as chunks_cls,
            patch("core.database.structured_store.StructuredDataStore", return_value=structured_store),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository") as parsed_cls,
        ):
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 4
            request_file = UploadFile(filename="finance.xlsx", file=io.BytesIO(source))
            response = asyncio.run(app_main.upload_document(
                request=None,
                file=request_file,
                title="Finance report",
                document_type="annual_report",
                domain="finance",
                fiscal_year=None,
                allowed_roles=["finance_analyst"],
                user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["processing_status"], "ready")
        saved_tables = structured_store.save_document_tables.call_args.args[2]
        self.assertEqual(saved_tables[0]["metadata"]["formulas"], [{
            "cell": "B2", "formula": "=SUM(B1:B1)", "formula_type": None,
            "formula_ref": None, "cached_value": "100",
        }])
        self.assertEqual(document_repo.update_processing_status.call_args.args[1], "ready")
        chunks_cls.return_value.replace_document.assert_called_once()

    def test_structured_store_binds_formula_metadata_as_jsonb(self):
        connection = MagicMock()
        store = StructuredDataStore(connection=connection)
        formulas = [{"cell": "B2", "formula": "=SUM(B1:B1)", "cached_value": "100"}]

        store.save_document_tables("DOC-1", "Finance", [{
            "page_number": 1, "table_index": 0, "columns": ["Value"],
            "rows": [{"Value": "100"}], "metadata": {"formulas": formulas},
        }])

        cursor = connection.cursor.return_value.__enter__.return_value
        insert_params = cursor.execute.call_args.args[1]
        self.assertEqual(insert_params[-1].obj["formulas"], formulas)
        record_params = cursor.executemany.call_args.args[1]
        self.assertEqual(record_params[0][3].obj, {"Value": "100"})


if __name__ == "__main__":
    unittest.main()
