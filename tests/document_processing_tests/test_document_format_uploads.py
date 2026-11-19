"""Exercise format validation, persistence handoff, and Upload Test previews."""

import asyncio
import base64
from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException, UploadFile
from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app import main, upload_test


class DocumentFormatUploadTest(unittest.IsolatedAsyncioTestCase):
    async def upload(self, suffix, content, parsed):
        request = SimpleNamespace(url=SimpleNamespace(path="/api/documents/parser-handoff"))
        storage = MagicMock()
        with (
            patch.dict("os.environ", {"DOCUMENT_PROCESSING_URL": "http://parser.test"}),
            patch.object(main, "_require_same_origin"),
            patch.object(main, "DocumentRepository") as repository,
            patch.object(main, "_storage_client", return_value=(storage, "private")),
            patch.object(main, "post_internal_service", return_value=parsed) as parse,
            patch("core.database.document_processing_output_repository.DocumentProcessingOutputRepository"),
        ):
            result = await main.upload_document(
                request=request, file=UploadFile(filename=f"report{suffix}", file=BytesIO(content)),
                title="Report", document_type="internal_report", domain="operations", fiscal_year=None,
                allowed_roles=["finance_analyst"], ocr_language="eng", user={"sub": "owner"},
            )
        return result, storage.storage.from_.return_value.upload, parse, repository

    async def test_knowledge_upload_passes_original_bytes_with_matching_media_type(self):
        office = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        cases = (
            (".doc", office, "application/msword"),
            (".xls", office, "application/vnd.ms-excel"),
            (".ppt", office, "application/vnd.ms-powerpoint"),
            (".bmp", b"BM", "image/bmp"),
            (".gif", b"GIF89a", "image/gif"),
            (".heic", b"\0\0\0\x10ftypheic\0\0\0\0", "image/heic"),
            (".heif", b"\0\0\0\x10ftypmif1\0\0\0\0", "image/heif"),
            (".avif", b"\0\0\0\x10ftypavif\0\0\0\0", "image/avif"),
            (".webp", b"RIFF\0\0\0\0WEBP", "image/webp"),
            (".svg", b'<svg width="4" height="3"/>', "image/svg+xml"),
        )
        for suffix, content, mime_type in cases:
            with self.subTest(suffix=suffix):
                parsed = {"elements": [], "tables": [], "page_sizes": {"1": {}, "2": {}}}
                result, upload, parse, repository = await self.upload(suffix, content, parsed)
                self.assertEqual(result["processing_status"], "parsed")
                self.assertEqual(upload.call_args.args[1], content)
                self.assertEqual(upload.call_args.args[2]["content-type"], mime_type)
                self.assertEqual(parse.call_args.args[2]["content"], base64.b64encode(content).decode())
                self.assertEqual(repository.return_value.register_upload.call_args.args[0]["format"],
                                 suffix[1:].upper())
                if suffix == ".gif":
                    self.assertEqual(result["page_count"], 2)

    async def test_mislabeled_raster_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            await self.upload(".avif", b"GIF89a", {})
        self.assertEqual(error.exception.status_code, 415)

    async def test_upload_test_previews_both_animated_frames(self):
        buffer = BytesIO()
        Image.new("RGB", (12, 8), "red").save(
            buffer, format="WEBP", lossless=True, save_all=True,
            append_images=[Image.new("RGB", (12, 8), "blue")],
        )
        content = buffer.getvalue()
        with (
            patch.object(upload_test, "_require_same_origin"),
            patch.dict(upload_test._UPLOAD_TEST_JOBS, clear=True),
            patch.object(upload_test, "_run_upload_test_job", new_callable=AsyncMock) as job,
        ):
            result = await upload_test.create_upload_test(
                request=None, file=UploadFile(filename="scan.webp", file=BytesIO(content)),
                intent="document", docling_device="cpu", docling_ocr=True,
                docling_ocr_language="eng", docling_table_structure=True,
                docling_num_threads=2, user={"sub": "owner"},
            )
            await asyncio.gather(*tuple(upload_test._UPLOAD_TEST_TASKS))
        self.assertEqual(result["status"], "processing")
        args = job.call_args.args[1]
        self.assertEqual(args["content"], content)
        self.assertEqual(args["page_count"], 2)
        for index, color in enumerate(((255, 0, 0), (0, 0, 255))):
            with Image.open(BytesIO(args["page_previews"][index])) as preview:
                self.assertEqual(preview.getpixel((0, 0)), color)

    async def test_upload_test_logs_observed_pdf_pages_over_the_limit(self):
        import fitz

        with fitz.open() as pdf:
            for _ in range(51):
                pdf.new_page()
            content = pdf.tobytes()
        with (
            patch.object(upload_test, "_require_same_origin"),
            patch.object(upload_test, "_run_upload_test_job", new_callable=AsyncMock) as job,
            self.assertLogs("app.upload_test", level="ERROR") as logs,
            self.assertRaises(HTTPException) as error,
        ):
            await upload_test.create_upload_test(
                request=None, file=UploadFile(filename="private.pdf", file=BytesIO(content)),
                intent="document", docling_device="cpu", docling_ocr=True,
                docling_ocr_language="eng", docling_table_structure=True,
                docling_num_threads=2, user={"sub": "owner"},
            )
        self.assertEqual(error.exception.status_code, 422)
        self.assertIn("51 pages", error.exception.detail)
        job.assert_not_called()
        event, payload = logs.records[0].getMessage().split(" ", 1)
        self.assertEqual(event, "DOCUMENT_PROCESS_COMPONENT_ERROR")
        details = json.loads(payload)
        self.assertEqual(details["component"], "upload_test_page_previews")
        self.assertEqual(details["error_code"], "page_limit_exceeded")
        self.assertEqual((details["page_count"], details["page_limit"], details["count_unit"]), (51, 50, "pages"))
        self.assertNotIn("private.pdf", payload)

    def test_svg_original_is_served_as_an_attachment(self):
        storage = MagicMock()
        storage.storage.from_.return_value.download.return_value = b"<svg/>"
        with (
            patch.object(main, "DocumentRepository") as repository,
            patch.object(main, "_storage_client", return_value=(storage, "private")),
        ):
            repository.return_value.uploaded_source.return_value = {
                "title": "Report", "format": "SVG", "storage_path": "report.svg",
            }
            response = main._uploaded_source_response("document", {"role": "admin", "sub": "owner"})
        self.assertTrue(response.headers["content-disposition"].startswith("attachment"))
        self.assertEqual(response.headers["content-type"], "image/svg+xml")
