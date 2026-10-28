import sys
import unittest
from io import BytesIO
from pathlib import Path

from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from document_processing.docling_adapter.digital_born.docx_semantics import apply_docx_semantics


class DocxSemanticsTest(unittest.TestCase):
    def test_missing_default_style_preserves_paragraph_text(self):
        document = Document()
        document.add_paragraph("Paragraph without a default style")
        normal = document.styles["Normal"]._element
        normal.getparent().remove(normal)
        content = BytesIO()
        document.save(content)
        self.assertIsNone(Document(BytesIO(content.getvalue())).paragraphs[0].style)
        result = {"elements": [{"text": "Paragraph without a default style", "metadata": {}}]}

        apply_docx_semantics(result, content.getvalue())

        self.assertEqual(result["elements"][0]["text"], "Paragraph without a default style")
        self.assertEqual(result["elements"][0]["metadata"]["section_path"], [])

    def test_defined_heading_style_retains_section_structure(self):
        document = Document()
        document.add_heading("Overview", level=1)
        content = BytesIO()
        document.save(content)
        result = {"elements": [{"text": "Overview", "metadata": {}}]}

        apply_docx_semantics(result, content.getvalue())

        self.assertEqual(result["elements"][0]["metadata"]["heading_level"], 1)
        self.assertEqual(result["elements"][0]["metadata"]["section_path"], ["Overview"])
