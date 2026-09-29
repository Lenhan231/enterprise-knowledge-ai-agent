import fitz
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_scan_document_processing import crop_pdf_page, rasterize_for_ocr, score_table_anchors, select_cases


class ScanDocumentProcessingEvaluationTest(unittest.TestCase):
    def test_case_selection_defaults_to_scans_and_allows_explicit_labeled_regions(self):
        pages = [
            {"id": "scan", "physical_scan": True},
            {"id": "poster", "physical_scan": False},
        ]
        self.assertEqual([case["id"] for case in select_cases(pages, [])], ["scan"])
        self.assertEqual([case["id"] for case in select_cases(pages, [], all_pages=True)], ["scan", "poster"])
        self.assertEqual([case["id"] for case in select_cases(pages, ["poster"])], ["poster"])
        with self.assertRaisesRegex(ValueError, "Unknown case ID"):
            select_cases(pages, ["missing"])
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            select_cases(pages, ["scan"], all_pages=True)

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

    def test_ocr_rasterization_removes_embedded_text_layer(self):
        source = fitz.open()
        page = source.new_page(width=200, height=100)
        page.insert_text((30, 50), "hidden OCR layer")
        source_pdf = source.tobytes()
        source.close()

        raster = fitz.open(stream=rasterize_for_ocr(source_pdf), filetype="pdf")
        self.assertEqual(raster[0].get_text().strip(), "")
        self.assertTrue(raster[0].get_images())
        raster.close()

    def test_financial_table_score_checks_periods_labels_values_and_signs(self):
        score = score_table_anchors(
            ["31/12/2024", "31/12/2023"],
            [{"label": "Lợi nhuận sau thuế", "values": ["(1.000)", "900"]}],
            [{
                "columns": ["label", "31/12/2024", "31/12/2023"],
                "rows": [{
                    "label": "Loi nhuan sau thue",
                    "31/12/2024": "(1,000)",
                    "31/12/2023": "900",
                }],
            }],
        )

        self.assertEqual(score["exact_header_matches"], 2)
        self.assertEqual(score["matched_anchor_rows"], 1)
        self.assertEqual(score["exact_numeric_cells"], 2)

    def test_missing_detected_table_scores_expected_rows_and_cells_as_misses(self):
        score = score_table_anchors(
            ["2011", "2010"],
            [{"label": "Revenue", "values": ["100", "90"]}],
            [],
        )

        self.assertEqual(score["expected_anchor_rows"], 1)
        self.assertEqual(score["matched_anchor_rows"], 0)
        self.assertEqual(score["anchor_row_recall"], 0.0)
        self.assertEqual(score["exact_numeric_cells"], 0)
        self.assertEqual(score["total_numeric_cells"], 2)

    def test_financial_table_score_does_not_hide_digit_or_sign_errors(self):
        score = score_table_anchors(
            ["31/12/2024", "31/12/2023"],
            [{"label": "Net profit", "values": ["(1,000)", "900"]}],
            [{
                "columns": ["label", "31/12/2024", "31/12/2023"],
                "rows": [{"label": "Net profit", "31/12/2024": "1.000", "31/12/2023": "901"}],
            }],
        )

        self.assertEqual(score["exact_numeric_cells"], 0)
        self.assertEqual(score["row_matches"][0]["exact_value_matches"], [False, False])

    def test_financial_table_score_checks_cell_location_and_column_assignment(self):
        expected = [{
            "label": "Revenue",
            "values": ["100", "90"],
            "cell_bboxes_pdf_points": {
                "value_1": [110, 40, 140, 48],
                "value_2": [210, 40, 240, 48],
            },
        }]
        table = {
            "columns": ["label", "value_1", "value_2"],
            "rows": [{"label": "Revenue", "value_1": "100", "value_2": "90"}],
            "metadata": {"row_cell_bboxes": [{
                "value_1": [110, 40, 140, 48],
                "value_2": [210, 40, 240, 48],
            }]},
        }

        correct = score_table_anchors(["1", "2"], expected, [table])
        table["metadata"]["row_cell_bboxes"][0]["value_1"], table["metadata"]["row_cell_bboxes"][0]["value_2"] = (
            table["metadata"]["row_cell_bboxes"][0]["value_2"],
            table["metadata"]["row_cell_bboxes"][0]["value_1"],
        )
        swapped = score_table_anchors(["1", "2"], expected, [table])

        self.assertEqual(correct["cell_location_recall"], 1.0)
        self.assertEqual(swapped["cell_location_recall"], 0.0)

    def test_financial_table_score_maps_year_bbox_keys_to_period_headers(self):
        expected = [{
            "label": "Revenue",
            "values": ["100", "90"],
            "cell_bboxes_pdf_points": {
                "2011": [110, 40, 140, 48],
                "2010": [210, 40, 240, 48],
            },
        }]
        table = {
            "columns": ["label", "31/12/2011", "31/12/2010"],
            "rows": [{"label": "Revenue", "31/12/2011": "100", "31/12/2010": "90"}],
            "metadata": {"row_cell_bboxes": [{
                "31/12/2011": [110, 40, 140, 48],
                "31/12/2010": [210, 40, 240, 48],
            }]},
        }

        correct = score_table_anchors(["31/12/2011", "31/12/2010"], expected, [table])
        table["metadata"]["row_cell_bboxes"][0]["31/12/2011"], table["metadata"]["row_cell_bboxes"][0]["31/12/2010"] = (
            table["metadata"]["row_cell_bboxes"][0]["31/12/2010"],
            table["metadata"]["row_cell_bboxes"][0]["31/12/2011"],
        )
        swapped = score_table_anchors(["31/12/2011", "31/12/2010"], expected, [table])

        self.assertEqual(correct["cell_location_recall"], 1.0)
        self.assertEqual(swapped["cell_location_recall"], 0.0)


if __name__ == "__main__":
    unittest.main()
