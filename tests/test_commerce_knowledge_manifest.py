import hashlib
import json
import unittest
from pathlib import Path

import fitz

from scripts.ingestion.generate_commerce_demo_policies import POLICIES, build_html


ROOT = Path(__file__).resolve().parents[1]


class CommerceKnowledgeManifestTest(unittest.TestCase):
    def test_policy_pdfs_are_registered_as_active_scan_only_synthetic_sources(self):
        manifest = json.loads((ROOT / "data/commerce_knowledge/manifest.json").read_text())
        policies = [source for source in manifest["sources"] if source.get("source_type") == "synthetic_demo_policy"]

        self.assertEqual({source["source_id"] for source in policies}, {
            "CD-POL-INV-001", "CD-POL-PROMO-001", "CD-POL-LOG-001",
        })
        for source in policies:
            with self.subTest(source_id=source["source_id"]):
                self.assertEqual(source["retrieval_status"], "active")
                self.assertEqual(source["ingestion_status"], "indexed")
                self.assertTrue(source["synthetic_company_policy"])
                self.assertIn("fictional", source["applicability"].casefold())
                pdf_path = ROOT / source["local_path"]
                pdf_bytes = pdf_path.read_bytes()
                self.assertEqual(hashlib.sha256(pdf_bytes).hexdigest(), source["content_sha256"])
                with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
                    self.assertGreaterEqual(len(pdf), 3)
                    self.assertTrue(all(not page.get_text().strip() and page.get_images() for page in pdf))

    def test_ocr_fixture_is_not_registered_as_business_evidence(self):
        manifest = json.loads((ROOT / "data/commerce_knowledge/manifest.json").read_text())
        sources = {source["source_id"] for source in manifest["sources"]}

        self.assertNotIn("commerce_synthetic_policy_scan_demo", sources)
        self.assertEqual(manifest["ocr_demo"]["status"], "created_isolated_fixture")
        self.assertIn("OCR Lab", manifest["ocr_demo"]["note"])

    def test_current_policy_ocr_references_match_active_pdf_checksums_without_css(self):
        manifest = json.loads((ROOT / "data/commerce_knowledge/manifest.json").read_text())
        sources = {source["source_id"]: source for source in manifest["sources"]}
        dataset = json.loads((ROOT / "data/evaluation/ocr/commerce_policy_scan_ground_truth.json").read_text())

        self.assertEqual(len(dataset["pages"]), 9)
        for page in dataset["pages"]:
            with self.subTest(page=page["id"]):
                source = sources[page["document_id"]]
                self.assertEqual(page["source_pdf_sha256"], source["content_sha256"])
                self.assertNotIn("font-family", page["reference_text"])
                self.assertTrue(page["reference_text"])

    def test_policy_pages_avoid_repeated_summary_and_metadata_table(self):
        policy = POLICIES[0]
        first_page = build_html(policy, 1)
        second_page = build_html(policy, 2)
        metadata_page = build_html(policy, 3)

        self.assertIn('class="summary"', first_page)
        self.assertNotIn('class="summary"', second_page)
        self.assertIn('class="running-title"', second_page)
        self.assertIn('class=\'metadata\'', metadata_page)
        self.assertNotIn("<table class='kv'", metadata_page)


if __name__ == "__main__":
    unittest.main()
