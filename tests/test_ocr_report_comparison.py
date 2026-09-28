import unittest

from scripts.compare_ocr_reports import compare_reports


def report(engine, *, dataset_hash="dataset", dpi=180, image_hash="image"):
    return {
        "dataset": "pilot",
        "dataset_sha256": dataset_hash,
        "render_dpi": dpi,
        "environment": {"process_peak_rss_mb": 10},
        "engines": {
            engine: {
                "engine_version": "1.0",
                "runtime_device": "cpu",
                "model_initialization_seconds": 2,
                "aggregate": {"table_rows_expected": 16, "table_rows_exact": 8, "table_row_recall": 0.5},
                "pages": [{
                    "document_id": "DOC", "page": 1, "language": "en",
                    "source_pdf_sha256": "source", "rendered_image_sha256": image_hash,
                    "hypothesis_text": "Revenue Profit 1,200 900",
                    "reference_characters": 10, "reference_words": 2,
                    "character_edit_distance": 1, "word_edit_distance": 1,
                    "cer": 0.1, "wer": 0.5, "latency_seconds": 2,
                }],
            }
        },
    }


class OcrReportComparisonTest(unittest.TestCase):
    def test_reports_compare_scores_and_resources_for_identical_inputs(self):
        result = compare_reports([report("easyocr"), report("paddleocr")])
        self.assertEqual(result["dataset_sha256"], "dataset")
        self.assertEqual(len(result["paired_pages"]), 1)
        self.assertEqual([row["engine"] for row in result["engines"]], ["easyocr", "paddleocr"])
        self.assertEqual(result["engines"][0]["micro_cer"], 0.1)
        self.assertEqual(result["engines"][0]["pages_per_minute"], 30.0)
        self.assertEqual(result["engines"][0]["table_row_recall"], 0.5)

    def test_rejects_different_dataset_or_rendered_page(self):
        with self.assertRaisesRegex(ValueError, "different dataset"):
            compare_reports([report("easyocr"), report("surya", dataset_hash="other")])
        with self.assertRaisesRegex(ValueError, "same source pages"):
            compare_reports([report("easyocr"), report("surya", image_hash="other-image")])

    def test_rejects_duplicate_engine_and_single_report(self):
        with self.assertRaisesRegex(ValueError, "Duplicate OCR engine"):
            compare_reports([report("easyocr"), report("easyocr")])
        with self.assertRaisesRegex(ValueError, "at least two"):
            compare_reports([report("easyocr")])

    def test_dataset_adds_cell_text_recall_without_claiming_layout_association(self):
        dataset = {"pages": [{
            "document_id": "DOC", "page": 1, "language": "en",
            "table_rows": [
                {"label": "Revenue", "values": ["1,200", "900"]},
                {"label": "Profit", "values": ["800", "700"]},
            ],
        }]}
        result = compare_reports([report("easyocr"), report("surya")], dataset)
        engine = result["engines"][0]
        self.assertEqual(engine["table_cells_expected"], 6)
        self.assertEqual(engine["table_cells_text_matched"], 4)
        self.assertAlmostEqual(engine["table_cell_text_recall"], 4 / 6, places=5)
        self.assertIn("ignores row and column", engine["table_cell_metric_scope"])


if __name__ == "__main__":
    unittest.main()
