import unittest
from unittest.mock import patch

from document_processing.document_processor import DocumentProcessor
from document_processing.invoice_text_processor import (
    InvoiceFields,
    SCHEMA,
    _fields_from_tables,
    _fields_from_labeled_elements,
    _parse_json_response,
    _prepare_extraction_input,
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

    def test_invoice_input_separates_guide_items_and_totals(self):
        columns = ["STT", "Tên hàng hóa, dịch vụ", "ĐVT", "Số lượng", "Đơn giá", "Thành tiền"]
        guide = dict(zip(columns, ["1", "2", "3", "4", "5", "6?4x5"]))
        actual = dict(zip(columns, ["", "Sửa chữa văn phòng", "", "", "", "118.000.000"]))
        subtotal = dict(zip(columns, ["", "", "Cộng tiền hàng hóa, dịch vụ:", "", "", "118.000.000"]))
        tax = dict(zip(columns, ["", "Thuế suất GTGT: 8%", "Tiền thuế GTGT:", "", "", "9.440.000"]))
        total = dict(zip(columns, ["", "", "Tổng tiền thanh toán:", "", "", "127.440.000"]))
        source_rows = [guide, actual, subtotal, tax, total]
        prepared = _prepare_extraction_input([], [{"columns": columns, "rows": source_rows}])
        table = prepared["tables"][0]
        self.assertEqual(table["item_rows"], [{
            "description": "Sửa chữa văn phòng", "quantity": None, "unit": None,
            "unit_price": None, "amount": "118.000.000",
        }])
        self.assertEqual(_fields_from_tables(prepared["tables"]), {
            "items": table["item_rows"], "subtotal": "118.000.000",
            "tax_amount": "9.440.000", "total_amount": "127.440.000",
        })
        self.assertEqual(source_rows, [guide, actual, subtotal, tax, total])

    def test_invoice_names_use_explicit_ocr_labels(self):
        fields = _fields_from_labeled_elements([
            {"type": "title", "text": "CÔNG TY TNHH ĐẦU TƯ XÂY DỰNG THƯƠNG MẠI GIA PHÁT HUY"},
            {"type": "text", "text": "Tên đơn vị: CÔNG TY TNHH NHÔM KÍNH BÌNH MINH"},
        ])
        self.assertEqual(fields, {
            "seller": "CÔNG TY TNHH ĐẦU TƯ XÂY DỰNG THƯƠNG MẠI GIA PHÁT HUY",
            "buyer": "CÔNG TY TNHH NHÔM KÍNH BÌNH MINH",
        })

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
