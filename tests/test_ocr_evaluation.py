import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

import fitz

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluate_ocr.py"
SPEC = importlib.util.spec_from_file_location("evaluate_ocr", SCRIPT)
evaluate_ocr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate_ocr)


class OCREvaluationTest(unittest.TestCase):
    def require_source_pdf(self, root, relative_path):
        if not (root / relative_path).is_file():
            self.skipTest("requires the optional downloaded Vinamilk source PDF corpus")

    def test_paddleocr_3_selects_cuda_when_available(self):
        torch = MagicMock()
        torch.cuda.is_available.return_value = True
        paddle = MagicMock()
        paddle.is_compiled_with_cuda.return_value = True
        paddleocr = MagicMock()
        with (
            patch.dict(sys.modules, {"torch": torch, "paddle": paddle, "paddleocr": paddleocr}),
        ):
            evaluate_ocr.create_engine("paddleocr", "vi")
        paddleocr.PaddleOCR.assert_called_once_with(
            lang="vi", use_doc_orientation_classify=False,
            use_doc_unwarping=False, use_textline_orientation=False,
            device="gpu:0", cpu_threads=2, enable_mkldnn=False,
        )

    def test_paddleocr_uses_cpu_when_wheel_has_no_cuda_support(self):
        torch = MagicMock()
        torch.cuda.is_available.return_value = True
        paddle = MagicMock()
        paddle.is_compiled_with_cuda.return_value = False
        paddleocr = MagicMock()
        with patch.dict(sys.modules, {"torch": torch, "paddle": paddle, "paddleocr": paddleocr}):
            evaluate_ocr.create_engine("paddleocr", "vi")
        self.assertEqual(paddleocr.PaddleOCR.call_args.kwargs["device"], "cpu")

    def test_environment_gpu_reports_device_when_cuda_is_available(self):
        torch = MagicMock()
        torch.cuda.is_available.return_value = True
        torch.cuda.get_device_name.return_value = "Kaggle T4"
        with patch.dict(sys.modules, {"torch": torch}):
            self.assertEqual(evaluate_ocr.environment_gpu(), (True, "Kaggle T4"))

    def test_surya_0171_uses_foundation_recognition_and_detection_predictors(self):
        surya = ModuleType("surya")
        surya.__path__ = []
        foundation = ModuleType("surya.foundation")
        detection = ModuleType("surya.detection")
        recognition = ModuleType("surya.recognition")
        foundation_predictor = object()
        detection_predictor = object()
        foundation.FoundationPredictor = MagicMock(return_value=foundation_predictor)
        detection.DetectionPredictor = MagicMock(return_value=detection_predictor)
        recognition.RecognitionPredictor = MagicMock(return_value="recognizer")
        with patch.dict(sys.modules, {
            "surya": surya,
            "surya.foundation": foundation,
            "surya.detection": detection,
            "surya.recognition": recognition,
        }):
            self.assertEqual(evaluate_ocr.create_engine("surya", "en"), ("recognizer", detection_predictor))
        foundation.FoundationPredictor.assert_called_once_with()
        recognition.RecognitionPredictor.assert_called_once_with(foundation_predictor)

    def test_surya_passes_detection_predictor_to_v0171_api(self):
        page = SimpleNamespace(text_lines=[SimpleNamespace(text="Vietnamese report")])
        recognizer = MagicMock(return_value=[page])
        detection_predictor = object()
        image_lib = MagicMock()
        image_lib.open.return_value.convert.return_value = object()
        with patch.dict(sys.modules, {"PIL": MagicMock(Image=image_lib)}):
            text, _, error = evaluate_ocr.run_engine(
                "surya", (recognizer, detection_predictor), Path("page.png"), "vi"
            )
        self.assertEqual(text, "Vietnamese report")
        self.assertIsNone(error)
        recognizer.assert_called_once_with(
            [image_lib.open.return_value.convert.return_value],
            det_predictor=detection_predictor,
        )

    def test_normalization_ignores_case_and_punctuation(self):
        self.assertEqual(evaluate_ocr.normalize("Doanh thu, NĂM 2024!"), "doanh thu năm 2024")

    def test_character_and_word_error_rates(self):
        self.assertEqual(evaluate_ocr.error_rate("abc", "abc"), 0)
        self.assertAlmostEqual(evaluate_ocr.error_rate("abc", "adc"), 1 / 3)
        self.assertEqual(evaluate_ocr.error_rate("", ""), 0)

    def test_tesseract_page_segmentation_mode_is_configurable(self):
        with patch.object(evaluate_ocr.subprocess, "run", return_value=SimpleNamespace(stdout="Revenue")) as run:
            text, _, error = evaluate_ocr.run_engine(
                "tesseract", None, Path("page.png"), "vie+eng", tesseract_psm=11,
            )
        self.assertEqual(text, "Revenue")
        self.assertIsNone(error)
        self.assertEqual(run.call_args.args[0][-2:], ["--psm", "11"])

    def test_table_row_recall_requires_label_and_both_period_values(self):
        rows = [
            {"label": "Tiền và các khoản tương đương tiền", "values": ["2.225.944", "2.912.027"]},
            {"label": "Hàng tồn kho", "values": ["5.634.710", "6.082.233"]},
        ]
        hypothesis = "Tiền và các khoản tương đương tiền 2.225.944 2.912.027\nHàng tồn kho 5.634.710"

        self.assertEqual(evaluate_ocr.exact_table_rows(rows, hypothesis), 1)
        self.assertEqual(evaluate_ocr.matched_table_row_indices(rows, hypothesis), [0])

    def test_table_cell_text_recall_ignores_association_but_respects_duplicates(self):
        rows = [
            {"label": "Revenue", "values": ["1,200", "900"]},
            {"label": "Profit", "values": ["900", "300"]},
        ]
        matched, expected = evaluate_ocr.table_cell_text_counts(
            rows, "Revenue Profit 1.200 900 300"
        )
        self.assertEqual((matched, expected), (5, 6))

    def test_ocr_summary_reports_exact_table_row_recall(self):
        summary = evaluate_ocr.summarize_pages([{
            "cer": 0.1, "wer": 0.2, "character_edit_distance": 1, "word_edit_distance": 1,
            "reference_characters": 10, "reference_words": 5, "latency_seconds": 1,
            "table_rows_expected": 4, "table_rows_exact": 3,
        }])

        self.assertEqual(summary["table_rows_expected"], 4)
        self.assertEqual(summary["table_rows_exact"], 3)
        self.assertEqual(summary["table_row_recall"], 0.75)

    def test_ocr_summary_reports_cell_text_recall_separately(self):
        summary = evaluate_ocr.summarize_pages([{
            "cer": 0.1, "wer": 0.2, "character_edit_distance": 1, "word_edit_distance": 1,
            "reference_characters": 10, "reference_words": 5, "latency_seconds": 1,
            "table_cells_expected": 6, "table_cells_text_matched": 5,
        }])
        self.assertAlmostEqual(summary["table_cell_text_recall"], 5 / 6, places=5)

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
        self.assertEqual(summary["pages_per_minute"], 30.0)

    def test_peak_memory_reports_process_and_child_scopes(self):
        memory = evaluate_ocr.peak_memory_mb()
        self.assertIn("process_peak_rss_mb", memory)
        self.assertIn("child_peak_rss_mb", memory)
        self.assertGreater(memory["process_peak_rss_mb"], 0)

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
        source_dataset = Path(__file__).resolve().parents[1] / "data/evaluation/vinamilk_ocr_ground_truth_v2.json"
        dataset = json.loads(source_dataset.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            pdf_path = temp_root / "fixture.pdf"
            dataset["pages"] = [dataset["pages"][0] | {"file": "fixture.pdf"}]
            dataset_path = temp_root / "dataset.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            document = fitz.open()
            for _ in range(dataset["pages"][0]["page"]):
                document.new_page()
            document[dataset["pages"][0]["page"] - 1].insert_text((72, 72), "fixture page")
            pdf_path.write_bytes(document.tobytes())
            document.close()
            with (
                patch.object(evaluate_ocr, "REPO_ROOT", temp_root),
                patch.object(evaluate_ocr, "create_engine", side_effect=RuntimeError("model load failed")),
                patch.object(evaluate_ocr.importlib.util, "find_spec", return_value=object()),
                patch.dict(sys.modules, {"torch": torch}),
                patch.object(sys, "argv", [
                    str(SCRIPT), "--dataset", str(dataset_path),
                    "--engines", "paddleocr", "--max-pages", "1", "--output", str(temp_root / "report.json"),
                ]),
            ):
                with patch.object(evaluate_ocr, "time") as clock:
                    clock.perf_counter.side_effect = [10.0, 10.2]
                    status = evaluate_ocr.main()
                self.assertEqual(status, 1)
            report = json.loads((temp_root / "report.json").read_text(encoding="utf-8"))
            engine = report["engines"]["paddleocr"]
            self.assertFalse(engine["available"])
            self.assertIn("model load failed", engine["model_initialization_error"])
            self.assertEqual(engine["aggregate"]["valid_pages"], 0)
            self.assertFalse(report["environment"]["cuda_available"])

    def test_neural_engines_are_initialized_and_run_sequentially(self):
        events = []
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            pdf = fitz.open()
            pdf.new_page().insert_text((72, 72), "fixture")
            (temp_root / "fixture.pdf").write_bytes(pdf.tobytes())
            pdf.close()
            dataset = {
                "dataset_id": "fixture",
                "reference_method": "test fixture",
                "limitations": "test only",
                "pages": [{
                    "document_id": "fixture", "file": "fixture.pdf", "page": 1,
                    "language": "vi", "reference_text": "fixture text",
                }],
            }
            dataset_path = temp_root / "dataset.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            output_path = temp_root / "report.json"

            def create_engine(engine, _language):
                events.append(("init", engine))
                return object()

            def run_engine(engine, _model, _image, _language):
                events.append(("run", engine))
                return "fixture text", 0.1, None

            torch = MagicMock()
            torch.cuda.is_available.return_value = False
            paddle = MagicMock()
            paddle.device.get_device.return_value = "cpu"
            with (
                patch.object(evaluate_ocr, "REPO_ROOT", temp_root),
                patch.object(evaluate_ocr.importlib.util, "find_spec", return_value=object()),
                patch.dict(sys.modules, {"torch": torch, "paddle": paddle}),
                patch.object(evaluate_ocr, "engine_version", return_value="test"),
                patch.object(evaluate_ocr, "create_engine", side_effect=create_engine),
                patch.object(evaluate_ocr, "run_engine", side_effect=run_engine),
                patch.object(sys, "argv", [
                    str(SCRIPT), "--dataset", str(dataset_path), "--engines", "paddleocr", "easyocr",
                    "--output", str(output_path),
                ]),
            ):
                self.assertEqual(evaluate_ocr.main(), 0)

            self.assertEqual(events, [
                ("init", "paddleocr"), ("run", "paddleocr"),
                ("init", "easyocr"), ("run", "easyocr"),
            ])
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["engines"]["paddleocr"]["aggregate"]["valid_pages"], 1)
            self.assertEqual(report["engines"]["easyocr"]["aggregate"]["valid_pages"], 1)
            self.assertEqual(report["engines"]["paddleocr"]["pages"][0]["hypothesis_text"], "fixture text")

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

    def test_v3_adds_manually_reviewed_physical_scan_region(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "data/evaluation/vinamilk_ocr_ground_truth_v3.json").read_text(encoding="utf-8"))
        scan = next(page for page in dataset["pages"] if page.get("physical_scan"))
        self.assertFalse(dataset["primary_metric_selection_eligible"])
        self.assertEqual((scan["document_id"], scan["page"], scan["language"]), ("VNM-CHARTER-2026-EN", 4, "en"))
        self.require_source_pdf(root, scan["file"])
        with fitz.open(root / scan["file"]) as pdf:
            page = pdf[scan["page"] - 1]
            self.assertEqual(page.get_text().strip(), "")
            self.assertTrue(page.get_images(full=True))
        self.assertIn("INTRODUCTION", scan["reference_text"])

    def test_v4_has_two_image_only_scans_with_manual_text_labels(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "data/evaluation/vinamilk_ocr_ground_truth_v4.json").read_text(encoding="utf-8"))
        scans = [page for page in dataset["pages"] if page.get("physical_scan")]
        self.assertEqual({page["document_id"] for page in scans}, {"VNM-CHARTER-2026-EN", "VNM-CGRULES-2026-EN"})
        self.assertTrue(all(page["reference_text"].strip() and len(page["clip_rect"]) == 4 for page in scans))
        for scan in scans:
            self.require_source_pdf(root, scan["file"])
            with fitz.open(root / scan["file"]) as pdf:
                page = pdf[scan["page"] - 1]
                self.assertEqual(page.get_text().strip(), "")
                self.assertTrue(page.get_images(full=True))

    def test_v5_contains_visually_reviewed_vietnamese_table_rows(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "data/evaluation/vinamilk_ocr_ground_truth_v5.json").read_text(encoding="utf-8"))
        table = next(page for page in dataset["pages"] if page.get("layout_type") == "financial_table")
        self.assertFalse(table.get("physical_scan", False))
        self.assertEqual(len(table["table_rows"]), 16)
        self.require_source_pdf(root, table["file"])
        with fitz.open(root / table["file"]) as pdf:
            page = pdf[table["page"] - 1]
            native_text = page.get_text("text", clip=fitz.Rect(table["clip_rect"]))
        self.assertEqual(evaluate_ocr.exact_table_rows(table["table_rows"], native_text), 16)

    def test_v6_scan_crops_preserve_full_printed_text_width(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "data/evaluation/vinamilk_ocr_ground_truth_v6.json").read_text(encoding="utf-8"))
        scans = [page for page in dataset["pages"] if page.get("physical_scan")]
        self.assertEqual(len(scans), 2)
        for scan in scans:
            self.require_source_pdf(root, scan["file"])
            with fitz.open(root / scan["file"]) as pdf:
                page = pdf[scan["page"] - 1]
                clip = fitz.Rect(scan["clip_rect"])
                self.assertLessEqual(clip.x0, 60)
                self.assertLessEqual(page.rect.width - clip.x1, 31)
                self.assertEqual(page.get_text().strip(), "")
                self.assertTrue(page.get_images(full=True))
            self.assertIn("clipped", scan["annotation"])

    def test_v7_adds_four_manually_labeled_image_only_scan_regions(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "data/evaluation/vinamilk_ocr_ground_truth_v7.json").read_text(encoding="utf-8"))
        additions = [
            page for page in dataset["pages"]
            if page["id"] in {
                "charter-2026-board-duties-toc-scan-en",
                "charter-2026-definitions-scan-en",
                "governance-rules-2026-board-meeting-toc-scan-en",
                "governance-rules-2026-ceo-toc-scan-en",
            }
        ]
        self.assertEqual(len(dataset["pages"]), 10)
        self.assertEqual(len(additions), 4)
        self.assertTrue(all(page.get("physical_scan") and page["reference_text"].strip() for page in additions))
        for scan in additions:
            self.require_source_pdf(root, scan["file"])
            with fitz.open(root / scan["file"]) as pdf:
                page = pdf[scan["page"] - 1]
                self.assertEqual(page.get_text().strip(), "")
                self.assertTrue(page.get_images(full=True))
                self.assertTrue(page.rect.contains(fitz.Rect(scan["clip_rect"])))


if __name__ == "__main__":
    unittest.main()
