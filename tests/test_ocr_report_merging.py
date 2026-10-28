import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/processing/merge_ocr_reports.py"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
SPEC = importlib.util.spec_from_file_location("merge_ocr_reports", SCRIPT)
merge_ocr_reports = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(merge_ocr_reports)


class OCRReportMergingTests(unittest.TestCase):
    def setUp(self):
        self.dataset = {
            "dataset_id": "combined",
            "render_dpi": 180,
            "reference_method": "reviewed",
            "reference_quality": "diagnostic",
            "limitations": "small test fixture",
            "pages": [
                {"document_id": "A", "page": 1, "language": "vi",
                 "source_pdf_sha256": "pdf-a", "rendered_image_sha256": "image-a",
                 "reference_text": "recognized text", "reference_annotation_method": "manual"},
                {"document_id": "B", "page": 2, "language": "en",
                 "source_pdf_sha256": "pdf-b", "rendered_image_sha256": "image-b",
                 "reference_text": "recognized text", "reference_annotation_method": "assisted"},
            ],
        }

    def report(self, dataset_id, row, *, version="1.0", device="cpu"):
        return {
            "dataset": dataset_id,
            "dataset_sha256": f"hash-{dataset_id}",
            "render_dpi": 180,
            "ocr_configuration": {"render_dpi": 180},
            "environment": {"process_peak_rss_mb": 100},
            "engines": {"example": {
                "engine_version": version,
                "runtime_device": device,
                "model_initialization_seconds": 1,
                "memory_telemetry": {"torch_cuda_peak_allocated_mb": None},
                "pages": [row],
            }},
        }

    def page(self, document_id, number, pdf_hash, image_hash):
        return {"document_id": document_id, "page": number, "language": "vi" if document_id == "A" else "en",
                "source_pdf_sha256": pdf_hash, "rendered_image_sha256": image_hash,
                "hypothesis_text": "recognized text", "reference_characters": 14,
                "reference_words": 2, "character_edit_distance": 7, "word_edit_distance": 1,
                "cer": 0.5, "wer": 0.5, "latency_seconds": 1, "error": None}

    def write_reports(self, directory, rows, **kwargs):
        paths = []
        for index, (dataset_id, row) in enumerate(rows):
            path = directory / f"run-{index}.json"
            path.write_text(json.dumps(self.report(dataset_id, row, **kwargs)))
            paths.append(path)
        return paths

    def test_merges_disjoint_hash_matched_pages_in_dataset_order(self):
        with tempfile.TemporaryDirectory(dir=SCRIPT.parents[1]) as temp:
            directory = Path(temp)
            reports = self.write_reports(directory, [
                ("second", self.page("B", 2, "pdf-b", "image-b")),
                ("first", self.page("A", 1, "pdf-a", "image-a")),
            ])

            result = merge_ocr_reports.merge_reports(self.dataset, "combined-hash", reports)["example"]
            engine = result["engines"]["example"]

        self.assertEqual([(row["document_id"], row["page"]) for row in engine["pages"]], [("A", 1), ("B", 2)])
        self.assertEqual(result["dataset_sha256"], "combined-hash")
        self.assertEqual(result["source_dataset_sha256s"], ["hash-first", "hash-second"])
        self.assertEqual(result["environment"]["process_peak_rss_mb"], 100)
        self.assertEqual(engine["pages"][0]["character_edit_distance"], 0)
        self.assertEqual(engine["pages"][0]["word_edit_distance"], 0)
        self.assertEqual(engine["pages"][0]["reference_source"], "manual")

    def test_rejects_render_hash_mismatch_and_engine_version_drift(self):
        with tempfile.TemporaryDirectory(dir=SCRIPT.parents[1]) as temp:
            directory = Path(temp)
            bad_hash = self.write_reports(directory, [
                ("first", self.page("A", 1, "pdf-a", "wrong-image")),
                ("second", self.page("B", 2, "pdf-b", "image-b")),
            ])
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                merge_ocr_reports.merge_reports(self.dataset, "combined-hash", bad_hash)

            drifted = self.write_reports(directory, [
                ("first", self.page("A", 1, "pdf-a", "image-a")),
                ("second", self.page("B", 2, "pdf-b", "image-b")),
            ])
            second = json.loads(drifted[1].read_text())
            second["engines"]["example"]["engine_version"] = "2.0"
            drifted[1].write_text(json.dumps(second))
            with self.assertRaisesRegex(ValueError, "version or runtime device"):
                merge_ocr_reports.merge_reports(self.dataset, "combined-hash", drifted)

            changed_environment = self.write_reports(directory, [
                ("first", self.page("A", 1, "pdf-a", "image-a")),
                ("second", self.page("B", 2, "pdf-b", "image-b")),
            ])
            second = json.loads(changed_environment[1].read_text())
            second["environment"]["gpu"] = "different GPU"
            changed_environment[1].write_text(json.dumps(second))
            with self.assertRaisesRegex(ValueError, "runtime environment"):
                merge_ocr_reports.merge_reports(self.dataset, "combined-hash", changed_environment)

            changed_settings = self.write_reports(directory, [
                ("first", self.page("A", 1, "pdf-a", "image-a")),
                ("second", self.page("B", 2, "pdf-b", "image-b")),
            ])
            second = json.loads(changed_settings[1].read_text())
            second["ocr_configuration"]["psm"] = 11
            changed_settings[1].write_text(json.dumps(second))
            with self.assertRaisesRegex(ValueError, "Mixed OCR settings"):
                merge_ocr_reports.merge_reports(self.dataset, "combined-hash", changed_settings)


if __name__ == "__main__":
    unittest.main()
