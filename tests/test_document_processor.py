import io
from pathlib import Path
import sys
import unittest
import zipfile
from unittest.mock import Mock, patch

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.document_processing.processors.document_processor import DocumentProcessor
from core.document_processing.processors.image.processor import ImageProcessor
from core.document_processing.processors.pdf.processor import PDFProcessor


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        for name, content in files.items():
            package.writestr(name, content)
    return output.getvalue()


class DocumentProcessorTest(unittest.TestCase):
    def setUp(self):
        self.processor = DocumentProcessor()

    def test_document_title_and_uploader_are_not_copied_into_chunk_metadata(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((40, 50), "Revenue and operations report content.")
        source = pdf.tobytes()
        pdf.close()

        result = self.processor.process("report.pdf", source, {
            "document_id": "DOC-1", "title": "Database title", "uploaded_by": "admin",
        })

        metadata = result["chunks"][0]["metadata"]
        self.assertNotIn("title", metadata)
        self.assertNotIn("uploaded_by", metadata)
        self.assertEqual(metadata["filename"], "report.pdf")

    def test_docx_extracts_paragraphs_and_structured_table(self):
        source = archive({"word/document.xml": """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
          <w:p><w:r><w:t>Annual revenue was 100 VND.</w:t></w:r></w:p><w:p><w:r><w:t>Profit was 25 VND.</w:t></w:r></w:p>
          <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Year</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Revenue</w:t></w:r></w:p></w:tc></w:tr>
          <w:tr><w:tc><w:p><w:r><w:t>2024</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>100</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        </w:body></w:document>"""})
        result = self.processor.process("report.docx", source, {"document_id": "D1"})
        self.assertIn("Annual revenue", result["chunks"][0]["text"])
        self.assertEqual(
            [chunk["metadata"]["chunk_index"] for chunk in result["chunks"]],
            list(range(len(result["chunks"]))),
        )
        self.assertEqual(result["tables"][0]["rows"], [{"Year": "2024", "Revenue": "100"}])

    def test_docx_heading_style_sets_section_title_for_following_chunks(self):
        source = archive({"word/document.xml": """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
          <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Financial performance</w:t></w:r></w:p>
          <w:p><w:r><w:t>Revenue was 100 billion VND.</w:t></w:r></w:p>
          <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Profit</w:t></w:r></w:p>
          <w:p><w:r><w:t>Profit was 25 billion VND.</w:t></w:r></w:p>
        </w:body></w:document>"""})

        result = self.processor.process("report.docx", source, {})

        self.assertEqual(
            [chunk["metadata"]["section_title"] for chunk in result["chunks"]],
            ["Financial performance", "Financial performance", "Profit", "Profit"],
        )

    def test_docx_office_math_is_kept_in_passage_and_marked_in_metadata(self):
        source = archive({"word/document.xml": """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body>
          <w:p><w:r><w:t>Revenue relation: </w:t></w:r><m:oMath><m:sup><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sup><m:r><m:t>= y</m:t></m:r></m:oMath></w:p>
        </w:body></w:document>"""})

        result = self.processor.process("equation.docx", source, {})

        self.assertIn("Revenue relation: x2= y", result["chunks"][0]["text"])
        self.assertTrue(result["chunks"][0]["metadata"]["contains_formula"])
        self.assertEqual(result["chunks"][0]["metadata"]["formula_text"], "x2= y")

    def test_formula_recognition_opt_in_enables_paddle_layout_for_pdf_uploads(self):
        processor = DocumentProcessor({"paddle_formula_recognition": True})
        with patch(
            "core.document_processing.processors.document_processor.PDFProcessor",
        ) as pdf_type:
            pdf_type.return_value.process.return_value = {"chunks": [], "tables": []}
            processor.process("report.pdf", b"pdf bytes", {"document_id": "PDF-FORMULA"})

        settings = pdf_type.call_args.args[0]
        self.assertTrue(settings["paddle_layout"])
        self.assertTrue(settings["paddle_formula_recognition"])

    def test_pptx_preserves_slide_number(self):
        source = archive({"ppt/slides/slide1.xml": """<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <p:spTree><p:sp><p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>Financial overview</a:t></a:r></a:p></p:txBody></p:sp>
          <a:graphicFrame><a:graphic><a:graphicData><a:tbl>
            <a:tr><a:tc><a:txBody><a:p><a:r><a:t>Year</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>Revenue</a:t></a:r></a:p></a:txBody></a:tc></a:tr>
            <a:tr><a:tc><a:txBody><a:p><a:r><a:t>2024</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>100 VND</a:t></a:r></a:p></a:txBody></a:tc></a:tr>
          </a:tbl></a:graphicData></a:graphic></a:graphicFrame></p:spTree></p:sld>"""})
        result = self.processor.process("report.pptx", source, {})
        self.assertEqual(result["chunks"][0]["metadata"]["page_number"], 1)
        self.assertEqual(result["chunks"][0]["metadata"]["section_title"], "Financial overview")
        self.assertIn("Revenue", result["chunks"][0]["text"])
        self.assertEqual(result["tables"][0]["page_number"], 1)
        self.assertEqual(result["tables"][0]["columns"], ["Year", "Revenue"])
        self.assertEqual(result["tables"][0]["rows"], [{"Year": "2024", "Revenue": "100 VND"}])
        self.assertEqual(result["tables"][0]["metadata"]["slide_number"], 1)

    def test_xlsx_extracts_rows_with_shared_strings(self):
        source = archive({
            "xl/workbook.xml": """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Finance" sheetId="1" r:id="rId1"/></sheets></workbook>""",
            "xl/_rels/workbook.xml.rels": """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>""",
            "xl/sharedStrings.xml": """<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Year</t></si><si><t>Revenue</t></si><si><t>2024</t></si></sst>""",
            "xl/worksheets/sheet1.xml": """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>100</v></c></row><row r="3"><c r="A3" t="inlineStr"><is><t>Total</t></is></c><c r="B3"><f>SUM(B2:B2)</f><v>100</v></c></row></sheetData></worksheet>""",
        })
        result = self.processor.process("report.xlsx", source, {})
        self.assertEqual(result["tables"][0]["rows"], [
            {"Year": "2024", "Revenue": "100"},
            {"Year": "Total", "Revenue": "100"},
        ])
        self.assertEqual(result["tables"][0]["metadata"]["formulas"], [{
            "cell": "B3", "formula": "=SUM(B2:B2)", "formula_type": None,
            "formula_ref": None, "cached_value": "100",
        }])
        self.assertIn("B3: =SUM(B2:B2) [cached value: 100]", result["chunks"][0]["text"])
        self.assertIn("Finance", result["chunks"][0]["metadata"]["sheet_name"])
        self.assertEqual(result["chunks"][0]["metadata"]["section_title"], "Finance")

    def test_text_file_strips_utf8_bom_and_keeps_document_provenance(self):
        result = self.processor.process(
            "notes.md",
            b"\xef\xbb\xbfRevenue was 100 VND.",
            {"document_id": "D-TEXT", "domain": "finance"},
        )

        self.assertEqual([chunk["text"] for chunk in result["chunks"]], ["Revenue was 100 VND."])
        self.assertEqual(result["chunks"][0]["metadata"]["document_id"], "D-TEXT")
        self.assertEqual(result["chunks"][0]["metadata"]["domain"], "finance")
        self.assertEqual(result["chunks"][0]["metadata"]["format"], "MD")
        self.assertEqual(result["chunks"][0]["metadata"]["chunk_index"], 0)
        self.assertEqual(result["chunks"][0]["metadata"]["chunk_strategy"], "sentence")

    def test_text_file_with_trailing_newline_is_not_treated_as_empty(self):
        result = self.processor.process(
            "notes.txt",
            b"Revenue was 100 VND.\n",
            {"document_id": "D-TRAILING-NEWLINE"},
        )

        self.assertEqual([chunk["text"] for chunk in result["chunks"]], ["Revenue was 100 VND."])

    def test_fixed_chunk_strategy_is_configurable_for_upload_ablation(self):
        processor = DocumentProcessor({"chunking_strategy": "fixed", "chunk_size": 30, "chunk_overlap": 5})
        result = processor.process(
            "notes.txt",
            b"First sentence. Second sentence. Third sentence.",
            {"document_id": "D-FIXED"},
        )

        self.assertGreater(len(result["chunks"]), 1)
        self.assertTrue(all(chunk["metadata"]["chunk_strategy"] == "fixed" for chunk in result["chunks"]))
        self.assertEqual(result["tables"], [])

    def test_image_ocr_uses_configured_language_and_keeps_provenance(self):
        processor = DocumentProcessor({"ocr_language": "vie+eng"})
        completed = Mock(stdout=b"Doanh thu nam 2024 la 100 ty dong.\n")
        with patch(
            "core.document_processing.processors.image.processor.subprocess.run",
            return_value=completed,
        ) as run:
            result = processor.process(
                "report.tiff",
                b"image bytes",
                {"document_id": "D-IMAGE", "domain": "finance"},
            )

        command = run.call_args.args[0]
        self.assertEqual(command[:6], ["tesseract", "stdin", "stdout", "-l", "vie+eng", "--psm"])
        self.assertEqual(command[-2:], ["--psm", "11"])
        self.assertEqual(run.call_args.kwargs["input"], b"image bytes")
        self.assertEqual(run.call_args.kwargs["timeout"], 90)
        self.assertEqual(result["chunks"][0]["text"], "Doanh thu nam 2024 la 100 ty dong.")
        self.assertEqual(result["chunks"][0]["metadata"]["text_extraction_method"], "tesseract")
        self.assertEqual(result["chunks"][0]["metadata"]["document_id"], "D-IMAGE")
        self.assertEqual(result["chunks"][0]["metadata"]["format"], "TIFF")
        self.assertEqual(result["tables"], [])

    def test_opt_in_vision_caption_adds_a_separate_source_marked_chunk(self):
        processor = DocumentProcessor({"vision_captioning": True})
        with (
            patch.object(ImageProcessor, "_ocr", return_value="Revenue 100 VND"),
            patch("core.llm.groq_provider.GroqProvider") as provider_type,
        ):
            provider = provider_type.return_value
            provider.caption_image.return_value = "A chart labels revenue as 100 VND."
            provider.vision_model_name = "qwen/qwen3.8-27b"
            result = processor.process("chart.png", b"png bytes", {"document_id": "D-CAPTION"})

        provider.caption_image.assert_called_once_with(b"png bytes", "image/png")
        provider.close.assert_called_once()
        self.assertEqual(len(result["chunks"]), 2)
        caption = result["chunks"][1]
        self.assertEqual(caption["text"], "AI-generated image caption (unverified): A chart labels revenue as 100 VND.")
        self.assertEqual(caption["metadata"]["layout_type"], "figure_caption")
        self.assertEqual(caption["metadata"]["text_extraction_method"], "groq_vision_caption")
        self.assertEqual(caption["metadata"]["caption_model"], "qwen/qwen3.8-27b")
        self.assertTrue(caption["metadata"]["is_model_generated"])

    def test_vision_caption_failure_keeps_ocr_text(self):
        processor = DocumentProcessor({"vision_captioning": True})
        with (
            patch.object(ImageProcessor, "_ocr", return_value="Scanned policy title"),
            patch("core.llm.groq_provider.GroqProvider") as provider_type,
        ):
            provider_type.return_value.caption_image.side_effect = RuntimeError("provider unavailable")
            result = processor.process("scan.jpg", b"image bytes", {"document_id": "D-CAPTION-FAIL"})

        self.assertEqual([chunk["text"] for chunk in result["chunks"]], ["Scanned policy title"])
        provider_type.return_value.close.assert_called_once()

    def test_image_ocr_recovers_table_from_word_boxes(self):
        document = fitz.open()
        page = document.new_page(width=300, height=200)
        image_bytes = page.get_pixmap(alpha=False).tobytes("png")
        document.close()
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
        table_scales = []

        def read_table_words(processor, page, pixmap=None):
            table_scales.append((processor.config["ocr_render_scale"], processor.config["ocr_table_render_scale"]))
            return words

        with (
            patch.object(ImageProcessor, "_ocr", return_value="Revenue 100 90\nCash 25 20\nTotal assets 500 450"),
            patch(
                "core.document_processing.processors.pdf.processor.PDFProcessor._ocr_page_words",
                autospec=True, side_effect=read_table_words,
            ),
        ):
            result = self.processor.process("scan.png", image_bytes, {"document_id": "SCAN-TABLE"})

        self.assertEqual(len(result["tables"]), 1)
        self.assertEqual(result["tables"][0]["rows"][-1], {
            "label": "Total assets", "value_1": "500", "value_2": "450",
        })
        self.assertEqual(result["tables"][0]["metadata"]["document_id"], "SCAN-TABLE")
        self.assertEqual(table_scales, [(2.5, 2.5)])
        self.assertEqual(result["tables"][0]["metadata"]["ocr"], {
            "engine": "tesseract", "language": "vie+eng",
            "table_psm": 6, "render_scale": 2.5,
        })

    def test_word_box_table_recovers_left_aligned_values_with_variable_widths(self):
        words = []
        rows = (
            ("Revenue", "61,824", "59,723", 48, 48),
            ("Profit", "9,453", "8,000", 39, 38),
            ("Assets", "44,000", "42,000", 53, 53),
        )
        for row_index, (label, first, second, first_width, second_width) in enumerate(rows):
            y = 30 + row_index * 24
            words.extend([
                (10, y, 80, y + 9, label, 1, row_index, 1),
                (150, y, 150 + first_width, y + 9, first, 1, row_index, 2),
                (300, y, 300 + second_width, y + 9, second, 1, row_index, 3),
            ])

        tables = PDFProcessor._tables_from_aligned_words(words, fitz.Rect(0, 0, 400, 120), 1)

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["metadata"]["column_alignment"], "left")
        self.assertEqual(tables[0]["rows"], [
            {"label": "Revenue", "value_1": "61,824", "value_2": "59,723"},
            {"label": "Profit", "value_1": "9,453", "value_2": "8,000"},
            {"label": "Assets", "value_1": "44,000", "value_2": "42,000"},
        ])

    def test_rejects_invalid_office_package(self):
        with self.assertRaisesRegex(ValueError, "Invalid Office archive"):
            self.processor.process("bad.docx", b"not a package", {})

    def test_rejects_office_zip_bomb_before_xml_parsing(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
            package.writestr("word/document.xml", b"<document>" + (b"A" * 2_000_000) + b"</document>")
        source = output.getvalue()
        with self.assertRaisesRegex(ValueError, "compression ratio"):
            self.processor.process("bomb.docx", source, {})

    def test_rejects_office_archive_with_too_many_entries(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as package:
            for index in range(10_001):
                package.writestr(f"entry-{index}", b"x")
        with self.assertRaisesRegex(ValueError, "too many archive entries"):
            self.processor.process("many.docx", output.getvalue(), {})


if __name__ == "__main__":
    unittest.main()
