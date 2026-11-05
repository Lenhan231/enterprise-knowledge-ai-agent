import unittest
from unittest.mock import patch

from document_processing.document_processor import DocumentProcessor
from document_processing.invoice_text_processor import (
    InvoiceFields,
    SCHEMA,
    _parse_json_response,
)


class InvoiceTextProcessorTest(unittest.TestCase):
    def test_schema_is_compact_and_rejects_tax_id_fields(self):
        self.assertEqual(
            set(SCHEMA),
            {"invoice_no", "date", "seller", "buyer", "items", "subtotal", "tax_amount", "total_amount"},
        )
        self.assertNotIn("tax_id", str(SCHEMA).lower())
        self.assertNotIn("seller_tax_id", InvoiceFields.model_fields)
        self.assertNotIn("buyer_tax_id", InvoiceFields.model_fields)

    def test_parser_keeps_only_the_selected_schema(self):
        parsed = _parse_json_response(
            '{"invoice_no":"A-1","seller_tax_id":"123","items":[]}'
        )
        self.assertIsNone(parsed)

    def test_invoice_dispatches_docling_then_text_extraction(self):
        docling_output = {
            "elements": [{"element_type": "text", "text": "HÓA ĐƠN"}],
            "tables": [{"columns": ["Mô tả"], "rows": [{"Mô tả": "Dịch vụ"}]}],
            "metadata": {},
        }
        extraction = {
            "model": "test-model", "revision": "test", "schema_version": "invoice.v1",
            "status": "review_required", "review_required": True,
            "fields": {"invoice_no": "A-1"}, "metrics": {},
        }
        with (
            patch("document_processing.docling_adapter.processor.DoclingProcessor.process", return_value=docling_output) as parse,
            patch("document_processing.invoice_text_processor.InvoiceTextProcessor.process", return_value=extraction) as extract,
        ):
            result = DocumentProcessor({"intent": "invoice"}).process("invoice.pdf", b"pdf", {})

        self.assertEqual(parse.call_count, 1)
        self.assertEqual(extract.call_args.args, (docling_output["elements"], docling_output["tables"]))
        self.assertEqual(result["invoice_extraction"], extraction)
        self.assertEqual(result["metadata"]["parser_engine"], "docling")
        self.assertEqual(result["metadata"]["pipeline_id"], "docling_qwen_invoice_text")


if __name__ == "__main__":
    unittest.main()
