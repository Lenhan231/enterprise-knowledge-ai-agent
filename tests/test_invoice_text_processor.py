import json
import unittest
from threading import Barrier
from unittest.mock import patch

from document_processing.document_processor import DocumentProcessor
from document_processing.invoice_text_processor import (
    InvoiceFields,
    SCHEMA,
    _extraction_jobs,
    _infer_with_gemini,
    _parse_json_response,
    _prepare_extraction_input,
)


class InvoiceTextProcessorTest(unittest.TestCase):
    def test_gemini_invoice_jobs_run_in_parallel_and_keep_input_order(self):
        both_requests_started = Barrier(2)

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.payload

        def fake_urlopen(request, timeout):
            prompt = request.data.decode("utf-8")
            both_requests_started.wait(timeout=2)
            response_text = "header" if '"text": "first"' in prompt else "table"
            return Response(
                json.dumps({
                    "modelVersion": "gemini-test-version",
                    "candidates": [{"content": {"parts": [{"text": response_text}]}}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2},
                }).encode("utf-8")
            )

        with patch("document_processing.invoice_text_processor.urlopen", side_effect=fake_urlopen):
            result = _infer_with_gemini(
                [
                    {"prompt": "first", "max_new_tokens": 256},
                    {"prompt": "second", "max_new_tokens": 1024},
                ],
                api_key="test-key",
                model_id="gemini-test",
                timeout=3,
            )

        self.assertEqual(result["responses"], ["header", "table"])
        self.assertEqual(result["revision"], "gemini-test-version")
        self.assertEqual(result["metrics"]["request_count"], 2)
        self.assertEqual(result["metrics"]["prompt_tokens"], 20)
        self.assertEqual(result["metrics"]["generated_tokens"], 4)
        self.assertIn("request_inference_seconds", result["metrics"])

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

    def test_invoice_parser_coerces_numbers_and_discards_arithmetic(self):
        parsed = _parse_json_response(
            '{"items":[{"description":"Sửa văn phòng","quantity":40,"unit":"đ",'
            '"unit_price":5,"amount":200}],"subtotal":"200 + 118000 = 118200",'
            '"tax_amount":9440000,"total_amount":127440000}'
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["items"][0]["quantity"], "40")
        self.assertEqual(parsed["tax_amount"], "9440000")
        self.assertIsNone(parsed["subtotal"])

    def test_invoice_input_preserves_rows_for_header_and_table_jobs(self):
        columns = ["STT", "Tên hàng hóa, dịch vụ", "ĐVT", "Số lượng", "Đơn giá", "Thành tiền"]
        guide = dict(zip(columns, ["1", "2", "3", "4", "5", "6?4x5"]))
        noisy_guide = dict(zip(columns, ["1", "tư.", "ở.", "40 đ.", "5.", "6 - 45."]))
        actual = dict(zip(columns, ["", "Sửa chữa văn phòng", "", "", "", "118.000.000"]))
        subtotal = dict(zip(columns, ["", "", "Cộng tiền hàng hóa, dịch vụ:", "", "", "118.000.000"]))
        tax = dict(zip(columns, ["", "Thuế suất GTGT: 8%", "Tiền thuế GTGT:", "", "", "9.440.000"]))
        total = dict(zip(columns, ["", "", "Tổng tiền thanh toán:", "", "", "127.440.000"]))
        source_rows = [guide, noisy_guide, actual, subtotal, tax, total]
        prepared = _prepare_extraction_input([], [{"columns": columns, "rows": source_rows}])
        jobs = _extraction_jobs(prepared)

        self.assertEqual([job["kind"] for job in jobs], ["table"])
        self.assertIn("Tên hàng hóa, dịch vụ", jobs[0]["prompt"])
        self.assertIn("118.000.000", jobs[0]["prompt"])
        self.assertIn("9.440.000", jobs[0]["prompt"])
        self.assertIn("127.440.000", jobs[0]["prompt"])
        self.assertEqual(source_rows, [guide, noisy_guide, actual, subtotal, tax, total])

    def test_invoice_party_labels_and_text_are_retained_as_evidence(self):
        elements = [
            {"element_type": "title", "text": "CÔNG TY TNHH ĐẦU TƯ XÂY DỰNG THƯƠNG MẠI GIA PHÁT HUY"},
            {"element_type": "text", "text": "Tên đơn vị: CÔNG TY TNHH NHÔM KÍNH BÌNH MINH"},
        ]
        jobs = _extraction_jobs(_prepare_extraction_input(elements, []))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["kind"], "document")
        self.assertIn('"element_type": "title"', jobs[0]["prompt"])
        self.assertIn("CÔNG TY TNHH ĐẦU TƯ XÂY DỰNG THƯƠNG MẠI GIA PHÁT HUY", jobs[0]["prompt"])
        self.assertIn("Tên đơn vị: CÔNG TY TNHH NHÔM KÍNH BÌNH MINH", jobs[0]["prompt"])

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
        self.assertEqual(extract.call_args.kwargs, {"reference_id": None})
        self.assertEqual(result["invoice_extraction"], extraction)
        self.assertEqual(result["metadata"]["parser_engine"], "docling")
        self.assertEqual(result["metadata"]["pipeline_id"], "docling_qwen_invoice_text")


if __name__ == "__main__":
    unittest.main()
