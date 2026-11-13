import unittest
import uuid
import os
from unittest.mock import patch

from app.upload_test import _process_and_save_upload_test


class UploadTestInvoiceTest(unittest.TestCase):
    def test_invoice_extraction_is_retained_with_test_run(self):
        extraction = {
            "model": "Qwen/Qwen2.5-0.5B-Instruct",
            "schema_version": "invoice.v1",
            "review_required": True,
            "fields": {"invoice_no": "A-1"},
            "raw_response": "{\"invoice_no\": \"A-1\"}",
            "metrics": {"inference_seconds": 8.5},
        }
        parsed = {
            "metadata": {"pipeline_id": "docling_qwen_invoice_text"},
            "elements": [{"text": "Invoice title", "metadata": {}}],
            "tables": [],
            "invoice_extraction": extraction,
        }
        with (
            patch.dict(os.environ, {"DOCUMENT_PROCESSING_URL": "http://document-processing"}),
            patch("core.services.client.post", return_value=parsed),
            patch("core.database.upload_test_repository.UploadTestRepository") as repository_type,
        ):
            _process_and_save_upload_test(
                run_id=uuid.uuid4(),
                filename="invoice.pdf",
                content=b"pdf",
                source_sha256="a" * 64,
                uploaded_by="tester",
                config={"intent": "invoice"},
                source_metadata={"source_type": "upload_test"},
                page_previews=[],
                preview_page_sizes={},
                page_count=1,
                pymupdf_version="test",
            )

        runtime_info = repository_type.return_value.save_run.call_args.kwargs["runtime_info"]
        self.assertEqual(runtime_info["invoice_extraction"], extraction)


if __name__ == "__main__":
    unittest.main()
