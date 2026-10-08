import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.processing.package_ocr_benchmark import ensure_dataset_source, package


class PackageOcrBenchmarkTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tools/processing").mkdir(parents=True)
        (self.root / "tools/processing/evaluate_ocr.py").write_text("# test evaluator\n")
        (self.root / "data/raw").mkdir(parents=True)
        (self.root / "data/evaluation").mkdir(parents=True)
        self.source = self.root / "data/raw/sample.pdf"
        self.source.write_bytes(b"%PDF-sample")
        self.labels = self.root / "data/evaluation/sample.json"
        self.labels.write_text(json.dumps({
            "dataset_id": "sample-diagnostic-v1",
            "dataset_title": "Sample OCR Diagnostic",
            "source_pdf_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
            "pages": [{"file": "data/raw/sample.pdf", "page": 1}],
        }))

    def test_packages_selected_dataset_and_hash_checked_source(self):
        with patch("tools.processing.package_ocr_benchmark.REPO_ROOT", self.root):
            result = package(self.root / "bundle", self.labels, "owner/sample-assets")

        project = self.root / "bundle/project"
        self.assertEqual(result["dataset_id"], "owner/sample-assets")
        self.assertTrue((project / "data/evaluation/sample.json").is_file())
        self.assertEqual((project / "data/raw/sample.pdf").read_bytes(), self.source.read_bytes())
        self.assertTrue((project / "scripts/processing/evaluate_ocr.py").is_file())
        metadata = json.loads((self.root / "bundle/dataset-metadata.json").read_text())
        self.assertEqual(metadata["id"], "owner/sample-assets")
        self.assertEqual(metadata["title"], "Sample OCR Diagnostic")
        self.assertIn("labelled page(s)", metadata["description"])
        self.assertNotIn("reviewed page(s)", metadata["description"])

    def test_refuses_source_pdf_that_does_not_match_reviewed_hash(self):
        payload = json.loads(self.labels.read_text())
        del payload["source_pdf_sha256"]
        payload["pages"] = [{
            "file": "data/raw/sample.pdf",
            "page": 1,
            "source_pdf_sha256": "0" * 64,
        }]
        self.labels.write_text(json.dumps(payload))
        with patch("tools.processing.package_ocr_benchmark.REPO_ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                package(self.root / "bundle", self.labels, "owner/sample-assets")

    def test_downloads_source_using_page_level_provenance(self):
        import tools.processing.package_ocr_benchmark as packaging
        source = self.root / "data/raw/downloaded.pdf"
        payload = b"%PDF-page-level-source"
        labels = {
            "pages": [{
                "file": "data/raw/downloaded.pdf",
                "source_url": "https://example.test/page-source.pdf",
                "source_pdf_sha256": hashlib.sha256(payload).hexdigest(),
            }],
        }
        with patch("tools.processing.package_ocr_benchmark.REPO_ROOT", self.root):
            with patch.object(packaging, "urlopen", return_value=BytesIO(payload)):
                ensure_dataset_source(labels, source)
        self.assertEqual(source.read_bytes(), payload)

    def test_downloads_missing_source_only_after_https_pdf_hash_verification(self):
        import tools.processing.package_ocr_benchmark as packaging
        source = self.root / "data/raw/downloaded.pdf"
        payload = b"%PDF-reviewed-source"
        labels = {
            "source_download_url": "https://example.test/source.pdf",
            "source_download_referer": "https://example.test/report",
            "source_pdf_sha256": hashlib.sha256(payload).hexdigest(),
        }
        with patch.object(packaging, "urlopen", return_value=BytesIO(payload)) as open_url:
            ensure_dataset_source(labels, source)
        self.assertEqual(source.read_bytes(), payload)
        self.assertEqual(open_url.call_args.args[0].get_header("Referer"), labels["source_download_referer"])

    def test_rejects_checksum_mismatch_without_creating_source_file(self):
        source = self.root / "data/raw/rejected.pdf"
        labels = {
            "source_download_url": "https://example.test/source.pdf",
            "source_pdf_sha256": "0" * 64,
        }
        with patch("tools.processing.package_ocr_benchmark.urlopen", return_value=BytesIO(b"%PDF-wrong")):
            with self.assertRaisesRegex(ValueError, "hash verification"):
                ensure_dataset_source(labels, source)
        self.assertFalse(source.exists())


if __name__ == "__main__":
    unittest.main()
