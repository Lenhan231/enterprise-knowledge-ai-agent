import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import fitz

from tools.ingestion.generate_commerce_demo_policies import POLICIES, _VisibleText, build_html
from tools.ingestion import ingest_commerce_knowledge
from tools.ingestion.ingest_commerce_knowledge import APPROVED_HOSTS


ROOT = Path(__file__).resolve().parents[1]


class CommerceKnowledgeManifestTest(unittest.TestCase):
    def test_local_policy_download_only_reuses_source_without_raw_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            local_path = root / "data/commerce_knowledge/synthetic_policies/policy.pdf"
            local_path.parent.mkdir(parents=True)
            local_path.write_bytes(b"%PDF-1.4 local test source")
            manifest_path = root / "data/commerce_knowledge/manifest.json"
            manifest_path.write_text(json.dumps({"sources": [{
                "source_id": "CD-POL-TEST",
                "local_path": "data/commerce_knowledge/synthetic_policies/policy.pdf",
                "retrieval_status": "active",
                "publisher": "Commerce Demo",
                "domains": ["inventory_allocation"],
                "title": "Test policy",
                "published_or_updated": "demo",
                "source_type": "synthetic_demo_policy",
                "synthetic_company_policy": True,
            }]}))

            with patch.object(ingest_commerce_knowledge, "ROOT", root):
                with patch.object(sys, "argv", ["ingest_commerce_knowledge.py", "--download-only"]):
                    self.assertEqual(ingest_commerce_knowledge.main(), 0)

            self.assertTrue(local_path.is_file())
            self.assertFalse((root / "data/raw/commerce_knowledge/CD-POL-TEST.pdf").exists())

    def test_government_business_guides_are_archived_from_active_retrieval(self):
        manifest = json.loads((ROOT / "data/commerce_knowledge/manifest.json").read_text())
        sources = [
            item for item in manifest["sources"]
            if item.get("publisher") == "Australian Government, business.gov.au"
        ]

        self.assertEqual(len(sources), 3)
        self.assertTrue(all(item["retrieval_status"] == "archived" for item in sources))
        self.assertTrue(all(item["ingestion_status"] == "archived" for item in sources))

    def test_shopify_marketing_plan_is_an_active_attributed_reference(self):
        manifest = json.loads((ROOT / "data/commerce_knowledge/manifest.json").read_text())
        source = next(
            item for item in manifest["sources"]
            if item["source_id"] == "SHOPIFY-HELP-DEVELOPING-MARKETING-PLAN"
        )

        self.assertEqual(source["retrieval_status"], "active")
        self.assertEqual(source["ingestion_status"], "indexed")
        self.assertEqual(source["evidence_class"], "company_practice_reference")
        self.assertNotEqual(source["evidence_class"], "company_policy_reference")
        self.assertEqual(source["domains"], ["promotion_planning"])
        self.assertTrue(source["content_sha256"])

    def test_iab_incrementality_pdf_is_a_domain_scoped_method_not_demo_policy(self):
        manifest = json.loads((ROOT / "data/commerce_knowledge/manifest.json").read_text())
        source = next(
            item for item in manifest["sources"]
            if item["source_id"] == "IAB-COMMERCE-INCREMENTALITY-GUIDELINES-2025"
        )

        self.assertEqual(source["retrieval_status"], "active")
        self.assertEqual(source["evidence_class"], "management_cookbook_reference")
        self.assertEqual(source["domains"], ["promotion_planning"])
        self.assertFalse(source["external_policy_reference"])
        self.assertIn("it is not a platform rule or Commerce Demo policy", source["applicability"])
        self.assertTrue(source["content_sha256"])

    def test_kroger_routing_pdf_is_scoped_to_its_supplier_policy(self):
        manifest = json.loads((ROOT / "data/commerce_knowledge/manifest.json").read_text())
        source = next(
            item for item in manifest["sources"]
            if item["source_id"] == "KROGER-VENDOR-ROUTING-INSTRUCTIONS-2024"
        )

        self.assertEqual(source["retrieval_status"], "active")
        self.assertEqual(source["domains"], ["nationwide_logistics"])
        self.assertEqual(source["evidence_class"], "company_practice_reference")
        self.assertTrue(source["external_policy_reference"])
        self.assertIn("not Commerce Demo policy", source["applicability"])
        self.assertIn("not a physical scan", source["notes"])
        self.assertIn(urlparse(source["url"]).hostname, APPROVED_HOSTS)

    def test_tiki_operating_guides_are_scoped_to_their_platform_domains(self):
        manifest = json.loads((ROOT / "data/commerce_knowledge/manifest.json").read_text())
        sources = {source["source_id"]: source for source in manifest["sources"]}
        expected = {
            "TIKI-FBT-INVENTORY-REPORT": "inventory_allocation",
            "TIKI-CATEGORY-DEAL-OPERATIONS": "promotion_planning",
            "TIKI-FBT-INVENTORY-TRANSFER": "nationwide_logistics",
        }

        for source_id, domain in expected.items():
            with self.subTest(source_id=source_id):
                source = sources[source_id]
                self.assertEqual(source["retrieval_status"], "active")
                self.assertEqual(source["ingestion_status"], "indexed")
                self.assertEqual(source["domains"], [domain])
                self.assertEqual(source["publisher"], "Tiki Seller Academy")
                self.assertEqual(source["evidence_class"], "platform_operating_rule")
                self.assertTrue(source["external_policy_reference"])
                self.assertEqual(len(source["content_sha256"]), 64)
                self.assertIn("Tiki", source["applicability"])
                self.assertIn(urlparse(source["url"]).hostname, APPROVED_HOSTS)

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

    def test_ocr_fixture_is_kept_out_of_production_knowledge_manifest(self):
        manifest = json.loads((ROOT / "data/commerce_knowledge/manifest.json").read_text())
        sources = {source["source_id"] for source in manifest["sources"]}

        self.assertNotIn("commerce_synthetic_policy_scan_demo", sources)
        self.assertEqual(manifest["ocr_demo"]["status"], "created_isolated_fixture")
        self.assertIn("Upload Test", manifest["ocr_demo"]["note"])

    def test_current_policy_ocr_references_match_active_pdf_checksums_without_css(self):
        manifest = json.loads((ROOT / "data/commerce_knowledge/manifest.json").read_text())
        sources = {source["source_id"]: source for source in manifest["sources"]}
        dataset_path = ROOT / "data/evaluation/ocr/commerce_policy_scan_ground_truth.json"
        dataset_bytes = dataset_path.read_bytes()
        dataset = json.loads(dataset_bytes)
        report = json.loads((ROOT / "artifacts/evaluation/ocr/pipeline/commerce-active-policy-scan-ocr-20261008.json").read_text())
        result_pages = {page["id"]: page for page in report["results"]}

        self.assertEqual(len(dataset["pages"]), 9)
        self.assertEqual(report["dataset_sha256"], hashlib.sha256(dataset_bytes).hexdigest())
        for page in dataset["pages"]:
            with self.subTest(page=page["id"]):
                source = sources[page["document_id"]]
                self.assertEqual(page["source_pdf_sha256"], source["content_sha256"])
                self.assertEqual(result_pages[page["id"]]["source_pdf_sha256"], page["source_pdf_sha256"])
                self.assertNotIn("font-family", page["reference_text"])
                self.assertNotRegex(page["reference_text"], r"\bPage\s+\d+/\d+\b")
                self.assertTrue(page["reference_text"])

    def test_current_policy_ocr_preserves_decision_limiting_qualifiers(self):
        dataset = json.loads((ROOT / "data/evaluation/ocr/commerce_policy_scan_ground_truth.json").read_text())
        report = json.loads((ROOT / "artifacts/evaluation/ocr/pipeline/commerce-active-policy-scan-ocr-20261008.json").read_text())
        reference_pages = {page["id"]: page["reference_text"] for page in dataset["pages"]}
        result_pages = {page["id"]: page["ocr_text"] for page in report["results"]}
        qualifiers = ("không", "chỉ", "nếu", "phải", "cần", "không được")

        def normalized(text):
            return " ".join(re.findall(r"\w+", text.casefold()))

        def count(text, term):
            return len(re.findall(rf"(?<!\w){re.escape(normalized(term))}(?!\w)", normalized(text)))

        self.assertEqual(reference_pages.keys(), result_pages.keys())
        for term in qualifiers:
            self.assertGreater(sum(count(text, term) for text in reference_pages.values()), 0, term)
            for page_id, reference in reference_pages.items():
                with self.subTest(page=page_id, qualifier=term):
                    self.assertEqual(count(reference, term), count(result_pages[page_id], term))

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

    def test_policy_ocr_reference_excludes_page_counter_footer(self):
        text = _VisibleText()
        text.feed(build_html(POLICIES[0], 1))

        self.assertTrue(text.parts)
        self.assertNotIn("Page 1/3", " ".join(text.parts))

    def test_inventory_policy_page_keeps_qualitative_decision_rules_as_text(self):
        first_page = build_html(POLICIES[0], 1)

        self.assertIn("lịch sử sự cố", first_page)
        self.assertIn("Không diễn giải số cờ", first_page)
        self.assertIn("báo cáo phần giao nhau", first_page)


if __name__ == "__main__":
    unittest.main()
