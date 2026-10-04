import builtins
import shutil
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.document_processing.processors.pdf_processor import PDFProcessor
from core.document_processing.processors.document_processor import DocumentProcessor


class PDFUploadProcessingTest(unittest.TestCase):
    def test_numeric_table_gate_handles_tesseract_cells_split_across_lines(self):
        ocr_text = "Region\nDelivered sample orders\nMedian transit days\nAvg fee units\n" \
            "120\n95\n80\n3.0\n4.0\n5.0\n42.50\n48.75\n55.25"
        self.assertTrue(PDFProcessor._looks_like_numeric_table(ocr_text))
        self.assertFalse(PDFProcessor._looks_like_numeric_table(
            "The report shows 120 orders in 2024.\nAverage delivery took 3.0 days."
        ))

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is required for the scanned-PDF integration fixture")
    def test_synthetic_scanned_pdf_upload_parser_extracts_table_cells(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "data/evaluation/ocr/commerce_synthetic_policy_scan_demo.pdf"
        parsed = DocumentProcessor({"paddle_layout": False}).process(
            path.name, path.read_bytes(), {"document_id": "OCR-DEMO"},
        )
        self.assertEqual(len(parsed["tables"]), 1)
        table = parsed["tables"][0]
        self.assertEqual(table["metadata"]["table_extraction_method"], "tesseract.tsv_aligned_columns")
        self.assertEqual(table["columns"], [
            "Region", "Delivered sample orders", "Median transit days", "Avg fee units",
        ])
        self.assertEqual(table["rows"], [
            {"Region": "East", "Delivered sample orders": "120", "Median transit days": "3.0", "Avg fee units": "42.50"},
            {"Region": "Central", "Delivered sample orders": "95", "Median transit days": "4.0", "Avg fee units": "48.75"},
            {"Region": "West", "Delivered sample orders": "80", "Median transit days": "5.0", "Avg fee units": "55.25"},
        ])

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is required for the degraded scan fixture")
    def test_degraded_scan_parser_groups_skewed_rows_and_ignores_dash_only_footer(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "data/evaluation/ocr/commerce_synthetic_degraded_scan_demo.pdf"
        parsed = DocumentProcessor({"paddle_layout": False}).process(
            path.name, path.read_bytes(), {"document_id": "OCR-DEGRADED-DEMO"},
        )

        self.assertEqual(len(parsed["tables"]), 1)
        table = parsed["tables"][0]
        self.assertEqual(table["columns"], [
            "Region", "Delivered sample orders", "Median transit days", "Avg fee units",
        ])
        self.assertEqual(table["rows"], [
            {"Region": "East", "Delivered sample orders": "120", "Median transit days": "3.0", "Avg fee units": "42.50"},
            {"Region": "Central", "Delivered sample orders": "95", "Median transit days": "4.0", "Avg fee units": "48.75"},
            {"Region": "West", "Delivered sample orders": "80", "Median transit days": "5.0", "Avg fee units": "55.25"},
        ])
        self.assertEqual(table["context"]["table_title"], "Synthetic regional logistics sample")

    def test_logical_account_table_fragments_keep_hierarchy_and_structured_rows(self):
        table = {
            "page_number": 7, "table_index": 0,
            "columns": ["label", "value_1", "value_2", "value_3"],
            "rows": [
                {"label": "Mã", "value_1": "huyết", "value_2": "2011", "value_3": "2010"},
                {"label": "100 TÀI SẢN NGẮN HẠN", "value_1": "", "value_2": "9.467", "value_3": "5.919"},
                {"label": "110 Tiền và các khoản tương đương tiền", "value_1": "3", "value_2": "3.156", "value_3": "613"},
                {"label": "111 Tiền", "value_1": "", "value_2": "790", "value_3": "249"},
                {"label": "112 Các khoản tương đương tiền", "value_1": "", "value_2": "2.366", "value_3": "364"},
                {"label": "120 Các khoản đầu tư tài chính ngắn hạn", "value_1": "4(a)", "value_2": "736", "value_3": "1.742"},
                {"label": "121 Đầu tư ngắn hạn", "value_1": "", "value_2": "815", "value_3": "1.812"},
                {"label": "129 Dự phòng giảm giá đầu tư ngắn hạn", "value_1": "", "value_2": "(79)", "value_3": "(70"},
                {"label": "130 Các khoản phải thu ngắn hạn", "value_1": "", "value_2": "2.169", "value_3": "1.124"},
                {"label": "131 Phải thu khách hàng", "value_1": "5", "value_2": "1.143", "value_3": "587"},
                {"label": "132 Trả trước cho người bán", "value_1": "", "value_2": "795", "value_3": "354"},
                {"label": "135 Các khoản phải thu khác", "value_1": "6", "value_2": "232", "value_3": "183"},
                {"label": "139 Dự phòng phải thu ngắn hạn khó đòi", "value_1": "", "value_2": "(1)", "value_3": "(596"},
                {"label": "140 Hàng tồn kho", "value_1": "7", "value_2": "3.272", "value_3": "2.351"},
                {"label": "141 Hàng tồn kho", "value_1": "", "value_2": "3.277", "value_3": "2.355"},
                {"label": "149 Dự phòng giảm giá hàng tồn kho", "value_1": "", "value_2": "(4)", "value_3": "(4"},
                {"label": "150 Tài sản ngắn hạn khác", "value_1": "", "value_2": "133", "value_3": "87"},
                {"label": "151 Chi phí trả trước ngắn hạn", "value_1": "8(a)", "value_2": "56", "value_3": "38"},
                {"label": "152 Thuế Giá trị Gia tăng được khấu trừ", "value_1": "", "value_2": "74", "value_3": "16"},
                {"label": "158 Tài sản ngắn hạn khác", "value_1": "", "value_2": "1", "value_3": "32"},
            ],
            "metadata": {"table_extraction_method": "tesseract.tsv_aligned_columns", "numeric_columns": [8, 9, 10]},
        }

        fragments = PDFProcessor._logical_table_fragments(
            table, table_title="BẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT",
            unit="VNĐ", column_labels={
                "label": "Mã | Tài sản", "value_1": "Thuyết minh",
                "value_2": "2011", "value_3": "2010",
            },
        )

        self.assertEqual(len(fragments), 5)
        self.assertIn("Đơn vị: VNĐ", fragments[0]["retrieval_text"])
        self.assertIn("2011", fragments[0]["retrieval_text"])
        self.assertIn("100 TÀI SẢN NGẮN HẠN", fragments[0]["retrieval_text"])
        self.assertIn("112 Các khoản tương đương tiền", fragments[0]["retrieval_text"])
        self.assertEqual(fragments[2]["structured_data"]["rows"][-1]["Mã | Tài sản"], "139 Dự phòng phải thu ngắn hạn khó đòi")
        self.assertEqual(fragments[2]["structured_data"]["rows"][-1]["2010"], "(596")
        self.assertNotIn("numeric_columns", fragments[0]["metadata"])
        self.assertNotIn('"rows"', fragments[0]["retrieval_text"])

    def test_high_overlap_replaces_same_page_flat_chunk_with_key_value_table_chunk(self):
        processor = PDFProcessor({"paddle_layout": False})
        chunks = [{
            "text": "Metric 2024 2023 Revenue 100 90 Profit 25 20",
            "metadata": {"page_number": 7, "chunk_index": 3, "section_title": "Financial results"},
        }]
        tables = [{
            "page_number": 7,
            "table_index": 2,
            "columns": ["Metric", "2024", "2023"],
            "rows": [
                {"Metric": "Revenue", "2024": "100", "2023": "90"},
                {"Metric": "Profit", "2024": "25", "2023": "20"},
            ],
            "metadata": {"table_extraction_method": "test.extractor"},
        }]

        result = processor._replace_flat_table_chunks(chunks, tables)

        self.assertEqual(len(result), 1)
        self.assertIn("Metric: Revenue | 2024: 100 | 2023: 90", result[0]["text"])
        self.assertEqual(result[0]["metadata"]["layout_type"], "table")
        self.assertEqual(result[0]["metadata"]["section_title"], "Financial results")
        self.assertTrue(result[0]["metadata"]["table_chunk_match"]["matched_source_chunk"])
        self.assertEqual(result[0]["metadata"]["chunk_index"], 0)

    def test_low_overlap_keeps_original_and_adds_structured_table_chunk(self):
        processor = PDFProcessor({"paddle_layout": False})
        chunks = [{
            "text": "Management discussion explains annual performance and market conditions.",
            "metadata": {"page_number": 4, "chunk_index": 0, "section_title": "Overview"},
        }]
        tables = [{
            "page_number": 4,
            "table_index": 0,
            "columns": ["Metric", "2024", "2023"],
            "rows": [{"Metric": "Revenue", "2024": "100", "2023": "90"}],
            "metadata": {"table_extraction_method": "test.extractor"},
        }]

        result = processor._replace_flat_table_chunks(chunks, tables)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["text"], chunks[0]["text"])
        self.assertNotEqual(result[0]["metadata"].get("layout_type"), "table")
        self.assertEqual(result[1]["metadata"]["layout_type"], "table")
        self.assertFalse(result[1]["metadata"]["table_chunk_match"]["matched_source_chunk"])

    def test_page_number_is_required_before_replacing_flat_chunk(self):
        processor = PDFProcessor({"paddle_layout": False})
        chunks = [{
            "text": "Metric 2024 2023 Revenue 100 90",
            "metadata": {"page_number": 1, "chunk_index": 0},
        }]
        tables = [{
            "page_number": 2,
            "table_index": 0,
            "columns": ["Metric", "2024", "2023"],
            "rows": [{"Metric": "Revenue", "2024": "100", "2023": "90"}],
            "metadata": {},
        }]

        result = processor._replace_flat_table_chunks(chunks, tables)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["metadata"]["page_number"], 1)
        self.assertEqual(result[1]["metadata"]["page_number"], 2)
        self.assertNotEqual(result[0]["metadata"].get("layout_type"), "table")

    def test_pdf_file_properties_are_not_repeated_in_each_chunk(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((40, 50), "Report body text with enough words.")
        pdf.set_metadata({
            "title": "Embedded PDF title", "author": "Scanner Device",
            "subject": "Subject metadata", "keywords": "secretariat, report",
        })
        source = pdf.tobytes()
        pdf.close()

        result = PDFProcessor({"paddle_layout": False, "extract_tables": False}).process({
            "content": source,
            "metadata": {"document_id": "DOC-METADATA", "filename": "report.pdf"},
        })

        metadata = result["chunks"][0]["metadata"]
        for field in ("title", "author", "subject", "keywords"):
            self.assertNotIn(field, metadata)

    def test_commerce_operational_pdf_extracts_native_table(self):
        pdf = fitz.open()
        page = pdf.new_page(width=600, height=400)
        for text, x, y in (
            ("Regional fulfillment results", 40, 50),
            ("Region", 40, 110), ("Delivered orders", 250, 110), ("Average days", 440, 110),
            ("East", 40, 145), ("120", 250, 145), ("3.0", 440, 145),
            ("Central", 40, 180), ("95", 250, 180), ("4.0", 440, 180),
            ("West", 40, 215), ("80", 250, 215), ("5.0", 440, 215),
        ):
            page.insert_text((x, y), text, fontsize=10)
        source = pdf.tobytes()
        pdf.close()

        result = PDFProcessor({"paddle_layout": False}).process({
            "content": source,
            "metadata": {"document_id": "COMMERCE-OPS-PDF"},
        })

        self.assertEqual(len(result["tables"]), 1)
        table = result["tables"][0]
        self.assertEqual(table["metadata"]["table_extraction_method"], "pymupdf.find_tables_text_aligned_columns")
        self.assertEqual(
            table["rows"],
            [
                {"label": "East", "value_1": "120", "value_2": "3.0"},
                {"label": "Central", "value_1": "95", "value_2": "4.0"},
                {"label": "West", "value_1": "80", "value_2": "5.0"},
            ],
        )

    def test_native_text_chunks_keep_page_and_document_metadata(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_textbox(fitz.Rect(40, 40, 550, 780), "Doanh thu thuần 2024. " + "Kết quả hoạt động doanh nghiệp. " * 100)
        source = pdf.tobytes()
        pdf.close()

        result = PDFProcessor({
            "paddle_layout": False,
            "ocr_fallback": False,
            "extract_tables": False,
            "chunk_size": 180,
            "chunk_overlap": 20,
        }).process({
            "content": source,
            "metadata": {"document_id": "DOC-1", "allowed_roles": ["finance_analyst"]},
        })

        self.assertGreater(len(result["chunks"]), 1)
        self.assertEqual([chunk["metadata"]["chunk_index"] for chunk in result["chunks"]], list(range(len(result["chunks"]))))
        self.assertTrue(all(chunk["metadata"]["page_number"] == 1 for chunk in result["chunks"]))
        self.assertTrue(all(chunk["metadata"]["layout_type"] == "text" for chunk in result["chunks"]))
        self.assertTrue(all(chunk["metadata"]["document_id"] == "DOC-1" for chunk in result["chunks"]))
        self.assertTrue(all(chunk["metadata"]["allowed_roles"] == ["finance_analyst"] for chunk in result["chunks"]))

    def test_scanned_page_uses_tesseract_fallback(self):
        pdf = fitz.open()
        pdf.new_page()
        source = pdf.tobytes()
        pdf.close()
        with patch("core.document_processing.processors.pdf_processor.shutil.which", return_value="/usr/bin/tesseract"), \
             patch("core.document_processing.processors.pdf_processor.subprocess.run", return_value=SimpleNamespace(
                 stdout="Doanh thu thuần năm 2024 đạt 100 tỷ đồng".encode("utf-8")
             )) as run:
            result = PDFProcessor({
                "paddle_layout": False, "ocr_fallback": True, "ocr_language": "vie+eng",
                "extract_tables": False, "chunk_size": 200, "chunk_overlap": 20,
            }).process({"content": source, "metadata": {"document_id": "SCAN-1"}})
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][-2:], ["--psm", "11"])
        self.assertIn("100 tỷ", result["chunks"][0]["text"])
        self.assertEqual(result["chunks"][0]["metadata"]["text_extraction_method"], "tesseract")
        self.assertEqual(result["chunks"][0]["metadata"]["ocr"], {
            "engine": "tesseract", "language": "vie+eng", "page_psm": 11, "render_scale": 1.5,
        })

    def test_numeric_scan_renders_table_words_at_higher_resolution(self):
        pdf = fitz.open()
        pdf.new_page()
        source = pdf.tobytes()
        pdf.close()
        processor = PDFProcessor({
            "paddle_layout": False, "ocr_fallback": True, "extract_tables": True,
        })
        processor.ocr_available = True

        with (
            patch.object(processor, "_needs_ocr", return_value=True),
            patch.object(
                processor, "_ocr_page",
                return_value="Revenue 100 90\nCash 25 20\nAssets 500 450",
            ) as text_ocr,
            patch.object(processor, "_ocr_page_words", return_value=[]) as table_ocr,
            patch.object(PDFProcessor, "_extract_page_tables", return_value=[]),
        ):
            processor._extract_pdf(source)

        text_ocr.assert_called_once()
        table_ocr.assert_called_once()
        text_pixmap = text_ocr.call_args.args[1]
        table_pixmap = table_ocr.call_args.args[1]
        self.assertIsNot(text_pixmap, table_pixmap)
        self.assertAlmostEqual(table_pixmap.width / text_pixmap.width, 2.5 / 1.5, places=2)
        self.assertEqual(processor._ocr_table_metadata()["render_scale"], 2.5)

    def test_mixed_page_appends_ocr_without_losing_native_text(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_textbox(
            fitz.Rect(40, 650, 550, 780),
            "Native report context remains searchable. Native report reference stays readable.",
        )
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 500, 400), False)
        page.insert_image(fitz.Rect(40, 40, 550, 600), pixmap=pixmap)
        source = pdf.tobytes()
        pdf.close()

        with patch("core.document_processing.processors.pdf_processor.shutil.which", return_value="/usr/bin/tesseract"), \
             patch("core.document_processing.processors.pdf_processor.subprocess.run", return_value=SimpleNamespace(
                 stdout=(
                     "Native report contxt remains searchable. Native report reference stays readable. "
                     "Net revenue 2024: 61.8 trillion VND"
                 ).encode("utf-8")
             )) as run:
            result = PDFProcessor({
                "paddle_layout": False, "ocr_fallback": True, "ocr_language": "vie+eng",
                "extract_tables": False, "chunk_size": 500, "chunk_overlap": 50,
            }).process({"content": source, "metadata": {"document_id": "MIXED-1"}})

        run.assert_called_once()
        combined_text = " ".join(chunk["text"] for chunk in result["chunks"])
        self.assertIn("Native report context", combined_text)
        self.assertIn("Native report reference stays readable", combined_text)
        self.assertEqual(combined_text.count("Native report context remains searchable."), 1)
        self.assertEqual(combined_text.count("Native report reference stays readable."), 1)
        self.assertIn("61.8 trillion", combined_text)
        self.assertEqual(result["chunks"][0]["metadata"]["text_extraction_method"], "pymupdf+tesseract")

    def test_opt_in_caption_crops_embedded_pdf_figure_with_source_page_metadata(self):
        pdf = fitz.open()
        page = pdf.new_page(width=600, height=800)
        page.insert_text((40, 50), "Annual results")
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
        page.insert_image(fitz.Rect(50, 100, 300, 350), pixmap=pixmap)
        source = pdf.tobytes()
        pdf.close()

        with patch("core.llm.groq_provider.GroqProvider") as provider_type:
            provider = provider_type.return_value
            provider.caption_image.return_value = "A bar chart compares revenue by year."
            provider.vision_model_name = "qwen/qwen3.8-27b"
            result = PDFProcessor({
                "paddle_layout": False, "ocr_fallback": False,
                "extract_tables": False, "vision_captioning": True,
            }).process({"content": source, "metadata": {"document_id": "PDF-FIGURE"}})

        provider.caption_image.assert_called_once()
        image_bytes, mime_type = provider.caption_image.call_args.args
        self.assertTrue(image_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(mime_type, "image/png")
        provider.close.assert_called_once()
        caption = next(chunk for chunk in result["chunks"] if chunk["metadata"].get("layout_type") == "figure_caption")
        self.assertEqual(caption["metadata"]["page_number"], 1)
        self.assertEqual(caption["metadata"]["document_id"], "PDF-FIGURE")
        self.assertEqual(caption["metadata"]["caption_model"], "qwen/qwen3.8-27b")
        self.assertTrue(caption["metadata"]["is_model_generated"])

    def test_detected_pdf_tables_have_explicit_layout_metadata(self):
        table = SimpleNamespace(
            header=SimpleNamespace(names=["Metric"], external=False),
            extract=lambda: [["Metric"], ["Revenue"]],
        )
        page = SimpleNamespace(
            get_text=lambda kind: [(0, 0, 10, 10, "123"), (60, 0, 70, 10, "456"), (0, 20, 10, 30, "234"), (60, 20, 70, 30, "567"), (0, 40, 10, 50, "345"), (60, 40, 70, 50, "678")],
            find_tables=lambda: SimpleNamespace(tables=[table]),
        )

        tables = PDFProcessor._extract_page_tables(page, 4)

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["metadata"]["layout_type"], "table")
        self.assertEqual(tables[0]["metadata"]["element_type"], "table")

    def test_optional_paddle_path_keeps_chart_recognition_text_and_geometry(self):
        pdf = fitz.open()
        pdf.new_page()
        source = pdf.tobytes()
        pdf.close()
        output = SimpleNamespace(json={"res": {"parsing_res_list": [{
            "block_label": "chart", "block_content": "Revenue: 100; Profit: 20",
            "block_bbox": [10, 20, 200, 120],
        }]}})
        pipeline = Mock()
        pipeline.predict.return_value = [output]
        paddle = SimpleNamespace(PPStructureV3=Mock(return_value=pipeline))

        original_import = builtins.__import__

        def import_paddleocr(name, *args, **kwargs):
            if name == "paddleocr":
                return paddle
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_paddleocr):
            result = PDFProcessor({"chunk_size": 200, "chunk_overlap": 20})._process_with_paddle(
                source, None, {"metadata": {"document_id": "CHART-1"}},
            )

        paddle.PPStructureV3.assert_called_once()
        self.assertTrue(paddle.PPStructureV3.call_args.kwargs["use_chart_recognition"])
        chart_chunk = result["chunks"][0]
        self.assertEqual(chart_chunk["text"], "Revenue: 100; Profit: 20")
        self.assertEqual(chart_chunk["metadata"]["element_type"], "chart")
        self.assertEqual(chart_chunk["metadata"]["layout_type"], "chart")
        self.assertEqual(chart_chunk["metadata"]["bbox"], [10, 20, 200, 120])
        self.assertTrue(chart_chunk["metadata"]["visual_content_extracted"])

    def test_optional_paddle_path_keeps_each_detected_table_as_a_linkable_chunk(self):
        pdf = fitz.open()
        pdf.new_page()
        source = pdf.tobytes()
        pdf.close()
        table_html = (
            "<table><tr><th>Metric</th><th>2024</th></tr>"
            "<tr><td>Revenue</td><td>100</td></tr></table>"
        )
        output = SimpleNamespace(json={"res": {"parsing_res_list": [
            {"block_label": "table", "block_content": table_html, "block_bbox": [10, 20, 200, 100]},
            {"block_label": "table", "block_content": table_html.replace("100", "90"), "block_bbox": [10, 120, 200, 200]},
        ]}})
        pipeline = Mock()
        pipeline.predict.return_value = [output]
        paddle = SimpleNamespace(PPStructureV3=Mock(return_value=pipeline))

        original_import = builtins.__import__

        def import_paddleocr(name, *args, **kwargs):
            if name == "paddleocr":
                return paddle
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_paddleocr):
            result = PDFProcessor({"chunk_size": 500})._process_with_paddle(
                source, None, {"metadata": {"document_id": "TABLES-1"}},
            )

        table_chunks = [chunk for chunk in result["chunks"] if chunk["metadata"]["layout_type"] == "table"]
        self.assertEqual(len(result["tables"]), 2)
        self.assertEqual([chunk["metadata"]["table_index"] for chunk in table_chunks], [0, 1])
        self.assertIn("100", table_chunks[0]["text"])
        self.assertIn("90", table_chunks[1]["text"])

    def test_optional_paddle_formula_path_keeps_latex_and_source_geometry(self):
        pdf = fitz.open()
        pdf.new_page()
        source = pdf.tobytes()
        pdf.close()
        output = SimpleNamespace(json={"res": {"parsing_res_list": [{
            "block_label": "formula", "block_content": r"\frac{R}{A}=0.25",
            "block_bbox": [10, 20, 200, 80],
        }]}})
        pipeline = Mock()
        pipeline.predict.return_value = [output]
        paddle = SimpleNamespace(PPStructureV3=Mock(return_value=pipeline))

        original_import = builtins.__import__

        def import_paddleocr(name, *args, **kwargs):
            if name == "paddleocr":
                return paddle
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_paddleocr):
            result = PDFProcessor({"paddle_formula_recognition": True})._process_with_paddle(
                source, None, {"metadata": {"document_id": "FORMULA-1"}},
            )

        paddle.PPStructureV3.assert_called_once()
        self.assertTrue(paddle.PPStructureV3.call_args.kwargs["use_formula_recognition"])
        chunk = result["chunks"][0]
        self.assertEqual(chunk["text"], r"\frac{R}{A}=0.25")
        self.assertEqual(chunk["metadata"]["element_type"], "formula")
        self.assertEqual(chunk["metadata"]["layout_type"], "formula")
        self.assertEqual(chunk["metadata"]["bbox"], [10, 20, 200, 80])
        self.assertTrue(chunk["metadata"]["contains_formula"])
        self.assertEqual(chunk["metadata"]["formula_representation"], "latex")

    def test_borderless_aligned_financial_table_rebuilds_labels_and_value_columns(self):
        matrix = [
            ["", "31/12/2024", "31/12/2023"],
            ["Revenue", "100", "90"],
            ["Cash and equivalents", "25", "20"],
            ["Total assets", "500", "450"],
        ]
        cells = []
        for column, (left, right) in enumerate(((0, 90), (100, 170), (180, 250))):
            cells.extend((left, row * 10, right, (row + 1) * 10) for row in range(len(matrix)))
        table = SimpleNamespace(
            extract=lambda: matrix,
            cells=cells,
            bbox=(0, 0, 250, 40),
        )
        words = []
        for row_index, label in enumerate(("Revenue", "Cash and equivalents", "Total assets"), start=1):
            words.append((5, row_index * 10 + 2, 80, row_index * 10 + 8, label, 0, row_index, 0))
        page = SimpleNamespace(get_text=lambda mode: words)

        result = PDFProcessor._split_aligned_text_table(table, page, 4, 2)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["table_index"], 2)
        self.assertEqual(result[0]["columns"], ["label", "31/12/2024", "31/12/2023"])
        self.assertEqual(result[0]["rows"], [
            {"label": "Revenue", "31/12/2024": "100", "31/12/2023": "90"},
            {"label": "Cash and equivalents", "31/12/2024": "25", "31/12/2023": "20"},
            {"label": "Total assets", "31/12/2024": "500", "31/12/2023": "450"},
        ])

    def test_pdf_table_fallback_runs_only_after_default_finds_no_tables(self):
        matrix = [
            ["", "31/12/2024", "31/12/2023"],
            ["Revenue", "100", "90"],
            ["Cash", "25", "20"],
            ["Assets", "500", "450"],
        ]
        cells = [
            (left, row * 10, right, (row + 1) * 10)
            for left, right in ((0, 90), (100, 170), (180, 250))
            for row in range(len(matrix))
        ]
        table = SimpleNamespace(extract=lambda: matrix, cells=cells, bbox=(0, 0, 250, 40))
        words = []
        for row, (label, value_2024, value_2023) in enumerate((
            ("Revenue", "100", "90"), ("Cash", "25", "20"), ("Assets", "500", "450"),
        ), start=1):
            y0, y1 = row * 10 + 2, row * 10 + 8
            words.extend([
                (5, y0, 80, y1, label, 0, row, 0),
                (110, y0, 130, y1, value_2024, 0, row, 1),
                (190, y0, 210, y1, value_2023, 0, row, 2),
            ])
        page = Mock()
        page.find_tables.side_effect = [
            SimpleNamespace(tables=[]),
            SimpleNamespace(tables=[table]),
        ]
        page.get_text.return_value = words

        result = PDFProcessor._extract_page_tables(page, 2)

        self.assertEqual(page.find_tables.call_args_list, [call(), call(strategy="text")])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["rows"][-1], {
            "label": "Assets", "31/12/2024": "500", "31/12/2023": "450",
        })

    def test_ocr_word_boxes_rebuild_scanned_financial_table_rows(self):
        words = []
        for row, (label, current, previous) in enumerate((
            ("Revenue", "100", "90"),
            ("Cash", "25", "20"),
            ("Total assets", "500", "450"),
        )):
            y = 40 + row * 20
            words.extend([
                (10, y, 85, y + 8, label, 1, row, 1),
                (110, y, 140, y + 8, current, 1, row, 2),
                (210, y, 240, y + 8, previous, 1, row, 3),
            ])

        tables = PDFProcessor._tables_from_aligned_words(words, fitz.Rect(0, 0, 300, 200), 3)

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["columns"], ["label", "value_1", "value_2"])
        self.assertEqual(tables[0]["rows"], [
            {"label": "Revenue", "value_1": "100", "value_2": "90"},
            {"label": "Cash", "value_1": "25", "value_2": "20"},
            {"label": "Total assets", "value_1": "500", "value_2": "450"},
        ])
        self.assertEqual(tables[0]["metadata"]["table_extraction_method"], "tesseract.tsv_aligned_columns")
        self.assertEqual(tables[0]["metadata"]["row_cell_bboxes"][0], {
            "label": [10, 40, 85, 48],
            "value_1": [110, 40, 140, 48],
            "value_2": [210, 40, 240, 48],
        })

    def test_ocr_table_columns_ignore_account_codes_and_note_references(self):
        words = [
            (35, 20, 185, 28, "Period", 1, 0, 1),
            (260, 20, 330, 28, "31122024", 1, 0, 2),
            (400, 20, 470, 28, "31122023", 1, 0, 3),
        ]
        for row, (label, account, note, current, previous) in enumerate((
            ("Revenue", "01", "23", "100000", "90000"),
            ("Cash balance", "02", "24", "25000", "20000"),
            ("Total assets", "03", "25", "500000", "450000"),
        )):
            y = 40 + row * 20
            words.extend([
                (10, y, 20, y + 8, account, 1, row, 1),
                (35, y, 185, y + 8, label, 1, row, 2),
                (150, y, 162, y + 8, note, 1, row, 3),
                (260, y, 330, y + 8, current, 1, row, 4),
                (400, y, 470, y + 8, previous, 1, row, 5),
            ])

        tables = PDFProcessor._tables_from_aligned_words(words, fitz.Rect(0, 0, 520, 200), 1)

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["columns"], ["label", "31/12/2024", "31/12/2023"])
        self.assertEqual(tables[0]["rows"], [
            {"label": "Revenue", "31/12/2024": "100000", "31/12/2023": "90000"},
            {"label": "Cash balance", "31/12/2024": "25000", "31/12/2023": "20000"},
            {"label": "Total assets", "31/12/2024": "500000", "31/12/2023": "450000"},
        ])

    def test_ocr_table_columns_preserve_side_by_side_financial_tables(self):
        words = []
        for row, (left, right) in enumerate((
            (("Cash", "100", "90"), ("Payables", "40", "30")),
            (("Inventory", "50", "45"), ("Borrowings", "25", "20")),
            (("Total assets", "500", "450"), ("Total liabilities", "200", "180")),
        )):
            y = 40 + row * 20
            words.extend([
                (30, y, 120, y + 8, left[0], 1, row, 1),
                (200, y, 230, y + 8, left[1], 1, row, 2),
                (300, y, 330, y + 8, left[2], 1, row, 3),
                (500, y, 580, y + 8, right[0], 1, row, 4),
                (650, y, 680, y + 8, right[1], 1, row, 5),
                (750, y, 780, y + 8, right[2], 1, row, 6),
            ])

        tables = PDFProcessor._tables_from_aligned_words(words, fitz.Rect(0, 0, 850, 120), 1)

        self.assertEqual(len(tables), 2)
        self.assertEqual(tables[0]["rows"][0], {"label": "Cash", "value_1": "100", "value_2": "90"})
        self.assertEqual(tables[1]["rows"][0], {"label": "Payables", "value_1": "40", "value_2": "30"})

    def test_tesseract_tsv_boxes_are_scaled_back_to_pdf_points(self):
        pdf = fitz.open()
        page = pdf.new_page(width=100, height=100)
        processor = PDFProcessor({"ocr_fallback": True})
        processor.ocr_available = True
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t15\t30\t30\t15\t95\tRevenue\n"
        )
        with patch(
            "core.document_processing.processors.pdf_processor.subprocess.run",
            return_value=SimpleNamespace(stdout=tsv.encode("utf-8")),
        ) as run:
            words = processor._ocr_page_words(page)
        pdf.close()

        self.assertEqual(len(words), 1)
        self.assertEqual(words[0][:4], (10.0, 20.0, 30.0, 30.0))
        self.assertEqual(words[0][4], "Revenue")
        self.assertEqual(run.call_args.args[0][-3:], ["--psm", "3", "tsv"])

    def test_tesseract_tsv_boxes_follow_configured_render_scale(self):
        pdf = fitz.open()
        page = pdf.new_page(width=100, height=100)
        processor = PDFProcessor({"ocr_fallback": True, "ocr_render_scale": 2.5})
        processor.ocr_available = True
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t25\t50\t50\t25\t95\tRevenue\n"
        )
        with patch(
            "core.document_processing.processors.pdf_processor.subprocess.run",
            return_value=SimpleNamespace(stdout=tsv.encode("utf-8")),
        ):
            words = processor._ocr_page_words(page)
        pdf.close()

        self.assertEqual(words[0][:4], (10.0, 20.0, 30.0, 30.0))

    def test_visually_prominent_heading_is_carried_to_following_pages(self):
        pdf = fitz.open()
        first = pdf.new_page()
        first.insert_text((40, 55), "Financial Performance", fontsize=20, fontname="hebo")
        first.insert_textbox(
            fitz.Rect(40, 80, 550, 760),
            "Reported financial results provide context for the business. " * 30,
            fontsize=10,
        )
        second = pdf.new_page()
        second.insert_textbox(
            fitz.Rect(40, 80, 550, 760),
            "The consolidated financial statement continues on this page. " * 30,
            fontsize=10,
        )
        source = pdf.tobytes()
        pdf.close()

        result = PDFProcessor({
            "paddle_layout": False, "ocr_fallback": False, "extract_tables": False,
            "chunk_size": 1500, "chunk_overlap": 100,
        }).process({"content": source, "metadata": {"document_id": "HEADING-1"}})

        page_one = [chunk for chunk in result["chunks"] if chunk["metadata"]["page_number"] == 1]
        page_two = [chunk for chunk in result["chunks"] if chunk["metadata"]["page_number"] == 2]
        self.assertTrue(page_one)
        self.assertTrue(page_two)
        self.assertTrue(all(chunk["metadata"]["section_title"] == "Financial Performance" for chunk in page_one))
        self.assertTrue(all(chunk["metadata"]["section_title"] == "Financial Performance" for chunk in page_two))

    def test_uppercase_heading_sets_section_without_mistaking_table_text_for_heading(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((40, 55), "FINANCIAL PERFORMANCE", fontsize=10)
        page.insert_text((40, 100), "CURRENT ASSETS", fontsize=10)
        page.insert_textbox(
            fitz.Rect(40, 130, 550, 760),
            "Doanh thu và chi phí được trình bày trong báo cáo. " * 12,
            fontsize=10,
        )
        source = pdf.tobytes()
        table_bbox = fitz.Rect(30, 80, 300, 115)
        headings = PDFProcessor._extract_page_headings(page, [table_bbox])
        pdf.close()

        self.assertEqual(headings, ["FINANCIAL PERFORMANCE"])

        with patch.object(
            PDFProcessor,
            "_extract_page_tables",
            return_value=[{
                "page_number": 1, "table_index": 0, "columns": [], "rows": [],
                "metadata": {"bbox": list(table_bbox)},
            }],
        ):
            result = PDFProcessor({
                "paddle_layout": False, "ocr_fallback": False,
            }).process({"content": source, "metadata": {"document_id": "VI-SECTION"}})
        self.assertTrue(result["chunks"])
        self.assertEqual(
            result["chunks"][0]["metadata"]["section_title"],
            "FINANCIAL PERFORMANCE",
        )

    def test_explicit_table_caption_is_saved_separately_from_section(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((40, 55), "CONSOLIDATED BALANCE SHEET", fontsize=10)
        page.insert_text((40, 120), "Current assets and cash equivalents", fontsize=10)
        source = pdf.tobytes()
        pdf.close()

        with patch.object(
            PDFProcessor,
            "_extract_page_tables",
            return_value=[{
                "page_number": 1, "table_index": 0,
                "columns": ["label", "2024"],
                "rows": [{"label": "Total assets", "2024": "100"}],
                "metadata": {"bbox": [30, 90, 550, 150]},
            }],
        ):
            result = PDFProcessor({
                "paddle_layout": False, "ocr_fallback": False,
            }).process({"content": source, "metadata": {"document_id": "TABLE-CAPTION"}})

        self.assertEqual(
            result["tables"][0]["context"]["table_title"],
            "CONSOLIDATED BALANCE SHEET",
        )

    def test_ocr_numbered_headings_set_section_title_for_scanned_pdf_chunks(self):
        pdf = fitz.open()
        pdf.new_page()
        source = pdf.tobytes()
        pdf.close()
        processor = PDFProcessor({
            "paddle_layout": False, "ocr_fallback": True, "extract_tables": False,
            "chunk_size": 800, "chunk_overlap": 100,
        })
        # Keep this parser unit test independent of whether Tesseract is installed
        # on the host; the OCR call itself is replaced below.
        processor.ocr_available = True

        with patch.object(
            processor,
            "_ocr_page",
            return_value=(
                "CHAPTER IV\nArticle 12. Rights and duties of the Audit Committee\n"
                "The Audit Committee reviews the financial statements and reports."
            ),
        ):
            result = processor.process({"content": source, "metadata": {"document_id": "SCAN-1"}})

        self.assertTrue(result["chunks"])
        self.assertEqual(result["chunks"][0]["metadata"]["text_extraction_method"], "tesseract")
        self.assertEqual(
            result["chunks"][0]["metadata"]["section_title"],
            "Article 12. Rights and duties of the Audit Committee",
        )

    def test_ocr_heading_detection_keeps_clear_headings_and_ignores_numbered_prose(self):
        text = (
            "SYNTHETIC DEMO POLICY - NOT A REAL COMPANY POLICY\n"
            "Mục đích và phạm vi\n"
            "Quy tắc này áp dụng cho tồn kho.\n"
            "Đầu ra agent cần có\n"
            "(1) snapshot/kỳ và số liệu SQL; (2) tín hiệu và phần giao nhau."
        )

        self.assertEqual(
            PDFProcessor._extract_ocr_page_headings(text),
            ["Mục đích và phạm vi", "Đầu ra agent cần có"],
        )
        self.assertEqual(
            PDFProcessor._extract_ocr_page_headings(
                "Region Delivered sample orders Median transit days Avg fee units",
                allow_unstructured=False,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
