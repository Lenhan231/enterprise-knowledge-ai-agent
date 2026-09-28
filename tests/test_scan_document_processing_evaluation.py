import fitz
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_scan_document_processing import crop_pdf_page, select_cases


class ScanDocumentProcessingEvaluationTest(unittest.TestCase):
    def test_case_selection_defaults_to_scans_and_allows_explicit_labeled_regions(self):
        pages = [
            {"id": "scan", "physical_scan": True},
            {"id": "poster", "physical_scan": False},
        ]
        self.assertEqual([case["id"] for case in select_cases(pages, [])], ["scan"])
        self.assertEqual([case["id"] for case in select_cases(pages, ["poster"])], ["poster"])
        with self.assertRaisesRegex(ValueError, "Unknown case ID"):
            select_cases(pages, ["missing"])

    def test_crop_preserves_rotated_page_scan_and_maps_view_coordinates(self):
        source = fitz.open()
        page = source.new_page(width=400, height=300)
        page.insert_text((80, 100), "scanned source")
        page.set_rotation(90)
        source_pdf = source.tobytes()
        source.close()

        crop = crop_pdf_page(source_pdf, 1, [50, 50, 250, 350])

        result = fitz.open(stream=crop, filetype="pdf")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].cropbox, fitz.Rect(50, 50, 350, 250))
        self.assertEqual(result[0].rotation, 90)
        result.close()

    def test_crop_rejects_a_region_outside_source_page(self):
        source = fitz.open()
        source.new_page(width=200, height=100)
        source_pdf = source.tobytes()
        source.close()

        with self.assertRaises(ValueError):
            crop_pdf_page(source_pdf, 1, [10, 10, 300, 300])

    def test_crop_serialization_has_a_stable_hash_for_paired_runs(self):
        source = fitz.open()
        source.new_page(width=400, height=300).insert_text((80, 100), "stable crop")
        source_pdf = source.tobytes()
        source.close()

        self.assertEqual(
            crop_pdf_page(source_pdf, 1, [50, 50, 250, 250]),
            crop_pdf_page(source_pdf, 1, [50, 50, 250, 250]),
        )


if __name__ == "__main__":
    unittest.main()
