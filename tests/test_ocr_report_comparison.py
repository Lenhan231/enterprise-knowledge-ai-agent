import unittest

from scripts.processing.compare_ocr_reports import compare_reports


def report(engine, *, dataset_hash="dataset", dpi=180, image_hash="image"):
    return {
        "dataset": "pilot",
        "dataset_sha256": dataset_hash,
        "render_dpi": dpi,
        "ocr_configuration": {"tesseract_page_segmentation_mode": 3} if engine == "tesseract" else {},
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
        self.assertEqual(result["engines"][0]["by_language"]["en"]["micro_cer"], 0.1)

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

    def test_tesseract_segmentation_modes_are_distinct_comparison_arms(self):
        psm3 = report("tesseract")
        psm11 = report("tesseract")
        psm11["ocr_configuration"]["tesseract_page_segmentation_mode"] = 11

        result = compare_reports([psm3, psm11])

        self.assertEqual([item["engine"] for item in result["engines"]], ["tesseract_psm3", "tesseract_psm11"])
        self.assertEqual([item["base_engine"] for item in result["engines"]], ["tesseract", "tesseract"])

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

    def test_dataset_row_scoring_accepts_interleaved_financial_table_columns(self):
        item = report("easyocr")
        page = item["engines"]["easyocr"]["pages"][0]
        page["hypothesis_text"] = "Revenue 01 VII.1 1,200 900"
        dataset = {"pages": [{
            "document_id": "DOC", "page": 1, "language": "en",
            "table_rows": [{"label": "Revenue", "values": ["1,200", "900"]}],
        }]}

        result = compare_reports([item, report("surya")], dataset)

        self.assertEqual(result["engines"][0]["table_rows_exact_from_dataset"], 1)

    def test_rescores_cached_outputs_against_updated_reference_for_same_render(self):
        item = report("easyocr")
        dataset = {"dataset_id": "pilot-v2-label-refresh", "pages": [{
            "document_id": "DOC", "page": 1, "language": "en",
            "source_pdf_sha256": "source", "rendered_image_sha256": "image",
            "reference_text": "Revenue Profit 1,200 900",
            "table_rows": [],
        }]}

        result = compare_reports(
            [item, report("surya")], dataset,
            rescore_references=True, dataset_sha256="updated-label-hash",
        )

        self.assertTrue(result["reference_rescored"])
        self.assertEqual(result["dataset"], "pilot-v2-label-refresh")
        self.assertEqual(result["dataset_sha256"], "updated-label-hash")
        self.assertEqual(result["source_ocr_dataset_sha256"], "dataset")
        self.assertEqual(result["engines"][0]["valid_pages"], 1)
        self.assertEqual(result["engines"][0]["micro_cer"], 0.0)
        self.assertEqual(result["engines"][0]["micro_wer"], 0.0)

    def test_rescoring_rejects_reference_for_different_render(self):
        dataset = {"pages": [{
            "document_id": "DOC", "page": 1, "language": "en",
            "source_pdf_sha256": "source", "rendered_image_sha256": "different-image",
            "reference_text": "Revenue",
        }]}
        with self.assertRaisesRegex(ValueError, "same source/rendered page"):
            compare_reports(
                [report("easyocr"), report("surya")], dataset,
                rescore_references=True, dataset_sha256="updated-label-hash",
            )

    def test_anchor_only_scan_pages_count_as_processed_and_contribute_table_metrics(self):
        reports = [report("tesseract"), report("easyocr")]
        for item in reports:
            pages = item["engines"][next(iter(item["engines"]))]["pages"]
            pages.append({
                "document_id": "DOC", "page": 2, "language": "vi",
                "source_pdf_sha256": "source-2", "rendered_image_sha256": "image-2",
                "hypothesis_text": "Assets 100", "reference_characters": 0,
                "reference_words": 0, "character_edit_distance": None,
                "word_edit_distance": None, "cer": None, "wer": None,
                "latency_seconds": 1.0, "error": None,
            })
        dataset = {"pages": [
            {"document_id": "DOC", "page": 1, "language": "en", "table_rows": []},
            {"document_id": "DOC", "page": 2, "language": "vi", "table_rows": [
                {"label": "Assets", "values": ["100", "90"]},
            ]},
        ]}

        result = compare_reports(reports, dataset)

        self.assertEqual(result["engines"][0]["valid_pages"], 1)
        self.assertEqual(result["engines"][0]["ocr_pages"], 2)
        self.assertEqual(result["engines"][0]["failed_pages"], 0)
        self.assertEqual(result["engines"][0]["table_cells_expected"], 3)
        self.assertEqual(result["engines"][0]["table_cells_text_matched"], 2)
        vietnamese = result["engines"][0]["by_language"]["vi"]
        self.assertEqual(vietnamese["table_rows_expected"], 1)
        self.assertEqual(vietnamese["table_cells_text_matched"], 2)


if __name__ == "__main__":
    unittest.main()
