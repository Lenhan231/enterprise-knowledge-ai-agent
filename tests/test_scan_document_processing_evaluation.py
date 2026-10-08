import hashlib
import json
import fitz
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.processing.evaluate_scan_document_processing import (
    crop_pdf_page,
    evaluate_region,
    rasterize_for_ocr,
    score_text_anchors,
    score_table_anchors,
    select_cases,
    source_text_for_scoring,
)


class ScanDocumentProcessingEvaluationTest(unittest.TestCase):
    def test_shopee_inventory_grid_labels_match_the_registered_source_hash(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads(
            (root / "data/evaluation/ocr/commerce_shopee_inventory_grid_anchors.json").read_text(encoding="utf-8")
        )
        self.assertFalse(dataset["primary_metric_selection_eligible"])
        self.assertEqual(len(dataset["pages"]), 1)
        page = dataset["pages"][0]
        source = (root / page["file"]).read_bytes()

        self.assertEqual(hashlib.sha256(source).hexdigest(), page["source_pdf_sha256"])
        self.assertFalse(page["physical_scan"])
        self.assertEqual(len(page["table_rows"]), 2)
        self.assertTrue(all(len(row["values"]) == 6 for row in page["table_rows"]))

    def test_text_anchor_score_does_not_treat_selected_phrases_as_full_page_cer(self):
        score = score_text_anchors(
            ["Stock is available", "Replenish soon"],
            "Stock is available for now; please replenish soon.",
        )

        self.assertEqual(score["matched_anchor_count"], 2)
        self.assertEqual(score["anchor_recall"], 1.0)
        self.assertIsNone(score_text_anchors(["expected"], None))
        self.assertIsNone(score_text_anchors([], "some OCR text"))

    def test_structured_table_serialization_is_not_counted_as_ocr_errors(self):
        chunks = [
            {"text": "East 120", "metadata": {"parser": "pymupdf"}},
            {"text": "Columns: label | value_1\\nRow 1: East | value_1: 120", "metadata": {
                "parser": "pymupdf.structured_table_chunk", "element_type": "table",
            }},
        ]

        self.assertEqual(source_text_for_scoring(chunks), "East 120")
        chunks[1]["metadata"]["table_chunk_match"] = {"matched_source_chunk": True}
        self.assertIsNone(source_text_for_scoring(chunks))

    def test_commerce_scan_upload_path_scores_ocr_text_and_structured_table_separately(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads(
            (root / "data/evaluation/ocr/commerce_scan_ground_truth.json").read_text(encoding="utf-8")
        )
        spec = next(page for page in dataset["pages"] if page.get("table_rows"))

        result = evaluate_region(spec, (root / spec["file"]).read_bytes())

        self.assertEqual(result["cer"], 0.0)
        self.assertEqual(result["wer"], 0.0)
        self.assertEqual(result["table_anchor_score"]["anchor_row_recall"], 1.0)
        self.assertEqual(result["table_anchor_score"]["exact_numeric_cell_accuracy"], 1.0)
        self.assertIn("generated table serialization excluded", result["text_score_scope"])

    def test_degraded_image_only_scan_is_not_rasterized_a_second_time(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads(
            (root / "data/evaluation/ocr/commerce_degraded_scan_ground_truth.json").read_text(encoding="utf-8")
        )
        spec = next(page for page in dataset["pages"] if page.get("table_rows"))

        result = evaluate_region(spec, (root / spec["file"]).read_bytes())

        self.assertLessEqual(result["cer"], 0.01)
        self.assertLessEqual(result["wer"], 0.05)
        self.assertEqual(result["table_anchor_score"]["anchor_row_recall"], 1.0)
        self.assertEqual(result["table_anchor_score"]["exact_numeric_cell_accuracy"], 1.0)

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

    def test_table_score_rejects_numeric_values_contaminated_by_action_text(self):
        score = score_table_anchors(
            ["Sales", "Available", "Minimum"],
            [{"label": "Product A", "values": ["10", "0", "0"]}],
            [{
                "columns": ["Product", "Sales", "Available", "Minimum"],
                "rows": [{"Product": "Product A", "Sales": "10", "Available": "0", "Minimum": "Edit 0"}],
            }],
        )

        self.assertEqual(score["exact_numeric_cells"], 2)
        self.assertEqual(score["row_matches"][0]["exact_value_matches"], [True, True, False])
        self.assertFalse(score["table_anchor_quality_pass"])

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

    def test_table_score_supports_semantic_text_column_headers(self):
        expected_headers = [
            "Region", "Delivered sample orders", "Median transit days", "Avg fee units",
        ]
        expected_rows = [
            {"label": "East", "values": ["120", "3.0", "42.50"]},
            {"label": "Central", "values": ["95", "4.0", "48.75"]},
            {"label": "West", "values": ["80", "5.0", "55.25"]},
        ]
        table = {
            "columns": expected_headers,
            "rows": [
                {"Region": "East", "Delivered sample orders": "120", "Median transit days": "3.0", "Avg fee units": "42.50"},
                {"Region": "Central", "Delivered sample orders": "95", "Median transit days": "4.0", "Avg fee units": "48.75"},
                {"Region": "West", "Delivered sample orders": "80", "Median transit days": "5.0", "Avg fee units": "55.25"},
            ],
        }

        score = score_table_anchors(expected_headers, expected_rows, [table])

        self.assertEqual(score["exact_header_matches"], 3)
        self.assertEqual(score["matched_anchor_rows"], 3)
        self.assertEqual(score["exact_numeric_cells"], 9)


if __name__ == "__main__":
    unittest.main()
