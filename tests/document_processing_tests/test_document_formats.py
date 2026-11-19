"""File-normalization and parser routing checks."""

from io import BytesIO
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from document_processing.document_processor import DocumentProcessor
from document_processing.formats import LEGACY_OFFICE_FORMATS, matches_signature
from document_processing.image_input import normalize_image
from document_processing.legacy_office import convert_legacy_office


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="3"><rect width="4" height="3" fill="#ff0000"/></svg>'
OFFICE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def raster_bytes(format_name, *, animated=False):
    output = BytesIO()
    image = Image.new("RGB", (4, 3), "red")
    options = {"lossless": True} if format_name == "WEBP" else {}
    if animated:
        options.update(save_all=True, append_images=[Image.new("RGB", (4, 3), "blue")], duration=100)
    image.save(output, format=format_name, **options)
    return output.getvalue()


def modern_image_bytes(format_name):
    interpreter = os.getenv("DOCUMENT_PROCESSING_IMAGE_PYTHON", sys.executable)
    return subprocess.run(
        [interpreter, "-c", """
import io
import sys
from PIL import Image

image = Image.new("RGB", (32, 24), (220, 25, 25))
if sys.argv[1] == "HEIF":
    from pillow_heif import register_heif_opener
    register_heif_opener()
output = io.BytesIO()
image.save(output, format=sys.argv[1])
sys.stdout.buffer.write(output.getvalue())
""", format_name],
        check=True, capture_output=True, timeout=20,
    ).stdout


