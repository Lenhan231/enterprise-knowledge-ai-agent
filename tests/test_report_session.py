"""Report library actions share session boundaries and protect in-flight edits."""
from pathlib import Path
import subprocess
import unittest


class ReportSessionTest(unittest.TestCase):
    def test_workspace_sessions_edits_and_revision_pinned_downloads(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/test_report_workspace.cjs'], cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
