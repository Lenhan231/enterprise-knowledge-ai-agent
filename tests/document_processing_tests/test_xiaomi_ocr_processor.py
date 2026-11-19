from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from document_processing.document_processor import DocumentProcessor
from document_processing.invoice.xiaomi_processor import (
    MODEL_ID,
    XiaomiOCRInvoiceProcessor,
    _parse_xiaomi_response,
)


class XiaomiOCRInvoiceProcessorTest(unittest.TestCase):
    @staticmethod
    def image_bytes():
        image = Image.new("RGB", (32, 24), "white")
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def test_response_parser_accepts_object_code_fence_and_list_wrapper(self):
        invoice = {"invoice_no": "A-1", "items": [{
            "description": "Paper", "quantity": 2, "unit": "box",
            "unit_price": 3, "amount": 6,
        }]}

        for response in (
            json.dumps(invoice),
            f"```json\n{json.dumps(invoice)}\n```",
            json.dumps([invoice]),
        ):
            with self.subTest(response=response[:20]):
                parsed = _parse_xiaomi_response(response)
                self.assertEqual(parsed["invoice_no"], "A-1")
                self.assertEqual(parsed["items"][0]["quantity"], "2")
                self.assertEqual(parsed["items"][0]["amount"], "6")

    def test_response_parser_rejects_invalid_schema(self):
        self.assertIsNone(_parse_xiaomi_response('{"unknown_field":"value"}'))
        self.assertIsNone(_parse_xiaomi_response("not JSON"))

    def test_process_renders_image_and_returns_reviewable_invoice_fields(self):
        model_response = {
            "invoice_no": "A-1", "date": "01/02/2026", "seller": "Seller",
            "buyer": "Buyer", "items": [{
                "description": "Paper", "quantity": "2", "unit": "box",
                "unit_price": "3", "amount": "6",
            }], "subtotal": "6", "tax_amount": "0", "total_amount": "6",
        }

        def fake_run(command, **kwargs):
            self.assertEqual(command[1:3], ["-m", "document_processing.invoice.xiaomi_worker"])
            request_path, response_path = map(Path, command[-2:])
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request["model_id"], MODEL_ID)
            self.assertEqual(len(request["pages"]), 1)
            self.assertIn('"items"', request["prompt"])
            Path(response_path).write_text(json.dumps({
                "revision": "test-revision",
                "pages": [{"page_number": 1, "response": json.dumps(model_response)}],
                "metrics": {"inference_seconds": 0.5},
            }), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with (
            patch(
                "document_processing.invoice.xiaomi_processor.resolve_xiaomi_python",
                return_value=Path(__file__),
            ),
            patch("document_processing.invoice.xiaomi_processor.subprocess.run", side_effect=fake_run),
        ):
            result = XiaomiOCRInvoiceProcessor().process(
                "invoice.png", self.image_bytes(), reference_id="INV-test",
            )

        self.assertEqual(result["model"], MODEL_ID)
        self.assertEqual(result["revision"], "test-revision")
        self.assertEqual(result["schema_version"], "invoice.v1")
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["fields"]["invoice_no"], "A-1")
        self.assertEqual(result["fields"]["items"][0]["amount"], "6")
        self.assertEqual(result["metrics"]["page_count"], 1)
        self.assertIsNone(result["parse_error"])

    def test_document_processor_dispatches_xiaomi_provider_with_original_source(self):
        parsed = {
            "elements": [{"element_type": "text", "text": "invoice OCR"}],
            "tables": [],
            "metadata": {},
        }
        extraction = {
            "model": MODEL_ID, "revision": "main", "schema_version": "invoice.v1",
            "status": "review_required", "review_required": True,
            "fields": {}, "metrics": {},
        }
        content = self.image_bytes()
        parser = Mock()
        parser.process.return_value = parsed
        docling_module = ModuleType("document_processing.docling_adapter.processor")
        docling_module.DoclingProcessor = Mock(return_value=parser)

        with (
            patch.dict(sys.modules, {"document_processing.docling_adapter.processor": docling_module}),
            patch("document_processing.invoice.xiaomi_processor.XiaomiOCRInvoiceProcessor.process", return_value=extraction) as extract,
            patch("document_processing.invoice.ocr_cache.invoice_docling_cache.get", return_value=None),
            patch("document_processing.invoice.ocr_cache.invoice_docling_cache.put", return_value=True),
        ):
            result = DocumentProcessor({
                "intent": "invoice", "invoice_provider": "xiaomi",
            }).process("invoice.png", content, {})

        self.assertEqual(extract.call_args.args, ("invoice.png", content))
        self.assertEqual(extract.call_args.kwargs, {"reference_id": None})
        self.assertEqual(result["invoice_extraction"], extraction)
        self.assertEqual(result["metadata"]["pipeline_id"], "docling_xiaomi_ocr_invoice")
        self.assertEqual(result["metadata"]["invoice_model"], MODEL_ID)


if __name__ == "__main__":
    unittest.main()
