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
from core.document_processing.processors.image_processor import ImageProcessor  # noqa: E402
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


def docx_with_sections() -> bytes:
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("word/document.xml", """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
          <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Financial performance</w:t></w:r></w:p>
          <w:p><w:r><w:t>Audited annual results.</w:t></w:r></w:p>
          <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Metric</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Amount</w:t></w:r></w:p></w:tc></w:tr>
            <w:tr><w:tc><w:p><w:r><w:t>Revenue</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>100 billion VND</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        </w:body></w:document>""")
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


def financial_summary_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=600, height=400)
    page.insert_text((40, 80), "Net revenue 2024 was 100 billion VND.", fontsize=12)
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
    def test_upload_extracts_only_requested_decision_domain_after_indexing(self):
        source = financial_summary_pdf()
        events = []
        document_repo = MagicMock()
        document_repo.save_business_metric_candidates.side_effect = lambda rows, **kwargs: events.append("business_metrics_saved") or len(rows)
        document_repo.save_business_metric_extraction_run.side_effect = lambda run: events.append("business_metric_run_saved") or 17
        structured_store = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.side_effect = lambda texts: [[0.1, 0.2] for _ in texts]
        chunk_repository = MagicMock()
        chunk_repository.replace_document.side_effect = lambda document_id, rows: events.append("indexed_chunks_saved")
        llm = MagicMock(model_name="test-financial-model")
        extracted = []

        def business_candidates(chunks, tables, document, provider):
            self.assertEqual(document["document_id"].split("-")[0], "UPLOAD")
            self.assertEqual(document["fiscal_year"], 2025)
            self.assertEqual(document["business_decision_domain"], "market_performance")
            self.assertIs(provider, llm)
            row = {
                "company": document["company"], "domain": "market_performance",
                "metric_name": "domestic_consolidated_net_revenue_growth",
                "metric_label": "Domestic consolidated net revenue growth",
                "fiscal_year": 2025, "metric_value": 0.3, "unit": "%",
                "scope": "Consolidated domestic market, year-over-year",
                "source_document_id": document["document_id"], "page_number": 1,
                "source_chunk_index": 0,
                "source_quote": "Domestic net revenue increased 0.3% YoY.",
                "source_url": document["source_url"],
                "allowed_roles": document["rbac"]["allowed_roles"],
                "extraction_method": "llm_parser", "extractor_version": "test-catalog-v1",
                "extraction_config": {},
            }
            extracted.append(row)
            return [row], [{
                "page_number": 1,
                "chunks": [{"chunk_index": 0, "selection_signals": {"domain_relevance_score": 1}}],
                "llm_metrics_returned": 1, "llm_metrics_accepted": 1,
                "validation_rejections": {},
            }]

        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository", return_value=chunk_repository),
            patch("core.database.structured_store.StructuredDataStore", return_value=structured_store),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository"),
            patch("core.analytics.metric_candidates.candidates", return_value=[]),
            patch("core.analytics.business_metric_extraction.extract_business_metric_candidates", side_effect=business_candidates),
            patch("core.analytics.financial_extraction.extract_financial_candidates", return_value=([], [])),
            patch("core.llm.groq_provider.GroqProvider", return_value=llm),
        ):
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 4
            response = asyncio.run(app_main.upload_document(
                request=None,
                file=UploadFile(filename="annual-report-final.pdf", file=io.BytesIO(source)),
                title="Vinamilk Annual Report 2025", document_type="annual_report",
                domain="finance_and_operations", fiscal_year=2025,
                business_decision_domain="market_performance",
                allowed_roles=["finance_analyst", "admin"], user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["business_metric_candidates"], 1)
        self.assertEqual(response["business_metric_extraction_run_id"], 17)
        self.assertEqual(events, ["indexed_chunks_saved", "business_metrics_saved", "business_metric_run_saved"])
        self.assertEqual(extracted[0]["source_document_id"], response["document_id"])
        document_repo.save_business_metric_candidates.assert_called_once_with(extracted, entered_by="parser")
        document_repo.save_business_metric_extraction_run.assert_called_once()
        run = document_repo.save_business_metric_extraction_run.call_args.args[0]
        self.assertEqual(run["audit"]["chunk_decisions"][0]["status"], "candidate_found")

    def test_upload_without_decision_domain_skips_business_metric_llm(self):
        source = financial_summary_pdf()
        document_repo = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.side_effect = lambda texts: [[0.1, 0.2] for _ in texts]
        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository"),
            patch("core.database.structured_store.StructuredDataStore"),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository"),
            patch("core.analytics.metric_candidates.candidates", return_value=[]),
            patch("core.analytics.financial_extraction.extract_financial_candidates", return_value=([], [])),
            patch("core.llm.groq_provider.GroqProvider") as provider_cls,
            patch("core.analytics.business_metric_extraction.extract_business_metric_candidates") as business_extractor,
        ):
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 4
            response = asyncio.run(app_main.upload_document(
                request=None,
                file=UploadFile(filename="annual-report.pdf", file=io.BytesIO(source)),
                title="Annual report", document_type="annual_report", domain="finance",
                fiscal_year=None, business_decision_domain="",
                allowed_roles=["finance_analyst"],
                user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["business_metric_candidates"], 0)
        provider_cls.assert_not_called()
        business_extractor.assert_not_called()

    def test_upload_no_longer_exposes_report_specific_metric_profile(self):
        from inspect import signature

        self.assertNotIn("metric_parser_profile", signature(app_main.upload_document).parameters)
        self.assertNotIn("/api/business-metrics/parser-profiles", {
            route.path for route in app_main.app.routes
        })

    def test_pdf_upload_retains_rule_candidates_when_financial_llm_generation_is_rate_limited(self):
        source = borderless_financial_pdf()
        document_repo = MagicMock()
        structured_store = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.side_effect = lambda texts: [[0.1, 0.2] for _ in texts]
        rule_candidate = {"metric_name": "net_revenue", "status": "needs_review"}
        llm = MagicMock(model_name="test-financial-model")
        llm.generate.side_effect = RuntimeError("rate limited")

        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository"),
            patch("core.database.structured_store.StructuredDataStore", return_value=structured_store),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository"),
            patch("core.analytics.metric_candidates.candidates", return_value=[rule_candidate]),
            patch("core.llm.groq_provider.GroqProvider", return_value=llm),
        ):
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 4
            response = asyncio.run(app_main.upload_document(
                request=None,
                file=UploadFile(filename="balance.pdf", file=io.BytesIO(source)),
                title="Balance sheet", document_type="annual_report", domain="finance",
                fiscal_year=2024, business_decision_domain="",
                allowed_roles=["finance_analyst"], user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["processing_status"], "ready")
        document_repo.save_metric_candidates.assert_called_once_with(
            response["document_id"], [rule_candidate],
        )
        self.assertEqual(llm.generate.call_count, 1)
        llm.close.assert_called_once()

    def test_pdf_upload_saves_selected_page_llm_metric_as_pending_review_candidate(self):
        source = financial_summary_pdf()
        document_repo = MagicMock()
        structured_store = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.side_effect = lambda texts: [[0.1, 0.2] for _ in texts]
        llm = MagicMock(model_name="test-financial-model")

        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository"),
            patch("core.database.structured_store.StructuredDataStore", return_value=structured_store),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository"),
            patch("core.analytics.metric_candidates.candidates", return_value=[]),
            patch("core.analytics.financial_extraction.extract_financial_candidates", return_value=([{
                "metric_name": "net_revenue", "candidate_values": ["100"],
                "unit": "billion VND", "extraction_method": "llm_selected_financial_page",
                "extractor_model": "test-financial-model", "fiscal_year": 2024,
                "status": "needs_review", "page_number": 1,
            }], [])),
            patch("core.llm.groq_provider.GroqProvider", return_value=llm),
        ):
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 8
            response = asyncio.run(app_main.upload_document(
                request=None,
                file=UploadFile(filename="annual-report.pdf", file=io.BytesIO(source)),
                title="Annual report", document_type="annual_report", domain="finance",
                fiscal_year=2024, business_decision_domain="",
                allowed_roles=["finance_analyst"], user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["processing_status"], "ready")
        self.assertEqual(llm.generate.call_count, 0)
        document_id, candidates = document_repo.save_metric_candidates.call_args.args
        self.assertEqual(document_id, response["document_id"])
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["metric_name"], "net_revenue")
        self.assertEqual(candidate["candidate_values"], ["100"])
        self.assertEqual(candidate["unit"], "billion VND")
        self.assertEqual(candidate["extraction_method"], "llm_selected_financial_page")
        self.assertEqual(candidate["extractor_model"], "test-financial-model")
        self.assertEqual(candidate["fiscal_year"], 2024)
        self.assertEqual(candidate["status"], "needs_review")
        self.assertEqual(candidate["page_number"], 1)
        llm.close.assert_called_once()

    def test_structured_table_inspection_is_company_scoped_and_paginated(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.description = [MagicMock(name="id"), MagicMock(name="page_number")]
        cursor.fetchall.return_value = [{
            "id": "DOC-1:page:2:table:0", "page_number": 2, "table_index": 0,
            "columns": ["Metric", "Value"], "metadata": {"parser": "test"},
            "row_count": 130, "rows": [{"Metric": "Revenue", "Value": "100"}],
        }]
        store = StructuredDataStore(connection=connection)

        result = store.get_document_tables(
            "DOC-1", company="Vinamilk", table_offset=2, table_limit=10,
            row_offset=30, row_limit=50,
        )

        self.assertEqual(result[0]["row_count"], 130)
        query, params = cursor.execute.call_args.args
        self.assertIn("d.company = %s", query)
        self.assertIn("LIMIT %s OFFSET %s", query)
        self.assertEqual(params, (50, 30, "DOC-1", "Vinamilk", 10, 2))

    def test_structured_table_inspection_rejects_unbounded_page_sizes(self):
        store = StructuredDataStore(connection=MagicMock())
        with self.assertRaisesRegex(ValueError, "table_limit"):
            store.get_document_tables("DOC-1", company="Vinamilk", row_limit=1000)

    def test_docx_section_title_flows_through_upload_into_retrieval_chunks(self):
        document_repo = MagicMock()
        structured_store = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.side_effect = lambda texts: [[0.1, 0.2] for _ in texts]

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
                file=UploadFile(filename="finance.docx", file=io.BytesIO(docx_with_sections())),
                title="Finance report",
                document_type="annual_report",
                domain="finance",
                fiscal_year=2024,
                business_decision_domain="",
                allowed_roles=["finance_analyst"],
                user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["processing_status"], "ready")
        persisted = chunks_cls.return_value.replace_document.call_args.args[1]
        self.assertEqual(
            chunks_cls.return_value.replace_document.call_args.args[0], response["document_id"],
        )
        self.assertEqual(persisted[0][0], "finance.docx")
        self.assertEqual(persisted[0][3]["section_title"], "Financial performance")
        self.assertEqual(persisted[0][3]["embedding_model"], "test-embedding")
        self.assertEqual(persisted[0][3]["actual_char_count"], len(persisted[0][2]))
        table_chunk = next((row for row in persisted if row[3].get("layout_type") == "table"), None)
        self.assertIsNotNone(table_chunk)
        self.assertIn("Metric: Revenue | Amount: 100 billion VND", table_chunk[2])
        self.assertEqual(table_chunk[3]["section_title"], "Financial performance")
        parsed = parsed_cls.return_value.replace_document.call_args.args[1]
        self.assertEqual(parsed[0]["metadata"]["section_title"], "Financial performance")
        parsed_table_chunk = next(chunk for chunk in parsed if chunk["metadata"].get("layout_type") == "table")
        self.assertIn("Metric: Revenue | Amount: 100 billion VND", parsed_table_chunk["text"])
        saved_table = structured_store.save_document_tables.call_args.args[2][0]
        self.assertEqual(saved_table["columns"], ["Metric", "Amount"])
        self.assertEqual(saved_table["rows"], [{"Metric": "Revenue", "Amount": "100 billion VND"}])

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
                    business_decision_domain="",
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

    def test_image_ocr_caption_and_table_flow_through_upload_to_persistence(self):
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
        embedding.embed_documents.return_value = [[0.1, 0.2], [0.3, 0.4]]
        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch.object(ImageProcessor, "_ocr", return_value="Revenue 100 90\nCash 25 20\nAssets 500 450"),
            patch.object(PDFProcessor, "_ocr_page_words", return_value=words),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository") as chunks_cls,
            patch("core.database.structured_store.StructuredDataStore", return_value=structured_store),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository") as parsed_cls,
            patch.dict("os.environ", {"DOCUMENT_VISION_CAPTIONS": "true"}),
            patch("core.llm.groq_provider.GroqProvider") as vision_provider,
        ):
            vision_provider.return_value.caption_image.return_value = "A financial table lists revenue, cash, and assets."
            vision_provider.return_value.vision_model_name = "qwen/qwen3.8-27b"
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 4
            response = asyncio.run(app_main.upload_document(
                request=None,
                file=UploadFile(filename="scan.png", file=io.BytesIO(source)),
                title="Scanned balance sheet",
                document_type="annual_report",
                domain="finance",
                fiscal_year=2024,
                business_decision_domain="",
                allowed_roles=["finance_analyst"],
                user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["processing_status"], "ready")
        parsed_chunks = parsed_cls.return_value.replace_document.call_args.args[1]
        self.assertTrue(parsed_chunks)
        self.assertIn("Revenue", parsed_chunks[0]["text"])
        self.assertEqual(parsed_chunks[0]["metadata"]["embedding_model"], "test-embedding")
        caption_chunk = next(chunk for chunk in parsed_chunks if chunk["metadata"].get("layout_type") == "figure_caption")
        self.assertEqual(caption_chunk["text"], "AI-generated image caption (unverified): A financial table lists revenue, cash, and assets.")
        self.assertEqual(caption_chunk["metadata"]["caption_model"], "qwen/qwen3.8-27b")
        vision_provider.return_value.close.assert_called_once()
        self.assertEqual(parsed_cls.return_value.set_status.call_args.args[1], "embedded")
        saved_tables = structured_store.save_document_tables.call_args.args[2]
        self.assertEqual(len(saved_tables), 1)
        self.assertEqual(saved_tables[0]["rows"][-1], {
            "label": "Assets", "value_1": "500", "value_2": "450",
        })
        self.assertEqual(saved_tables[0]["metadata"]["ocr"]["table_psm"], 6)
        chunks_cls.return_value.replace_document.assert_called_once()

    def test_borderless_pdf_table_flows_through_upload_to_structured_store(self):
        source = borderless_financial_pdf()
        document_repo = MagicMock()
        structured_store = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.return_value = [[0.1, 0.2]]
        processor_settings = {}
        original_processor_init = DocumentProcessor.__init__

        def capture_processor_settings(processor, config=None):
            processor_settings.update(config or {})
            original_processor_init(processor, config)

        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository") as chunks_cls,
            patch("core.database.structured_store.StructuredDataStore", return_value=structured_store),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository") as parsed_cls,
            patch.dict("os.environ", {
                "DOCUMENT_PADDLE_FORMULA_RECOGNITION": "true",
                "DOCUMENT_VISION_CAPTIONS": "true",
            }),
            patch.object(DocumentProcessor, "__init__", capture_processor_settings),
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
                business_decision_domain="",
                allowed_roles=["finance_analyst"],
                user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["processing_status"], "ready")
        self.assertTrue(processor_settings["paddle_formula_recognition"])
        self.assertTrue(processor_settings["vision_captioning"])
        saved_tables = structured_store.save_document_tables.call_args.args[2]
        self.assertEqual(len(saved_tables), 1)
        self.assertEqual(saved_tables[0]["columns"], ["label", "31/12/2024", "31/12/2023"])
        self.assertEqual(saved_tables[0]["rows"][-1], {
            "label": "Assets", "31/12/2024": "500", "31/12/2023": "450",
        })
        self.assertEqual(saved_tables[0]["metadata"]["table_extraction_method"], "pymupdf.find_tables_text_aligned_columns")
        chunks_cls.return_value.replace_document.assert_called_once()

    def test_scanned_pdf_table_flows_from_ocr_parser_to_structured_store(self):
        pdf = fitz.open()
        pdf.new_page(width=600, height=400)
        source = pdf.tobytes()
        pdf.close()
        words = [
            (40, 30, 180, 38, "Period", 1, 0, 1),
            (300, 30, 390, 38, "31122024", 1, 0, 2),
            (470, 30, 560, 38, "31122023", 1, 0, 3),
        ]
        for row, (label, current, previous) in enumerate((
            ("Revenue", "100000", "90000"),
            ("Cash balance", "25000", "20000"),
            ("Total assets", "500000", "450000"),
        )):
            y = 60 + row * 25
            words.extend([
                (40, y, 180, y + 8, label, 1, row + 1, 1),
                (300, y, 390, y + 8, current, 1, row + 1, 2),
                (470, y, 560, y + 8, previous, 1, row + 1, 3),
            ])

        document_repo = MagicMock()
        structured_store = MagicMock()
        storage = MagicMock()
        storage.storage.from_.return_value.upload.return_value = None
        embedding = MagicMock(model_name="test-embedding", max_sequence_length=100)
        embedding.embed_documents.side_effect = lambda texts: [[0.1, 0.2] for _ in texts]
        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
            patch.object(app_main, "DocumentRepository", return_value=document_repo),
            patch("core.document_processing.processors.pdf_processor.shutil.which", return_value="/usr/bin/tesseract"),
            patch.object(PDFProcessor, "_ocr_page", return_value="Revenue 100000 90000\nCash balance 25000 20000\nTotal assets 500000 450000"),
            patch.object(PDFProcessor, "_ocr_page_words", return_value=words),
            patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding),
            patch("core.utils.token_counter.TokenCounter") as counter_cls,
            patch("core.database.document_chunks_repository.DocumentChunkRepository") as chunks_cls,
            patch("core.database.structured_store.StructuredDataStore", return_value=structured_store),
            patch("core.database.processed_chunks_repository.ProcessedChunksRepository") as parsed_cls,
            patch.dict("os.environ", {
                "DOCUMENT_PADDLE_LAYOUT": "false",
                "DOCUMENT_PADDLE_FORMULA_RECOGNITION": "false",
                "DOCUMENT_VISION_CAPTIONS": "false",
            }),
        ):
            counter_cls.return_value.split_text.side_effect = lambda text, **kwargs: [text]
            counter_cls.return_value.count.return_value = 4
            response = asyncio.run(app_main.upload_document(
                request=None,
                file=UploadFile(filename="scanned-statement.pdf", file=io.BytesIO(source)),
                title="Scanned statement",
                document_type="annual_report",
                domain="finance",
                fiscal_year=None,
                business_decision_domain="",
                allowed_roles=["finance_analyst"],
                user={"sub": "uploader-1"},
            ))

        self.assertEqual(response["processing_status"], "ready")
        saved_tables = structured_store.save_document_tables.call_args.args[2]
        self.assertEqual(saved_tables[0]["columns"], ["label", "31/12/2024", "31/12/2023"])
        self.assertEqual(saved_tables[0]["rows"], [
            {"label": "Revenue", "31/12/2024": "100000", "31/12/2023": "90000"},
            {"label": "Cash balance", "31/12/2024": "25000", "31/12/2023": "20000"},
            {"label": "Total assets", "31/12/2024": "500000", "31/12/2023": "450000"},
        ])
        embedding_inputs = embedding.embed_documents.call_args.args[0]
        self.assertTrue(any("label: Revenue" in text for text in embedding_inputs))
        persisted_chunks = chunks_cls.return_value.replace_document.call_args.args[1]
        table_chunk = next(row for row in persisted_chunks if row[3].get("layout_type") == "table")
        self.assertIn("31/12/2024: 100000", table_chunk[2])
        self.assertTrue(any("Revenue 100000 90000" in text for text in embedding_inputs))
        self.assertFalse(table_chunk[3]["table_chunk_match"]["matched_source_chunk"])
        parsed_chunks = parsed_cls.return_value.replace_document.call_args.args[1]
        self.assertTrue(any(chunk["metadata"].get("layout_type") == "table" for chunk in parsed_chunks))
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
                business_decision_domain="",
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
                business_decision_domain="",
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
        row_cell_bboxes = [{"label": [10, 20, 50, 30], "2024": [100, 20, 130, 30]}]

        store.save_document_tables("DOC-1", "Finance", [{
            "page_number": 1, "table_index": 0, "columns": ["Value"],
            "rows": [{"Value": "100"}],
            "metadata": {"formulas": formulas, "row_cell_bboxes": row_cell_bboxes},
        }])

        cursor = connection.cursor.return_value.__enter__.return_value
        insert_params = cursor.execute.call_args.args[1]
        self.assertEqual(insert_params[-1].obj["formulas"], formulas)
        self.assertEqual(insert_params[-1].obj["row_cell_bboxes"], row_cell_bboxes)
        record_params = cursor.executemany.call_args.args[1]
        self.assertEqual(record_params[0][3].obj, {"Value": "100"})


if __name__ == "__main__":
    unittest.main()
