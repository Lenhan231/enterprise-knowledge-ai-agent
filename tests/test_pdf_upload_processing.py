import builtins
import json
import re
import shutil
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.document_processing.processors.pdf.processor import PDFProcessor
from core.document_processing.document_processor import DocumentProcessor


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
        self.assertNotIn("orientation_correction_degrees", table["metadata"]["ocr"])
        self.assertEqual(table["columns"], [
            "Region", "Delivered sample orders", "Median transit days", "Avg fee units",
        ])
        self.assertEqual(table["rows"], [
            {"Region": "East", "Delivered sample orders": "120", "Median transit days": "3.0", "Avg fee units": "42.50"},
            {"Region": "Central", "Delivered sample orders": "95", "Median transit days": "4.0", "Avg fee units": "48.75"},
            {"Region": "West", "Delivered sample orders": "80", "Median transit days": "5.0", "Avg fee units": "55.25"},
        ])
        self.assertTrue(all(
            "deskew_correction_degrees" not in chunk["metadata"].get("ocr", {})
            for chunk in parsed["chunks"]
        ))

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is required for the skewed-scan integration fixture")
    def test_upload_deskews_scanned_text_and_records_the_correction(self):
        from io import BytesIO
        from PIL import Image
        from tools.processing.evaluate_ocr import error_rate, normalize

        root = Path(__file__).resolve().parents[1]
        source = fitz.open(root / "data/evaluation/ocr/commerce_synthetic_policy_scan_demo.pdf")
        page = source[0]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        reference_data = json.loads((root / "data/evaluation/ocr/commerce_scan_ground_truth.json").read_text())
        reference = reference_data["pages"][0]["reference_text"]
        image = Image.open(BytesIO(pixmap.tobytes("png")))
        skewed = image.rotate(-3, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(248, 248, 248))
        image_bytes = BytesIO()
        skewed.save(image_bytes, format="PNG")
        pdf = fitz.open()
        output_page = pdf.new_page(width=page.rect.width, height=page.rect.height)
        output_page.insert_image(output_page.rect, stream=image_bytes.getvalue())
        skewed_pdf = pdf.tobytes()
        source.close()
        pdf.close()

        parsed_without_deskew = DocumentProcessor({
            "paddle_layout": False, "ocr_deskew": False,
        }).process("skewed-synthetic-scan.pdf", skewed_pdf, {"document_id": "OCR-SKEW-BASELINE"})
        parsed_with_deskew = DocumentProcessor({
            "paddle_layout": False,
        }).process("skewed-synthetic-scan.pdf", skewed_pdf, {"document_id": "OCR-SKEW-CORRECTED"})
        baseline_text = " ".join(chunk["text"] for chunk in parsed_without_deskew["chunks"])
        corrected_text = " ".join(chunk["text"] for chunk in parsed_with_deskew["chunks"])
        baseline_cer = error_rate(normalize(reference), normalize(baseline_text))
        corrected_cer = error_rate(normalize(reference), normalize(corrected_text))

        self.assertGreater(baseline_cer, 0.05)
        self.assertLess(corrected_cer, baseline_cer / 2)
        self.assertTrue(any(
            2.5 <= abs(chunk["metadata"]["ocr"]["deskew_correction_degrees"]) <= 4.5
            for chunk in parsed_with_deskew["chunks"]
            if chunk["metadata"].get("ocr", {}).get("deskew_correction_degrees") is not None
        ))

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is required for the skewed-table integration fixture")
    def test_deskewed_page_text_keeps_table_extraction_on_source_geometry(self):
        from io import BytesIO
        from PIL import Image

        root = Path(__file__).resolve().parents[1]
        source = fitz.open(root / "data/evaluation/ocr/commerce_synthetic_policy_scan_demo.pdf")
        page = source[1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        skewed = Image.open(BytesIO(pixmap.tobytes("png"))).rotate(
            -3, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(248, 248, 248),
        )
        image_bytes = BytesIO()
        skewed.save(image_bytes, format="PNG")
        source_rect = page.rect
        source.close()
        pdf = fitz.open()
        output_page = pdf.new_page(width=source_rect.width, height=source_rect.height)
        output_page.insert_image(output_page.rect, stream=image_bytes.getvalue())
        skewed_pdf = pdf.tobytes()
        pdf.close()

        parsed = DocumentProcessor({"paddle_layout": False}).process(
            "skewed-synthetic-table.pdf", skewed_pdf, {"document_id": "OCR-SKEW-TABLE"},
        )

        self.assertEqual(len(parsed["tables"]), 1)
        table = parsed["tables"][0]
        self.assertEqual([row["Region"] for row in table["rows"]], ["East", "Central", "West"])
        self.assertEqual([row["Avg fee units"] for row in table["rows"]], ["42.50", "48.75", "55.25"])
        self.assertTrue(any(
            chunk["metadata"].get("ocr", {}).get("deskew_correction_degrees")
            for chunk in parsed["chunks"]
        ))
        self.assertTrue(source_rect.contains(fitz.Rect(table["metadata"]["bbox"])))
        self.assertTrue(all(
            source_rect.contains(fitz.Rect(box))
            for row in table["metadata"]["row_cell_bboxes"]
            for box in row.values() if box
        ))

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is required for orientation detection")
    def test_sideways_scanned_pdf_upload_is_corrected_and_table_boxes_keep_source_coordinates(self):
        from io import BytesIO
        from PIL import Image

        root = Path(__file__).resolve().parents[1]
        source = fitz.open(root / "data/evaluation/ocr/commerce_synthetic_policy_scan_demo.pdf")
        pixmap = source[1].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        source.close()
        sideways = Image.open(BytesIO(pixmap.tobytes("png"))).rotate(90, expand=True)
        image_bytes = BytesIO()
        sideways.save(image_bytes, format="PNG")

        pdf = fitz.open()
        page = pdf.new_page(width=sideways.width / 2.5, height=sideways.height / 2.5)
        page.insert_image(page.rect, stream=image_bytes.getvalue())
        source_pdf = pdf.tobytes()
        source_rect = page.rect
        pdf.close()

        parsed = DocumentProcessor({"paddle_layout": False}).process(
            "sideways-synthetic-scan.pdf", source_pdf, {"document_id": "OCR-ROTATED"},
        )

        self.assertEqual(len(parsed["tables"]), 1)
        table = parsed["tables"][0]
        self.assertEqual(table["rows"], [
            {"Region": "East", "Delivered sample orders": "120", "Median transit days": "3.0", "Avg fee units": "42.50"},
            {"Region": "Central", "Delivered sample orders": "95", "Median transit days": "4.0", "Avg fee units": "48.75"},
            {"Region": "West", "Delivered sample orders": "80", "Median transit days": "5.0", "Avg fee units": "55.25"},
        ])
        self.assertEqual(table["metadata"]["ocr"]["orientation_correction_degrees"], 90)
        chunk_text = " ".join(chunk["text"] for chunk in parsed["chunks"])
        self.assertIn("Synthetic regional logistics sample", chunk_text)
        self.assertIn("42.50", chunk_text)
        bbox = fitz.Rect(table["metadata"]["bbox"])
        self.assertTrue(source_rect.contains(bbox))
        self.assertTrue(all(
            source_rect.contains(fitz.Rect(box))
            for row in table["metadata"]["row_cell_bboxes"]
            for box in row.values() if box
        ))

    def test_orientation_bbox_transform_handles_all_tesseract_quarter_turns(self):
        expected = {
            90: [150.0, 20.0, 170.0, 40.0],
            180: [160.0, 50.0, 180.0, 70.0],
            270: [30.0, 60.0, 50.0, 80.0],
        }
        for degrees, expected_bbox in expected.items():
            with self.subTest(degrees=degrees):
                table = {"metadata": {
                    "bbox": [20, 30, 40, 50],
                    "ocr_column_header_bbox": [20, 30, 40, 50],
                    "row_cell_bboxes": [{"label": [20, 30, 40, 50]}],
                }}
                PDFProcessor._restore_table_coordinates(
                    table, fitz.Rect(0, 0, 200, 100), degrees,
                )
                metadata = table["metadata"]
                self.assertEqual(metadata["bbox"], expected_bbox)
                self.assertEqual(metadata["ocr_column_header_bbox"], expected_bbox)
                self.assertEqual(metadata["row_cell_bboxes"][0]["label"], expected_bbox)

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is required for the split-table scan fixture")
    def test_scanned_table_continuation_links_adjacent_page_segments_and_inherits_title(self):
        from io import BytesIO
        from PIL import Image

        columns = [(40, "Region"), (230, "Delivered sample orders"), (390, "Median transit days"), (515, "Avg fee units")]
        rows = [
            [(40, "East"), (260, "120"), (425, "3.0"), (535, "42.50")],
            [(40, "Central"), (260, "95"), (425, "4.0"), (535, "48.75")],
            [(40, "West"), (260, "80"), (425, "5.0"), (535, "55.25")],
            [(40, "South"), (260, "70"), (425, "6.0"), (535, "61.00")],
            [(40, "North"), (260, "60"), (425, "7.0"), (535, "59.00")],
            [(40, "Coastal"), (260, "50"), (425, "8.0"), (535, "63.00")],
        ]
        source = fitz.open()
        for page_number, y_positions in enumerate(([570, 630, 680, 730], [100, 155, 205, 255]), start=1):
            page = source.new_page(width=595, height=842)
            if page_number == 1:
                page.insert_text((40, 510), "Synthetic regional logistics table", fontsize=14)
            for x, text in columns:
                page.insert_text((x, y_positions[0]), text, fontsize=9)
            page_rows = rows[(page_number - 1) * 3:page_number * 3]
            for row, y in zip(page_rows, y_positions[1:]):
                for (x, _), (_, value) in zip(columns, row):
                    page.insert_text((x, y), value, fontsize=9)

        scanned = fitz.open()
        for page_index, page in enumerate(source):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            if page_index == 0:
                sideways = Image.open(BytesIO(pixmap.tobytes("png"))).rotate(90, expand=True)
                image_bytes = BytesIO()
                sideways.save(image_bytes, format="PNG")
                image_page = scanned.new_page(width=sideways.width / 2, height=sideways.height / 2)
                image_page.insert_image(image_page.rect, stream=image_bytes.getvalue())
            else:
                image_page = scanned.new_page(width=page.rect.width, height=page.rect.height)
                image_page.insert_image(image_page.rect, pixmap=pixmap)
        pdf_bytes = scanned.tobytes()
        source.close()
        scanned.close()

        parsed = DocumentProcessor({"paddle_layout": False}).process(
            "split-synthetic-table.pdf", pdf_bytes, {"document_id": "OCR-SPLIT-TABLE"},
        )

        self.assertEqual(len(parsed["tables"]), 2)
        first, second = parsed["tables"]
        self.assertEqual(first["page_number"], 1)
        self.assertEqual(second["page_number"], 2)
        self.assertEqual(first["metadata"]["continuation_group_id"], second["metadata"]["continuation_group_id"])
        self.assertEqual(first["metadata"]["continued_to_page"], 2)
        self.assertEqual(second["metadata"]["continued_from_page"], 1)
        self.assertEqual(first["metadata"]["ocr"]["orientation_correction_degrees"], 90)
        self.assertEqual(first["context"]["table_title"], "Synthetic regional logistics table")
        self.assertEqual(second["context"]["table_title"], "Synthetic regional logistics table")
        self.assertEqual([row["Region"] for row in first["rows"]], ["East", "Central", "West"])
        self.assertEqual([row["Region"] for row in second["rows"]], ["South", "North", "Coastal"])
        table_chunks = {
            chunk["metadata"]["page_number"]: chunk
            for chunk in parsed["chunks"] if chunk["metadata"].get("layout_type") == "table"
        }
        self.assertIn("Table: Synthetic regional logistics table", table_chunks[2]["text"])
        self.assertEqual(table_chunks[2]["metadata"]["continued_from_page"], 1)

    def test_table_continuation_link_skips_mismatched_or_ambiguous_segments(self):
        pdf = fitz.open()
        pdf.new_page(width=595, height=842)
        pdf.new_page(width=595, height=842)

        def table(page_number, table_index, columns, bbox):
            return {
                "page_number": page_number, "table_index": table_index, "columns": columns,
                "context": {}, "metadata": {"bbox": bbox},
            }

        mismatched = [
            table(1, 0, ["Region", "2025"], [20, 700, 400, 820]),
            table(2, 0, ["Region", "2024"], [20, 20, 400, 200]),
        ]
        PDFProcessor._link_continued_tables(mismatched, pdf)
        self.assertNotIn("continuation_group_id", mismatched[0]["metadata"])

        ambiguous = [
            table(1, 0, ["Region", "2025"], [20, 700, 400, 820]),
            table(1, 1, ["Region", "2025"], [20, 710, 400, 825]),
            table(2, 0, ["Region", "2025"], [20, 20, 400, 200]),
        ]
        PDFProcessor._link_continued_tables(ambiguous, pdf)
        self.assertTrue(all(
            "continuation_group_id" not in item["metadata"] for item in ambiguous
        ))
        pdf.close()

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
        table_chunks = [chunk for chunk in parsed["chunks"] if chunk["metadata"].get("layout_type") == "table"]
        self.assertTrue(table_chunks)
        self.assertIn("Table: Synthetic regional logistics sample", table_chunks[0]["text"])
        self.assertEqual(table_chunks[0]["metadata"]["table_title"], "Synthetic regional logistics sample")
        page_two_text = " ".join(
            chunk["text"] for chunk in parsed["chunks"]
            if chunk["metadata"].get("page_number") == 2
            and chunk["metadata"].get("layout_type") == "text"
        )
        self.assertIn("Every record on this page is invented", page_two_text)
        self.assertNotIn("Median transit days 30", page_two_text)
        self.assertIn("Median transit days: 3.0", table_chunks[0]["text"])
        self.assertEqual(parsed["chunks"][1]["metadata"]["ocr"]["page_psm"], 3)
        self.assertEqual(parsed["chunks"][1]["metadata"]["ocr"]["render_scale"], 2.5)

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
            "context": {"table_title": "Annual Commerce Performance"},
            "metadata": {"table_extraction_method": "test.extractor"},
        }]

        result = processor._replace_flat_table_chunks(chunks, tables)

        self.assertEqual(len(result), 1)
        self.assertIn("Metric: Revenue | 2024: 100 | 2023: 90", result[0]["text"])
        self.assertEqual(result[0]["metadata"]["layout_type"], "table")
        self.assertIn("Table: Annual Commerce Performance", result[0]["text"])
        self.assertEqual(result[0]["metadata"]["table_title"], "Annual Commerce Performance")
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

    def test_pdf_page_counter_footer_is_removed_from_retrieval_chunks(self):
        pdf = fitz.open()
        for number, title in ((1, "Inventory decision principles"), (2, "Evidence needed before action")):
            page = pdf.new_page()
            page.insert_text((40, 50), title)
            page.insert_text((40, 810), f"Commerce Demo · Demo v1.0 · Page {number}/2")
        source = pdf.tobytes()
        pdf.close()

        result = PDFProcessor({
            "paddle_layout": False, "ocr_fallback": False, "extract_tables": False,
            "chunk_size": 300, "chunk_overlap": 0,
        }).process({"content": source, "metadata": {"document_id": "PDF-FOOTER"}})

        self.assertEqual(len(result["chunks"]), 2)
        self.assertEqual([chunk["metadata"]["page_number"] for chunk in result["chunks"]], [1, 2])
        self.assertEqual([chunk["text"] for chunk in result["chunks"]], [
            "Inventory decision principles", "Evidence needed before action",
        ])
        self.assertFalse(any("Page 1/2" in chunk["text"] or "Page 2/2" in chunk["text"]
                             for chunk in result["chunks"]))

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is required for the scanned-policy integration fixture")
    def test_scanned_commerce_policy_keeps_page_content_without_footer_chunks(self):
        path = Path(__file__).resolve().parents[1] / "data/commerce_knowledge/synthetic_policies/promotion-planning.pdf"
        result = DocumentProcessor({"paddle_layout": False, "extract_tables": False}).process(
            path.name, path.read_bytes(), {"document_id": "CD-POL-PROMO-001"},
        )

        self.assertEqual({chunk["metadata"]["page_number"] for chunk in result["chunks"]}, {1, 2, 3})
        self.assertTrue(any("Không được suy diễn" in chunk["text"] for chunk in result["chunks"]))
        self.assertFalse(any(re.search(r"Page\s+\d+/3\s*$", chunk["text"]) for chunk in result["chunks"]))

    def test_scanned_page_uses_tesseract_fallback(self):
        pdf = fitz.open()
        pdf.new_page()
        source = pdf.tobytes()
        pdf.close()
        with patch("core.document_processing.processors.pdf.processor.shutil.which", return_value="/usr/bin/tesseract"), \
             patch("core.document_processing.processors.pdf.processor.subprocess.run", return_value=SimpleNamespace(
                 stdout="Doanh thu thuần năm 2024 đạt 100 tỷ đồng".encode("utf-8")
             )) as run:
            result = PDFProcessor({
                "paddle_layout": False, "ocr_fallback": True, "ocr_language": "vie+eng",
                "extract_tables": False, "chunk_size": 200, "chunk_overlap": 20,
            }).process({"content": source, "metadata": {"document_id": "SCAN-1"}})
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][-4:], ["-l", "osd", "--psm", "0"])
        self.assertEqual(run.call_args_list[-1].args[0][-2:], ["--psm", "11"])
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

        with patch("core.document_processing.processors.pdf.processor.shutil.which", return_value="/usr/bin/tesseract"), \
             patch("core.document_processing.processors.pdf.processor.subprocess.run", return_value=SimpleNamespace(
                 stdout=(
                     "Native report contxt remains searchable. Native report reference stays readable. "
                     "Net revenue 2024: 61.8 trillion VND"
                 ).encode("utf-8")
             )) as run:
            result = PDFProcessor({
                "paddle_layout": False, "ocr_fallback": True, "ocr_language": "vie+eng",
                "extract_tables": False, "chunk_size": 500, "chunk_overlap": 50,
            }).process({"content": source, "metadata": {"document_id": "MIXED-1"}})

        self.assertEqual(run.call_count, 2)
        self.assertIn("osd", run.call_args_list[0].args[0])
        self.assertIn("--psm", run.call_args_list[-1].args[0])
        combined_text = " ".join(chunk["text"] for chunk in result["chunks"])
        self.assertIn("Native report context", combined_text)
        self.assertIn("Native report reference stays readable", combined_text)
        self.assertEqual(combined_text.count("Native report context remains searchable."), 1)
        self.assertEqual(combined_text.count("Native report reference stays readable."), 1)
        self.assertIn("61.8 trillion", combined_text)
        self.assertEqual(result["chunks"][0]["metadata"]["text_extraction_method"], "pymupdf+tesseract")

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is required for the mixed-page OCR fixture")
    def test_mixed_text_and_embedded_table_image_are_extracted(self):
        table_pdf = fitz.open()
        table_page = table_pdf.new_page(width=468, height=220)
        table_page.insert_text((24, 38), "Region", fontsize=14)
        table_page.insert_text((205, 38), "Orders", fontsize=14)
        table_page.insert_text((330, 38), "Transit days", fontsize=14)
        for y, region, orders, days in (
            (82, "East", "120", "4.52"),
            (128, "Central", "95", "4.51"),
            (174, "West", "80", "4.51"),
        ):
            table_page.insert_text((24, y), region, fontsize=14)
            table_page.insert_text((205, y), orders, fontsize=14)
            table_page.insert_text((330, y), days, fontsize=14)
        table_pixmap = table_page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        image_bytes = table_pixmap.tobytes("png")
        table_pdf.close()

        pdf = fitz.open()
        page = pdf.new_page(width=612, height=792)
        body = "Commerce operating report. Inventory and delivery records are reviewed by region. " * 18
        page.insert_textbox(fitz.Rect(40, 430, 560, 780), body, fontsize=9)
        page.insert_image(fitz.Rect(72, 170, 540, 390), stream=image_bytes)
        source = pdf.tobytes()
        pdf.close()

        weak_words = [
            (90 + index * 12, 190, 100 + index * 12, 205, f"weak{index}", 1, 1, index, 24.0)
            for index in range(5)
        ]
        with patch.object(PDFProcessor, "_ocr_page_words", return_value=weak_words):
            low_confidence = DocumentProcessor({"ocr_language": "eng"}).process(
                "mixed-operations-report.pdf", source, {"document_id": "MIXED-TABLE-LOW-CONFIDENCE"},
            )

        low_confidence_text = " ".join(chunk["text"] for chunk in low_confidence["chunks"])
        self.assertIn("Commerce operating report", low_confidence_text)
        self.assertNotIn("weak0", low_confidence_text)
        self.assertEqual(low_confidence["tables"], [])
        self.assertNotIn("ocr", low_confidence["chunks"][0]["metadata"])
        self.assertEqual(low_confidence["chunks"][0]["metadata"]["ocr_diagnostics"], [{
            "scope": "embedded_image_region",
            "status": "rejected",
            "reason": "low_mean_word_confidence",
            "mean_word_confidence": 24.0,
            "minimum_word_confidence": 60,
        }])

        result = DocumentProcessor({"ocr_language": "eng"}).process(
            "mixed-operations-report.pdf", source, {"document_id": "MIXED-TABLE-1"},
        )

        combined_text = " ".join(chunk["text"] for chunk in result["chunks"])
        self.assertIn("Commerce operating report", combined_text)
        self.assertIn("East", combined_text)
        self.assertEqual(result["chunks"][0]["metadata"]["text_extraction_method"], "pymupdf+tesseract")
        self.assertTrue(result["chunks"][0]["metadata"]["ocr"])
        self.assertEqual(result["chunks"][0]["metadata"]["ocr"]["scope"], "embedded_image_regions")
        self.assertEqual(result["chunks"][0]["metadata"]["ocr"]["render_scale"], 2.5)
        self.assertGreaterEqual(result["chunks"][0]["metadata"]["ocr"]["mean_word_confidence"], 60)
        self.assertEqual(len(result["tables"]), 1)
        rows = result["tables"][0]["rows"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["Region"], "East")
        self.assertEqual((rows[0]["Orders"], rows[0]["Transit days"]), ("120", "4.52"))
        self.assertGreaterEqual(result["tables"][0]["metadata"]["ocr"]["mean_word_confidence"], 60)

    def test_mixed_page_drops_ocr_lines_already_present_in_native_text(self):
        native = "SELLER EDUCATION HUB\nSHOPEE UNI\nTruy cập Quản Lý Tồn Kho\nQUẢN LÝ TỒN KHO"
        ocr = "SHOPEE UNI\nTruy cập Quản Lý Tồn Kho\nTong quan ton kho\nQuan ly ton kho"

        result = PDFProcessor._remove_ocr_duplicates(native, ocr)

        self.assertNotIn("Truy cập Quản Lý Tồn Kho", result)
        self.assertNotIn("Quan ly ton kho", result)
        self.assertNotIn("SHOPEE UNI", result)
        self.assertIn("Tong quan ton kho", result)

    def test_embedded_image_ocr_must_add_enough_new_text(self):
        native = "Sales History Demand Forecast Seasonality Create Shipment " * 4
        noisy_ocr = native * 3 + "100 Flige vCreate"
        useful_ocr = "Commerce report. Net revenue 61.8 trillion VND for the year."

        self.assertFalse(PDFProcessor._has_meaningful_ocr_additions(native, noisy_ocr))
        self.assertTrue(PDFProcessor._has_meaningful_ocr_additions("Commerce report.", useful_ocr))

    def test_noisy_embedded_ocr_is_omitted_without_losing_table_word_boxes(self):
        pdf = fitz.open()
        page = pdf.new_page()
        native = "Native report context remains searchable. " * 18
        page.insert_textbox(fitz.Rect(30, 500, 550, 760), native, fontsize=10)
        page.insert_text((30, 480), "Sales History Demand Forecast Seasonality Create Shipment")
        image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 300), False)
        page.insert_image(fitz.Rect(30, 80, 550, 450), pixmap=image)
        source = pdf.tobytes()
        pdf.close()

        words = [
            (40 + index * 8, 100, 46 + index * 8, 110, token, 1, 1, index, 90.0)
            for index, token in enumerate(("Sales", "History", "Demand", "Forecast", "Seasonality") * 12 + ("100", "Flige", "vCreate"))
        ]
        processor = PDFProcessor({
            "paddle_layout": False, "ocr_fallback": True, "ocr_language": "eng",
            "extract_tables": True,
        })
        with patch.object(processor, "_ocr_page_words", return_value=words), patch.object(
            PDFProcessor, "_extract_page_tables", return_value=[],
        ) as extract_tables:
            result = processor.process({"content": source, "metadata": {"document_id": "MIXED-OCR-NOISE"}})

        text = " ".join(chunk["text"] for chunk in result["chunks"])
        self.assertIn("Native report context remains searchable", text)
        self.assertNotIn("Flige", text)
        self.assertNotIn("vCreate", text)
        self.assertNotIn("ocr", result["chunks"][0]["metadata"])
        self.assertEqual(extract_tables.call_args.args[2], words)

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

    def test_single_row_native_table_candidate_is_rejected(self):
        table = SimpleNamespace(
            header=SimpleNamespace(names=["Metric"], external=False),
            extract=lambda: [["Metric"], ["Revenue"]],
        )
        page = SimpleNamespace(
            get_text=lambda kind: [(0, 0, 10, 10, "123"), (60, 0, 70, 10, "456"), (0, 20, 10, 30, "234"), (60, 20, 70, 30, "567"), (0, 40, 10, 50, "345"), (60, 40, 70, 50, "678")],
            find_tables=lambda strategy=None: SimpleNamespace(tables=[table] if strategy is None else []),
        )

        tables = PDFProcessor._extract_page_tables(page, 4)

        self.assertEqual(tables, [])

    def test_weak_native_candidate_does_not_block_ocr_table_fallback(self):
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
        weak_native_table = SimpleNamespace(
            header=SimpleNamespace(names=["Screenshot title"], external=False),
            extract=lambda: [["Screenshot title"], ["Shop inventory"]],
        )
        page = SimpleNamespace(
            rect=fitz.Rect(0, 0, 300, 200),
            get_text=lambda kind: words,
            find_tables=lambda strategy=None: SimpleNamespace(
                tables=[weak_native_table] if strategy is None else [],
            ),
        )

        tables = PDFProcessor._extract_page_tables(page, 4, ocr_words=words)

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["metadata"]["table_extraction_method"], "tesseract.tsv_aligned_columns")
        self.assertEqual(tables[0]["rows"][-1], {
            "label": "Total assets", "value_1": "500", "value_2": "450",
        })

    def test_native_text_table_without_numeric_cells_is_detected(self):
        pdf = fitz.open()
        page = pdf.new_page(width=600, height=400)
        x_edges = [30, 160, 290, 420, 570]
        y_edges = [80, 140, 200, 260, 320]
        for y in y_edges:
            page.draw_line((x_edges[0], y), (x_edges[-1], y))
        for x in x_edges:
            page.draw_line((x, y_edges[0]), (x, y_edges[-1]))
        matrix = [
            ["Use case", "Experiment", "Model based", "Econometric"],
            ["Optimize", "Small tests", "Counterfactual", "Long horizon"],
            ["Allocate budget", "Controlled test", "Unified data", "Channel model"],
            ["Compare network", "Holdout", "Causal model", "Slow method"],
        ]
        for row_index, row in enumerate(matrix):
            for column_index, text in enumerate(row):
                page.insert_text(
                    (x_edges[column_index] + 5, y_edges[row_index] + 35),
                    text,
                    fontsize=8,
                )

        tables = PDFProcessor._extract_page_tables(page, 1)

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["columns"], matrix[0])
        self.assertEqual(len(tables[0]["rows"]), 3)
        self.assertEqual(tables[0]["rows"][0]["Use case"], "Optimize")
        pdf.close()

    def test_native_table_uses_leaf_labels_under_merged_title_and_group_headers(self):
        matrix = [
            ["Regional Distribution Network", None, None],
            ["Distribution & Consolidation Centers", None, "Outbound Plants"],
            ["Atlanta DC", "Phoenix DC", "Dairy Plant"],
            ["Indianapolis DC", "Denver DC", "Bakery Plant"],
            ["Cincinnati DC", "Riverside DC", "Farm"],
            ["Inbound materials contact: logistics@example.com", None, None],
        ]
        table_rows = [
            SimpleNamespace(cells=[(0, 0, 250, 10), None, None]),
            SimpleNamespace(cells=[(0, 10, 150, 20), None, (150, 10, 250, 20)]),
            SimpleNamespace(cells=[(0, 20, 80, 30), (80, 20, 150, 30), (150, 20, 250, 30)]),
            SimpleNamespace(cells=[(0, 30, 80, 40), (80, 30, 150, 40), (150, 30, 250, 40)]),
            SimpleNamespace(cells=[(0, 40, 80, 50), (80, 40, 150, 50), (150, 40, 250, 50)]),
            SimpleNamespace(cells=[(0, 50, 250, 60), None, None]),
        ]
        table = SimpleNamespace(
            header=SimpleNamespace(
                names=matrix[0], external=False, cells=table_rows[0].cells,
            ),
            bbox=(0, 0, 250, 50), rows=table_rows,
            extract=lambda: matrix,
        )
        words = [
            (0, y, 10, y + 5, str(index), 0, index, 0)
            for index, y in enumerate((0, 20, 40))
        ] + [
            (60, y, 70, y + 5, str(index + 10), 0, index, 1)
            for index, y in enumerate((0, 20, 40))
        ]
        page = SimpleNamespace(
            get_text=lambda kind: words,
            find_tables=lambda: SimpleNamespace(tables=[table]),
        )

        tables = PDFProcessor._extract_page_tables(page, 8)

        self.assertEqual(tables[0]["context"]["table_title"], "Regional Distribution Network")
        self.assertEqual(tables[0]["context"]["notes"], ["Inbound materials contact: logistics@example.com"])
        self.assertEqual(tables[0]["columns"], [
            "Distribution & Consolidation Centers",
            "Distribution & Consolidation Centers (2)",
            "Outbound Plants",
        ])
        self.assertEqual(len(tables[0]["rows"]), 3)
        self.assertEqual(tables[0]["rows"][0], {
            "Distribution & Consolidation Centers": "Atlanta DC",
            "Distribution & Consolidation Centers (2)": "Phoenix DC",
            "Outbound Plants": "Dairy Plant",
        })

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
            result = PDFProcessor({
                "chunk_size": 200, "chunk_overlap": 20,
                "paddle_chart_recognition": True,
            })._process_with_paddle(
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

        self.assertFalse(paddle.PPStructureV3.call_args.kwargs["enable_mkldnn"])
        table_chunks = [chunk for chunk in result["chunks"] if chunk["metadata"]["layout_type"] == "table"]
        self.assertFalse(paddle.PPStructureV3.call_args.kwargs["use_chart_recognition"])
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
            "core.document_processing.processors.pdf.processor.subprocess.run",
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
            "core.document_processing.processors.pdf.processor.subprocess.run",
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
    def test_native_heading_wins_over_ocr_labels_from_embedded_ui(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((40, 40), "FBA Restock", fontsize=22, fontname="hebo")
        page.insert_text((40, 66), "Overview", fontsize=22, fontname="hebo")
        for y, line in zip(
            (120, 140, 160, 180),
            (
                "This guide explains how to plan inventory replenishment for products.",
                "Review demand and available stock before making a shipment.",
                "Use supplier lead time when planning replenishment quantity.",
                "Check each product before sending stock to the warehouse.",
            ),
        ):
            page.insert_text((40, y), line, fontsize=10)
        source = pdf.tobytes()
        pdf.close()

        processor = PDFProcessor({
            "paddle_layout": False, "ocr_fallback": True, "extract_tables": False,
        })
        processor.ocr_available = True
        with (
            patch.object(processor, "_needs_ocr", return_value=True),
            patch.object(
                processor,
                "_ocr_page",
                return_value=(
                    "FBA Restock Overview\nReview recommended quantity.\n"
                    "Hide recommendation"
                ),
            ),
        ):
            result = processor.process({"content": source, "metadata": {"document_id": "MIXED-SCAN"}})

        self.assertTrue(result["chunks"])
        self.assertTrue(all(
            chunk["metadata"]["section_title"] == "FBA Restock Overview"
            for chunk in result["chunks"]
        ))


if __name__ == "__main__":
    unittest.main()