class DocumentFormatTest(unittest.TestCase):
    def test_bitmap_and_svg_render_as_png(self):
        for suffix, payload in ((".bmp", raster_bytes("BMP")), (".svg", SVG)):
            with self.subTest(suffix=suffix):
                encoded, extension = normalize_image(payload, suffix)
                self.assertEqual(extension, ".png")
                with Image.open(BytesIO(encoded)) as result:
                    self.assertEqual(result.format, "PNG")
                    self.assertEqual(result.getpixel((1, 1)), (255, 0, 0))

    def test_animated_gif_and_webp_preserve_frame_order(self):
        for format_name, suffix in (("GIF", ".gif"), ("WEBP", ".webp")):
            with self.subTest(suffix=suffix):
                encoded, extension = normalize_image(raster_bytes(format_name, animated=True), suffix)
                self.assertEqual(extension, ".tiff")
                with Image.open(BytesIO(encoded)) as result:
                    self.assertEqual(result.n_frames, 2)
                    self.assertEqual(result.getpixel((1, 1)), (255, 0, 0))
                    result.seek(1)
                    self.assertEqual(result.getpixel((1, 1)), (0, 0, 255))

    def test_heic_heif_and_avif_decode_with_the_configured_runtime(self):
        heif = modern_image_bytes("HEIF")
        avif = modern_image_bytes("AVIF")
        for suffix, payload in ((".heic", heif), (".heif", heif), (".avif", avif)):
            with self.subTest(suffix=suffix):
                encoded, extension = normalize_image(payload, suffix)
                self.assertEqual(extension, ".png")
                with Image.open(BytesIO(encoded)) as result:
                    red, green, blue = result.getpixel((1, 1))
                    self.assertEqual(result.size, (32, 24))
                    self.assertGreater(red, 170)
                    self.assertLess(max(green, blue), 60)
        self.assertFalse(matches_signature(avif, ".heic"))
        self.assertFalse(matches_signature(heif, ".avif"))

    def test_image_limits_and_invalid_content(self):
        with patch("document_processing.image_input._MAX_FRAMES", 1):
            with self.assertRaisesRegex(ValueError, "frame limit"):
                normalize_image(raster_bytes("GIF", animated=True), ".gif")
        with patch("document_processing.image_input._MAX_TOTAL_PIXELS", 20):
            with self.assertRaisesRegex(ValueError, "pixel limit"):
                normalize_image(raster_bytes("GIF", animated=True), ".gif")
        with self.assertRaisesRegex(ValueError, "does not match"):
            normalize_image(raster_bytes("BMP"), ".avif")
        with self.assertRaisesRegex(ValueError, "Could not open"):
            normalize_image(b"GIF89a", ".gif")
        with self.assertRaisesRegex(ValueError, "external references"):
            normalize_image(b'<svg><image href="file:///image.png"/></svg>', ".svg")

    def test_parser_preserves_original_format_and_animation_pages(self):
        module = ModuleType("document_processing.docling_adapter.processor")
        results = {"elements": [
            {"text": "First frame", "metadata": {"format": "TIFF", "page_number": 1}},
            {"text": "Second frame", "metadata": {"format": "TIFF", "page_number": 2}},
        ], "tables": [{"rows": [], "page_number": 2, "metadata": {"format": "TIFF"}}]}
        with (
            patch.dict(sys.modules, {module.__name__: module}),
            patch.dict(os.environ, {"DOCUMENT_PROCESSING_URL": ""}),
            patch.object(module, "DoclingProcessor", create=True) as docling,
        ):
            docling.return_value.process.return_value = results
            result = DocumentProcessor().process("scan.webp", raster_bytes("WEBP", animated=True), {})
            payload, _, document = docling.return_value.process.call_args.args
        self.assertTrue(matches_signature(payload, ".tiff"))
        self.assertEqual(document["metadata"]["format"], "TIFF")
        self.assertEqual(result["metadata"]["format"], "WEBP")
        self.assertEqual([item["metadata"]["page_number"] for item in result["elements"]], [1, 2])
        self.assertTrue(all(item["metadata"]["format"] == "WEBP" for item in result["elements"]))
        self.assertEqual(result["tables"][0]["page_number"], 2)
        self.assertEqual(result["tables"][0]["metadata"]["format"], "WEBP")

    def test_legacy_parser_passes_open_xml_to_docling(self):
        module = ModuleType("document_processing.docling_adapter.processor")
        for suffix, target_suffix in LEGACY_OFFICE_FORMATS.items():
            with (
                self.subTest(suffix=suffix),
                patch.dict(sys.modules, {module.__name__: module}),
                patch.dict(os.environ, {"DOCUMENT_PROCESSING_URL": ""}),
                patch.object(module, "DoclingProcessor", create=True) as docling,
                patch("document_processing.document_processor.convert_legacy_office",
                      return_value=(b"open xml", target_suffix)) as convert,
            ):
                docling.return_value.process.return_value = {
                    "elements": [{"text": "Report", "metadata": {"format": target_suffix[1:].upper()}}],
                }
                result = DocumentProcessor().process(f"report{suffix}", OFFICE, {})
                convert.assert_called_once_with(OFFICE, suffix)
                payload, _, document = docling.return_value.process.call_args.args
                self.assertEqual(payload, b"open xml")
                self.assertEqual(document["metadata"]["format"], target_suffix[1:].upper())
                self.assertEqual(result["elements"][0]["metadata"]["format"], suffix[1:].upper())

    def test_rejects_invalid_legacy_input_and_missing_converter(self):
        with patch("document_processing.legacy_office.shutil.which", return_value=None) as which:
            with self.assertRaisesRegex(ValueError, "does not match"):
                convert_legacy_office(b"invalid", ".doc")
            which.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "LibreOffice"):
                convert_legacy_office(OFFICE, ".doc")

    def test_new_document_extensions_do_not_enable_invoice_or_caption(self):
        for intent in ("invoice", "image_caption"):
            with self.subTest(intent=intent), self.assertRaisesRegex(ValueError, "document processing only"):
                DocumentProcessor({"intent": intent}).process("upload.avif", b"", {})

    @unittest.skipUnless(shutil.which("soffice") and importlib.util.find_spec("docling"),
                         "Requires the LibreOffice and Docling runtime")
    def test_real_legacy_office_files_remain_readable_after_conversion(self):
        from docx import Document
        from openpyxl import Workbook
        from pptx import Presentation

        word = Document()
        word.add_paragraph("Legacy Word marker")
        sheet = Workbook()
        sheet.active.append(("Item", "Amount"))
        sheet.active.append(("Legacy Excel marker", 527))
        slides = Presentation()
        slide = slides.slides.add_slide(slides.slide_layouts[5])
        slide.shapes.title.text = "Legacy PowerPoint marker"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            processor = DocumentProcessor({"docling_ocr": False, "docling_chart_recognition": False})
            for suffix, source, export_filter, marker in (
                (".doc", word, "MS Word 97", "Legacy Word marker"),
                (".xls", sheet, "MS Excel 97", "Legacy Excel marker"),
                (".ppt", slides, "MS PowerPoint 97", "Legacy PowerPoint marker"),
            ):
                with self.subTest(suffix=suffix):
                    original = root / f"sample{LEGACY_OFFICE_FORMATS[suffix]}"
                    source.save(str(original))
                    subprocess.run([
                        "soffice", f"-env:UserInstallation={(root / 'profile').as_uri()}", "--headless",
                        "--convert-to", f"{suffix[1:]}:{export_filter}", "--outdir", directory, str(original),
                    ], check=True, capture_output=True, timeout=45)
                    legacy = root / f"sample{suffix}"
                    with patch.dict(os.environ, {"DOCUMENT_PROCESSING_URL": ""}):
                        result = processor.process(legacy.name, legacy.read_bytes(), {})
                    self.assertIn(marker, json.dumps(result["elements"] + result["tables"]))
