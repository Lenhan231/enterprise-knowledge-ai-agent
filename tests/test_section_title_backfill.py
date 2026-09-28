import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from backfill_section_titles import plan_updates


class SectionTitleBackfillTest(unittest.TestCase):
    def test_plans_only_missing_titles_when_all_chunk_text_matches(self):
        parsed = [
            {"chunk_index": 0, "content": "Heading and text", "section_title": "Section A", "page_number": 1},
            {"chunk_index": 1, "content": "More text", "section_title": "Section A", "page_number": 1},
            {"chunk_index": 2, "content": "Existing", "section_title": "Section B", "page_number": 2},
        ]
        stored = [
            {"id": 10, "chunk_index": 0, "content": "Heading and text", "metadata": {"section_title": None}},
            {"id": 11, "chunk_index": 1, "content": "More text", "metadata": {}},
            {"id": 12, "chunk_index": 2, "content": "Existing", "metadata": {"section_title": "Reviewed"}},
        ]

        updates, mismatch = plan_updates(parsed, stored)

        self.assertIsNone(mismatch)
        self.assertEqual([row["chunk_index"] for row in updates], [0, 1])
        self.assertEqual(updates[0]["new_section_title"], "Section A")

    def test_skips_entire_document_on_content_mismatch(self):
        parsed = [{"chunk_index": 0, "content": "Parser text", "section_title": "Section A", "page_number": 1}]
        stored = [{"id": 10, "chunk_index": 0, "content": "Different text", "metadata": {}}]

        updates, mismatch = plan_updates(parsed, stored)

        self.assertEqual(updates, [])
        self.assertEqual(mismatch, "content_mismatch_at_chunk_0")

    def test_skips_document_when_chunk_count_differs(self):
        updates, mismatch = plan_updates(
            [{"chunk_index": 0, "content": "A", "section_title": "Section A", "page_number": 1}],
            [],
        )

        self.assertEqual(updates, [])
        self.assertEqual(mismatch, "chunk_count_mismatch")


if __name__ == "__main__":
    unittest.main()
