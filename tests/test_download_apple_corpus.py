from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from download_apple_corpus import DEFAULT_IDS, read_manifest, safe_filename


MANIFEST = (
    REPO_ROOT / "data/manifests/apple/FA26AI69_Apple_Corpus_Manifest_v1.xlsx"
)


class DownloadAppleCorpusTest(unittest.TestCase):
    def test_vertical_slice_is_present_in_manifest(self):
        documents = {row["document_id"]: row for row in read_manifest(MANIFEST)}

        self.assertLessEqual(set(DEFAULT_IDS), documents.keys())
        self.assertEqual(documents["APL-PRC-001"]["domain"], "Procurement")
        self.assertEqual(documents["APL-SUP-001"]["domain"], "Supply Chain")

    def test_safe_filename_is_stable(self):
        filename = safe_filename(
            {"document_id": "APL-CMP-003", "title": "Anti-Corruption Policy"}
        )

        self.assertEqual(filename, "apl-cmp-003_anti_corruption_policy.pdf")


if __name__ == "__main__":
    unittest.main()
