import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from document_processing.document_processor import DocumentProcessor
from document_processing.invoice_ocr_cache import InvoiceDoclingCache, invoice_docling_cache


class InvoiceDoclingCacheTest(unittest.TestCase):
    def test_key_is_scoped_to_source_format_and_parser_configuration(self):
        cache = InvoiceDoclingCache()
        config = {"docling_ocr_engine": "vietocr", "docling_num_threads": 2}

        key = cache.key(b"same invoice", "pdf", config)

        self.assertEqual(key, cache.key(b"same invoice", "pdf", config))
        self.assertNotEqual(key, cache.key(b"different invoice", "pdf", config))
        self.assertNotEqual(key, cache.key(b"same invoice", "png", config))
        self.assertNotEqual(
            key,
            cache.key(b"same invoice", "pdf", {**config, "docling_num_threads": 1}),
        )

    def test_entries_expire_and_return_isolated_copies(self):
        now = [10.0]
        cache = InvoiceDoclingCache(ttl_seconds=5, clock=lambda: now[0])
        key = cache.key(b"invoice", "pdf", {})
        source = {"elements": [{"text": "Total"}], "tables": []}

        self.assertTrue(cache.put(key, source))
        cached = cache.get(key)
        cached["elements"][0]["text"] = "changed"
        self.assertEqual(cache.get(key)["elements"][0]["text"], "Total")

        now[0] += 5
        self.assertIsNone(cache.get(key))

    def test_cache_skips_oversized_results(self):
        cache = InvoiceDoclingCache(max_entry_bytes=20)
        key = cache.key(b"invoice", "pdf", {})

        self.assertFalse(cache.put(key, {"elements": [{"text": "x" * 100}]}))
        self.assertIsNone(cache.get(key))

    def test_retry_after_gemini_timeout_reuses_docling_but_refreshes_invoice_metadata(self):
        invoice_docling_cache.clear()
        self.addCleanup(invoice_docling_cache.clear)
        docling_result = {
            "elements": [{"element_type": "text", "text": "Invoice", "metadata": {"parser": "docling"}}],
            "tables": [],
            "metadata": {},
        }
        extraction = {
            "model": "test-model",
            "revision": "test-revision",
            "schema_version": "invoice.v1",
            "status": "review_required",
            "review_required": True,
            "fields": {"invoice_no": "A-1"},
            "metrics": {},
        }
        processor = DocumentProcessor({"intent": "invoice", "invoice_provider": "gemini"})
        docling_process = Mock(return_value=docling_result)
        docling_module = ModuleType("document_processing.docling_adapter.processor")
        docling_module.DoclingProcessor = Mock(
            return_value=SimpleNamespace(process=docling_process)
        )
        infer = Mock(side_effect=[TimeoutError("Gemini timed out"), extraction])
        invoice_module = ModuleType("document_processing.invoice_text_processor")
        invoice_module.InvoiceTextProcessor = Mock(
            return_value=SimpleNamespace(process=infer)
        )

        with (
            patch.dict("sys.modules", {
                "document_processing.docling_adapter.processor": docling_module,
                "document_processing.invoice_text_processor": invoice_module,
            }),
        ):
            with self.assertRaises(TimeoutError):
                processor.process("invoice.pdf", b"same invoice bytes", {"invoice_id": "retry-1"})

            result = processor.process(
                "invoice.pdf", b"same invoice bytes", {"invoice_id": "retry-2"}
            )

        docling_process.assert_called_once()
        self.assertEqual(infer.call_count, 2)
        self.assertEqual(result["elements"][0]["metadata"]["invoice_id"], "retry-2")
        self.assertEqual(result["invoice_extraction"]["fields"]["invoice_no"], "A-1")


if __name__ == "__main__":
    unittest.main()
