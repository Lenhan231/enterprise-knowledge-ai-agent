from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from download_apple_corpus import (
    DEFAULT_IDS,
    read_manifest,
    safe_filename,
)


class DownloadAppleCorpusTest(unittest.TestCase):
    @patch("download_apple_corpus.DocumentRepository")
    def test_read_manifest_calls_repository(self, MockRepository):
        mock_repo = MockRepository.return_value
        mock_repo.list_documents.return_value = [{"document_id": "A"}]
        
        result = read_manifest()
        
        self.assertEqual(result, [{"document_id": "A"}])
        mock_repo.list_documents.assert_called_once()
        mock_repo.close.assert_called_once()

    def test_safe_filename_is_stable(self):
        filename = safe_filename(
            {"document_id": "APL-CMP-003", "title": "Anti-Corruption Policy"}
        )

        self.assertEqual(filename, "apl-cmp-003_anti_corruption_policy.pdf")


if __name__ == "__main__":
    unittest.main()
