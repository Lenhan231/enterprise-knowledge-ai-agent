import builtins
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.document_processing.processors.pdf_processor import PDFProcessor


class PDFUploadProcessingTest(unittest.TestCase):
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

    def test_numeric_scan_reuses_render_between_text_and_table_ocr(self):
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
        self.assertIs(text_ocr.call_args.args[1], table_ocr.call_args.args[1])

    def test_mixed_page_appends_ocr_without_losing_native_text(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_textbox(
            fitz.Rect(40, 650, 550, 780),
            "Native report context remains searchable. " * 3,
        )
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 500, 400), False)
        page.insert_image(fitz.Rect(40, 40, 550, 600), pixmap=pixmap)
        source = pdf.tobytes()
        pdf.close()

        with patch("core.document_processing.processors.pdf_processor.shutil.which", return_value="/usr/bin/tesseract"), \
             patch("core.document_processing.processors.pdf_processor.subprocess.run", return_value=SimpleNamespace(
                 stdout="Net revenue 2024: 61.8 trillion VND".encode("utf-8")
             )) as run:
            result = PDFProcessor({
                "paddle_layout": False, "ocr_fallback": True, "ocr_language": "vie+eng",
                "extract_tables": False, "chunk_size": 500, "chunk_overlap": 50,
            }).process({"content": source, "metadata": {"document_id": "MIXED-1"}})

        run.assert_called_once()
        combined_text = " ".join(chunk["text"] for chunk in result["chunks"])
        self.assertIn("Native report context", combined_text)
        self.assertIn("61.8 trillion", combined_text)
        self.assertEqual(result["chunks"][0]["metadata"]["text_extraction_method"], "pymupdf+tesseract")

    def test_detected_pdf_tables_have_explicit_layout_metadata(self):
        table = SimpleNamespace(
            header=SimpleNamespace(names=["Metric"], external=False),
            extract=lambda: [["Metric"], ["Revenue"]],
        )
        page = SimpleNamespace(find_tables=lambda: SimpleNamespace(tables=[table]))

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


if __name__ == "__main__":
    unittest.main()
