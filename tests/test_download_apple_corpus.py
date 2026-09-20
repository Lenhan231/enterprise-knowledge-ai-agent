from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from download_apple_corpus import (
    DEFAULT_IDS,
    DEFAULT_MANIFEST,
    RESOLVED_URLS,
    google_sheets_export_url,
    read_manifest,
    safe_filename,
)
from scripts.source_downloaders.registry import get_downloader
from scripts.source_downloaders.html import HTMLDownloader
from scripts.source_downloaders.image import ImageDownloader
from scripts.source_downloaders.pdf import PDFDownloader


MANIFEST = (
    REPO_ROOT / "data/manifests/apple/FA26AI69_Apple_Corpus_Manifest_v1.xlsx"
)


class DownloadAppleCorpusTest(unittest.TestCase):
    def test_project_google_sheet_is_loaded_from_environment(self):
        self.assertIn("10IYB7P7G7LK_AX15Jhlq0LZwMla--x1PH8UtLRWAd28", DEFAULT_MANIFEST)

    def test_known_landing_pages_have_direct_pdf_urls(self):
        expected = {
            "APL-ENV-001",
            "APL-ENV-004",
            "APL-ENV-005",
            "APL-SUP-002",
            "APL-SUP-003",
        }

        self.assertLessEqual(expected, RESOLVED_URLS.keys())
        for document_id in expected:
            self.assertTrue(RESOLVED_URLS[document_id].endswith(".pdf"))

    def test_vertical_slice_is_present_in_manifest(self):
        if not MANIFEST.exists():
            self.skipTest("optional local manifest snapshot is not present")
        documents = {row["document_id"]: row for row in read_manifest(MANIFEST)}

        self.assertLessEqual(set(DEFAULT_IDS), documents.keys())
        self.assertEqual(documents["APL-PRC-001"]["domain"], "Procurement")
        self.assertEqual(documents["APL-SUP-001"]["domain"], "Supply Chain")

    def test_safe_filename_is_stable(self):
        filename = safe_filename(
            {"document_id": "APL-CMP-003", "title": "Anti-Corruption Policy"}
        )

        self.assertEqual(filename, "apl-cmp-003_anti_corruption_policy.pdf")

    def test_html_manifest_entry_uses_html_extension(self):
        filename = safe_filename(
            {
                "document_id": "APL-CMP-006",
                "title": "General Terms and Conditions",
                "format": "HTML",
                "official_url": "https://www.apple.com/legal/gtc.html",
            }
        )

        self.assertEqual(filename, "apl-cmp-006_general_terms_and_conditions.html")

    def test_landing_page_in_multi_format_entry_uses_html_extension(self):
        filename = safe_filename(
            {
                "document_id": "APL-FIN-001",
                "title": "Form 10-K",
                "format": "PDF/HTML/XLSX/XBRL",
                "official_url": "https://example.com/filing/default.aspx",
            }
        )

        self.assertEqual(filename, "apl-fin-001_form_10_k.html")

    def test_downloader_registry_separates_source_types(self):
        self.assertIsInstance(get_downloader({"format": "PDF"}), PDFDownloader)
        self.assertIsInstance(get_downloader({"format": "HTML"}), HTMLDownloader)
        image = get_downloader(
            {"format": "PNG", "official_url": "https://example.com/chart.png"}
        )
        self.assertIsInstance(image, ImageDownloader)
        self.assertEqual(image.extension, ".png")

    def test_image_filename_uses_image_format(self):
        filename = safe_filename(
            {
                "document_id": "APL-IMG-001",
                "title": "Supplier Map",
                "format": "WEBP",
                "official_url": "https://example.com/map",
            }
        )

        self.assertEqual(filename, "apl-img-001_supplier_map.webp")

    def test_google_sheet_url_is_converted_to_xlsx_export(self):
        url = (
            "https://docs.google.com/spreadsheets/d/abc_123-XYZ/"
            "edit?usp=sharing#gid=987654"
        )

        self.assertEqual(
            google_sheets_export_url(url),
            "https://docs.google.com/spreadsheets/d/abc_123-XYZ/"
            "export?format=xlsx&gid=987654",
        )

    def test_non_google_sheet_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Not a Google Sheets URL"):
            google_sheets_export_url("https://example.com/manifest.xlsx")


if __name__ == "__main__":
    unittest.main()
