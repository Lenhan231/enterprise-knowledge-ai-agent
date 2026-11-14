import base64
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.services.runtime import LOCK, Parse, _invoice_provider_is_remote, parse


class InvoiceRuntimeLockTest(unittest.TestCase):
    def _body(self, provider, **config):
        return Parse(
            filename="invoice.pdf",
            content=base64.b64encode(b"%PDF test").decode("ascii"),
            config={"intent": "invoice", "invoice_provider": provider, **config},
        )

    def test_remote_provider_selection_excludes_local_modal_fallback(self):
        self.assertTrue(_invoice_provider_is_remote({"invoice_provider": "gemini"}))
        self.assertTrue(_invoice_provider_is_remote({"invoice_provider": "groq"}))
        with patch.dict(os.environ, {"DOCUMENT_PROCESSING_INVOICE_MODAL_URL": ""}):
            self.assertTrue(_invoice_provider_is_remote({
                "invoice_provider": "modal", "invoice_modal_url": "https://modal.example/run",
            }))
            self.assertFalse(_invoice_provider_is_remote({"invoice_provider": "modal"}))
        self.assertFalse(_invoice_provider_is_remote({"invoice_provider": "local"}))

    def test_remote_provider_does_not_hold_parser_lock_for_extraction(self):
        processor = Mock()

        def process(*args, **kwargs):
            parser_lock = kwargs["invoice_docling_lock"]
            self.assertIs(parser_lock, LOCK)
            self.assertTrue(parser_lock.acquire(blocking=False))
            parser_lock.release()
            kwargs["on_invoice_docling_lock_wait"](2.5)
            return {"elements": [], "tables": []}

        processor.process.side_effect = process
        with (
            patch.dict(os.environ, {
                "SERVICE_KIND": "document-processing",
                "INTERNAL_SERVICE_TOKEN": "test-token",
            }),
            patch("document_processing.document_processor.DocumentProcessor", return_value=processor),
        ):
            result = parse(self._body("gemini"))

        self.assertEqual(result["elements"], [])
        self.assertFalse(LOCK.locked())

    def test_local_modal_fallback_keeps_parser_lock_for_extraction(self):
        processor = Mock()
        processor.process.side_effect = lambda *args, **kwargs: (
            {"elements": [], "tables": []} if LOCK.locked()
            else self.fail("local invoice inference did not retain the parser lock")
        )
        with (
            patch.dict(os.environ, {
                "SERVICE_KIND": "document-processing",
                "INTERNAL_SERVICE_TOKEN": "test-token",
                "DOCUMENT_PROCESSING_INVOICE_PROVIDER": "modal",
                "DOCUMENT_PROCESSING_INVOICE_MODAL_URL": "",
            }),
            patch("document_processing.document_processor.DocumentProcessor", return_value=processor),
        ):
            result = parse(self._body("modal"))

        self.assertEqual(result["elements"], [])
        self.assertFalse(LOCK.locked())


if __name__ == "__main__":
    unittest.main()
