import os
import unittest
from unittest.mock import patch

from app.main import _process_invoice_upload


class InvoiceProcessingSettingsTest(unittest.TestCase):
    def test_invoice_upload_uses_fast_tableformer_without_changing_vietocr(self):
        parsed = {
            "invoice_extraction": {
                "status": "review_required",
                "model": "test-model",
                "fields": {},
            },
            "elements": [],
            "tables": [],
        }
        with (
            patch.dict(os.environ, {
                "DOCUMENT_PROCESSING_URL": "http://document-processing",
                "DOCUMENT_PROCESSING_OCR_ENGINE": "vietocr",
            }),
            patch("app.main.post_internal_service", return_value=parsed) as post,
            patch("core.database.invoice_repository.InvoiceRepository") as repository_type,
        ):
            _process_invoice_upload(
                invoice_id="INV-test",
                filename="invoice.pdf",
                content=b"%PDF-test",
                uploaded_by="tester",
                source_sha256="a" * 64,
                model_provider="gemini",
            )

        config = post.call_args.args[2]["config"]
        self.assertEqual(config["docling_table_mode"], "fast")
        self.assertEqual(config["docling_ocr_engine"], "vietocr")
        self.assertTrue(config["docling_table_structure"])
        repository_type.return_value.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
