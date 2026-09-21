from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.download_apple_corpus import (
    DEFAULT_IDS,
    read_manifest,
    safe_filename,
)


class DownloadAppleCorpusTest(unittest.TestCase):
    @patch("scripts.download_apple_corpus.DocumentRepository")
    def test_manifest_is_loaded_from_repository_and_connection_is_closed(self, repository_type):
        repository = MagicMock()
        repository.list_documents.return_value = [{"document_id": DEFAULT_IDS[0]}]
        repository_type.return_value = repository

        self.assertEqual(read_manifest(), [{"document_id": DEFAULT_IDS[0]}])
        repository.list_documents.assert_called_once_with()
        repository.close.assert_called_once_with()

    def test_safe_filename_is_stable(self):
        filename = safe_filename(
            {"document_id": "APL-CMP-003", "title": "Anti-Corruption Policy"}
        )

        self.assertEqual(filename, "apl-cmp-003_anti_corruption_policy.pdf")

if __name__ == "__main__":
    unittest.main()
