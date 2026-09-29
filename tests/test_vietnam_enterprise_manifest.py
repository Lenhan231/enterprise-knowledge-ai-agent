import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class VietnamEnterpriseManifestTest(unittest.TestCase):
    def test_governance_sources_point_to_documents_and_preserve_stated_versions(self):
        manifest = json.loads(
            (REPO_ROOT / "data/vietnam_enterprises/manifest.json").read_text(encoding="utf-8")
        )
        by_id = {item["document_id"]: item for item in manifest["documents"]}
        governance_ids = [
            "VNM-CGR-2020-EN", "VNM-CGR-2021-EN", "VNM-CGR-2022-EN",
            "VNM-CGR-2023-EN", "VNM-CGR-2024-EN", "VNM-CGR-2025-EN",
            "VNM-CHARTER-2026-EN", "VNM-CGRULES-2026-EN",
            "VNM-CODE-2025-EN", "VNM-DISCLOSURE-2025-EN",
        ]
        for document_id in governance_ids:
            with self.subTest(document_id=document_id):
                item = by_id[document_id]
                self.assertTrue(item["source_url"].lower().endswith(".pdf"))
                self.assertEqual(item["format"], "PDF")
        code = by_id["VNM-CODE-2025-EN"]
        self.assertEqual(code["year_or_version"], "January 2010")
        self.assertIsNone(code["fiscal_year"])
        self.assertIn("PDF cover dates the document January 2010", code["verification"])
        self.assertIn("FiinGroup", by_id["VNM-CGR-2022-EN"]["verification"])

    def test_single_enterprise_manifest_has_one_company_and_unique_ids(self):
        manifest = json.loads(
            (REPO_ROOT / "data/vietnam_enterprises/manifest.json").read_text(encoding="utf-8")
        )
        documents = manifest["documents"]
        document_ids = [document["document_id"] for document in documents]

        self.assertTrue(manifest["company"])
        self.assertEqual({document["company"] for document in documents}, {manifest["company"]})
        self.assertEqual(len(document_ids), len(set(document_ids)))


if __name__ == "__main__":
    unittest.main()
