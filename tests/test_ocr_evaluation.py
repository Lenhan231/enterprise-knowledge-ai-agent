import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock

import fitz

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluate_ocr.py"
SPEC = importlib.util.spec_from_file_location("evaluate_ocr", SCRIPT)
evaluate_ocr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate_ocr)


class OCREvaluationTest(unittest.TestCase):
    def test_normalization_ignores_case_and_punctuation(self):
        self.assertEqual(evaluate_ocr.normalize("Doanh thu, NĂM 2024!"), "doanh thu năm 2024")

    def test_character_and_word_error_rates(self):
        self.assertEqual(evaluate_ocr.error_rate("abc", "abc"), 0)
        self.assertAlmostEqual(evaluate_ocr.error_rate("abc", "adc"), 1 / 3)
        self.assertEqual(evaluate_ocr.error_rate("", ""), 0)

    def test_aggregate_reports_macro_and_reference_length_weighted_scores(self):
        summary = evaluate_ocr.summarize_pages([
            {"cer": 0.5, "wer": 0.5, "character_edit_distance": 5, "word_edit_distance": 1,
             "reference_characters": 10, "reference_words": 2, "latency_seconds": 1},
            {"cer": 0.1, "wer": 0.2, "character_edit_distance": 9, "word_edit_distance": 2,
             "reference_characters": 90, "reference_words": 10, "latency_seconds": 3},
            {"cer": None, "wer": None, "character_edit_distance": None, "word_edit_distance": None,
             "reference_characters": 20, "reference_words": 4, "latency_seconds": 0.1},
        ])
        self.assertEqual(summary["valid_pages"], 2)
        self.assertEqual(summary["macro_mean_page_cer"], 0.3)
        self.assertEqual(summary["micro_cer"], 0.14)
        self.assertEqual(summary["micro_wer"], 0.25)

    def test_paddle_v2_output_is_adapted(self):
        class PaddleV2:
            def ocr(self, image_path, cls=False):
                return [[[None, ("Vietnamese report", 0.99)]]]

        with patch.object(evaluate_ocr, "time") as clock:
            clock.perf_counter.side_effect = [1.0, 1.1]
            text, elapsed, error = evaluate_ocr.run_engine("paddleocr", PaddleV2(), Path("page.png"), "vie+eng")
        self.assertEqual(text, "Vietnamese report")
        self.assertAlmostEqual(elapsed, 0.1)
        self.assertIsNone(error)

    def test_paddle_v3_output_is_adapted(self):
        class Page:
            json = {"res": {"rec_texts": ["Annual report", "Revenue"]}}

        class PaddleV3:
            def predict(self, image_path):
                return [Page()]

        text, _, error = evaluate_ocr.run_engine("paddleocr", PaddleV3(), Path("page.png"), "vie+eng")
        self.assertEqual(text, "Annual report\nRevenue")
        self.assertIsNone(error)

    def test_engine_version_uses_installed_package_metadata(self):
        with patch.object(evaluate_ocr.importlib.metadata, "version", return_value="3.0.1") as version:
            self.assertEqual(evaluate_ocr.engine_version("paddleocr"), "3.0.1")
        version.assert_called_once_with("paddleocr")

    def test_engine_version_returns_none_when_package_metadata_is_missing(self):
        error = evaluate_ocr.importlib.metadata.PackageNotFoundError("surya-ocr")
        with patch.object(evaluate_ocr.importlib.metadata, "version", side_effect=error):
            self.assertIsNone(evaluate_ocr.engine_version("surya"))

    def test_model_initialization_failure_keeps_explicitly_unscored_engine(self):
        torch = MagicMock()
        torch.cuda.is_available.return_value = False
        dataset_path = Path(__file__).resolve().parents[1] / "data/evaluation/vinamilk_ocr_ground_truth_v2.json"
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        pdf_path = Path(dataset["pages"][0]["file"])
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open()
        for _ in range(dataset["pages"][0]["page"]):
            document.new_page()
        document[dataset["pages"][0]["page"] - 1].insert_text((72, 72), "fixture page")
        pdf_path.write_bytes(document.tobytes())
        document.close()
        try:
            with (
                patch.object(evaluate_ocr, "create_engine", side_effect=RuntimeError("model load failed")),
                patch.object(evaluate_ocr.importlib.util, "find_spec", return_value=object()),
                patch.dict(sys.modules, {"torch": torch}),
                patch.object(sys, "argv", [
                    str(SCRIPT), "--dataset", str(dataset_path),
                    "--engines", "paddleocr", "--max-pages", "1", "--output", "/tmp/ocr-evaluator-test.json",
                ]),
                patch.object(evaluate_ocr.Path, "mkdir"),
                patch.object(evaluate_ocr.Path, "write_text") as write_text,
            ):
                with patch.object(evaluate_ocr, "time") as clock:
                    clock.perf_counter.side_effect = [10.0, 10.2]
                    status = evaluate_ocr.main()
                self.assertEqual(status, 1)
                report = json.loads(write_text.call_args.args[0])
            engine = report["engines"]["paddleocr"]
            self.assertFalse(engine["available"])
            self.assertIn("model load failed", engine["model_initialization_error"])
            self.assertEqual(engine["aggregate"]["valid_pages"], 0)
            self.assertFalse(report["environment"]["cuda_available"])
        finally:
            pdf_path.unlink(missing_ok=True)

    def test_selected_page_language_uses_visible_page_not_document_suffix(self):
        dataset_path = Path(__file__).resolve().parents[1] / "data/evaluation/ocr_pages.json"
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        languages = {page["document_id"]: page["language"] for page in dataset["pages"]}
        self.assertEqual(languages["VNM-AR-2020-VI"], "en")
        self.assertEqual(languages["VNM-AR-2021-VI"], "en")
        self.assertEqual(languages["VNM-AR-2022-VI"], "vi")
        self.assertEqual(languages["VNM-AR-2023-EN"], "en")
        self.assertEqual(languages["VNM-AR-2024-VI"], "vi")
        self.assertIn("checked visually", dataset["language_label_method"])

    def test_human_reviewed_ocr_regions_have_manual_references_and_same_crop_protocol(self):
        dataset_path = Path(__file__).resolve().parents[1] / "data/evaluation/vinamilk_ocr_ground_truth.json"
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        self.assertTrue(dataset["primary_metric_selection_eligible"])
        self.assertEqual(dataset["reference_quality"], "human_transcribed_visual_review")
        self.assertEqual(len(dataset["pages"]), 2)
        for case in dataset["pages"]:
            self.assertEqual(len(case["clip_rect"]), 4)
            self.assertTrue(case["reference_text"].strip())
            self.assertIn(case["language"], {"vi", "en"})

    def test_v2_human_review_dataset_includes_raster_embedded_report_art(self):
        dataset_path = Path(__file__).resolve().parents[1] / "data/evaluation/vinamilk_ocr_ground_truth_v2.json"
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        self.assertEqual(dataset["reference_quality"], "human_transcribed_visual_review")
        self.assertFalse(dataset["primary_metric_selection_eligible"])
        poster = next(page for page in dataset["pages"] if page["id"] == "annual-2020-product-poster-vi")
        self.assertEqual(poster["document_id"], "VNM-AR-2020-VI")
        self.assertEqual(poster["page"], 22)
        self.assertIn("TĂNG CƯỜNG ĐỀ KHÁNG", poster["reference_text"])
        self.assertIn("not a physical scan", dataset["limitations"])


if __name__ == "__main__":
    unittest.main()
