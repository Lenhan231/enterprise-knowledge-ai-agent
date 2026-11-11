import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.chunking.preview_processing_output import map_output, preview
from core.chunking.processor import ChunkingProcessor
from core.tokenization.token_counter import TokenCounter


class CharacterTokenizer:
    def num_special_tokens_to_add(self, pair=False):
        return 2

    def __call__(self, text, **kwargs):
        return {"offset_mapping": [(i, i + 1) for i in range(len(text))]}

    def encode(self, text, add_special_tokens=False):
        count = len(text)
        if text.startswith("passage: "):
            count = len(text.removeprefix("passage: ")) + 1
        return list(range(count + (2 if add_special_tokens else 0)))


class ProcessingOutputPreviewTest(unittest.TestCase):
    def test_product_in_ancestor_heading_survives_token_splits(self):
        counter = TokenCounter.__new__(TokenCounter)
        counter.tokenizer = CharacterTokenizer()
        from core.tokenization.embedding_chunker import build_embedding_chunks
        parsed = {"elements": [{"table_ref": 0, "metadata": {
            "element_type": "table", "section_title": "Weight",
            "section_path": ["CTL-4100WL", "Specifications", "Weight"],
        }}], "tables": [{"columns": ["Value"], "rows": [
            {"Value": "250 g " * 40}
        ]}]}
        chunks = ChunkingProcessor().process(parsed)["chunks"]
        bounded = build_embedding_chunks(chunks, counter, 128, "test")
        self.assertGreater(len(bounded), 1)
        for chunk in bounded:
            self.assertTrue(chunk["text"].startswith("Section: CTL-4100WL > Specifications > Weight\n"))
            self.assertEqual(chunk["text"].count("Section:"), 1)
            self.assertLessEqual(chunk["metadata"]["token_count"], 126)

    def setUp(self):
        def text(value, y):
            return {"text": value, "metadata": {"page_number": 1, "bbox": [0, y, 100, y + 10],
                    "bbox_coordinate_origin": "BOTTOMLEFT", "element_type": "text"}}
        self.row = {
            "document_id": "DOC-1", "document_metadata": {"filename": "sample.pdf", "source_sha256": "hash"},
            "text_elements": [text("Before table.", 90), text("After table.", 10)],
            "structured_tables": [{"columns": ["Item"], "rows": [{"Item": "Value"}], "context": {},
                                   "page_number": 1, "table_index": 0,
                                   "metadata": {"bbox": [0, 40, 100, 60], "bbox_coordinate_origin": "BOTTOMLEFT"}}],
            "figures": [{"element_type": "figure", "metadata": {"page_number": 1}}],
        }
        self.document = {"title": "Sample", "domain": "general", "document_type": "report",
                         "allowed_roles": [], "knowledge_base_active": False}

    def test_mapping_restores_table_position_preserves_source_and_denies_empty_roles(self):
        original = copy.deepcopy(self.row)
        parsed, warnings = map_output(self.row, self.document)
        self.assertEqual([e.get("table_ref") for e in parsed["elements"]], [None, 0, None])
        self.assertEqual(self.row, original)
        self.assertEqual(parsed["tables"][0]["metadata"]["source_sha256"], "hash")
        self.assertEqual(parsed["tables"][0]["metadata"]["allowed_roles"], [])
        self.assertTrue(any("deny access" in warning for warning in warnings))
        self.assertEqual(len(parsed["elements"]), 3)

    def test_explicit_source_order_wins_over_coordinates(self):
        self.row["text_elements"][0]["source_order"] = 2
        self.row["text_elements"][1]["source_order"] = 0
        self.row["structured_tables"][0]["source_order"] = 1
        parsed, _ = map_output(self.row, self.document)
        self.assertEqual(parsed["elements"][0]["text"], "After table.")
        self.assertEqual(parsed["metadata"]["reading_order_method"], "source_order")

    def test_canonical_elements_preserve_parser_order_and_table_context(self):
        table = copy.deepcopy(self.row["structured_tables"][0])
        table["context"] = {"table_title": "Sales"}
        canonical = {"document_id": "DOC-1", "document_metadata": self.row["document_metadata"],
                     "elements": [self.row["text_elements"][1],
                                  {"table_ref": 0, "metadata": {"element_type": "table", "page_number": 1, "section_title": "Revenue"}},
                                  self.row["figures"][0], self.row["text_elements"][0]], "tables": [table]}
        original = copy.deepcopy(canonical)
        parsed, _ = map_output(canonical, self.document)
        self.assertEqual(canonical, original)
        self.assertEqual(parsed["metadata"]["reading_order_method"], "stored_elements_order")
        self.assertEqual(parsed["elements"][0]["text"], "After table.")
        self.assertEqual(len(parsed["elements"]), 3)
        chunks = ChunkingProcessor().process(parsed)["chunks"]
        table_chunk = next(c for c in chunks if c["metadata"].get("element_type") == "table")
        self.assertIn("Section: Revenue", table_chunk["text"])
        self.assertIn("Table: Sales", table_chunk["text"])
        self.assertEqual(table_chunk["metadata"]["source_elements"],
                         [{"field": "elements", "index": 1}, {"field": "tables", "index": 0}])

    def test_canonical_invalid_table_reference_is_rejected(self):
        row = {"document_id": "DOC-1", "document_metadata": {}, "tables": [],
               "elements": [{"table_ref": 0, "metadata": {"element_type": "table"}}]}
        with self.assertRaisesRegex(ValueError, "references"):
            map_output(row, self.document)

    def test_top_left_coordinates_and_missing_coordinates(self):
        for item in self.row["text_elements"]:
            item["metadata"]["bbox_coordinate_origin"] = "TOPLEFT"
        self.row["structured_tables"][0]["metadata"].pop("bbox")
        parsed, warnings = map_output(self.row, self.document)
        self.assertEqual(parsed["elements"][0]["text"], "After table.")
        self.assertEqual(parsed["elements"][-1]["table_ref"], 0)
        self.assertTrue(any("unresolved" in w for w in warnings))

    def test_token_preview_is_bounded_and_keeps_parent_and_table_sources(self):
        self.row["text_elements"][0]["text"] = "A long sentence with useful content. " * 15
        counter = TokenCounter.__new__(TokenCounter)
        counter.tokenizer = CharacterTokenizer()
        report = preview(self.row, self.document, counter, "test-e5", limit=128)
        self.assertFalse(report["database_writes"])
        self.assertFalse(report["embeddings_created"])
        self.assertGreater(len(report["embedding_passages"]), len(report["parser_chunks"]))
        self.assertTrue(all(c["metadata"]["prefixed_input_tokens"] <= 128 for c in report["embedding_passages"]))
        table = next(c for c in report["embedding_passages"] if c["metadata"].get("element_type") == "table")
        self.assertIn("Columns: Item", table["text"])
        self.assertEqual(table["metadata"]["source_elements"], [{"field": "structured_tables", "index": 0}])
        self.assertTrue(all("parser_chunk_index" in c["metadata"] for c in report["embedding_passages"]))

    def test_grouping_and_short_merges_keep_all_source_references(self):
        self.row["structured_tables"] = []
        parsed, _ = map_output(self.row, self.document)
        chunks = ChunkingProcessor().process(parsed)["chunks"]
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]["metadata"]["source_elements"]), 2)
        parsed["elements"][1]["metadata"]["element_type"] = "paragraph"
        chunks = ChunkingProcessor().process(parsed)["chunks"]
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]["metadata"]["source_elements"]), 2)

    def test_provenance_does_not_change_chunk_text(self):
        parsed, _ = map_output(self.row, self.document)
        baseline = copy.deepcopy(parsed)
        for element in baseline["elements"]:
            element["metadata"].pop("source_elements", None)
        for table in baseline["tables"]:
            table["metadata"].pop("source_elements", None)
        processor = ChunkingProcessor()
        self.assertEqual([c["text"] for c in processor.process(parsed)["chunks"]],
                         [c["text"] for c in processor.process(baseline)["chunks"]])

    def test_heading_and_backward_merges_preserve_sources(self):
        def element(text, kind, index):
            return {"text": text, "metadata": {"page_number": 1, "section_title": "Heading",
                    "element_type": kind, "source_elements": [{"field": "text_elements", "index": index}]}}
        parsed = {"elements": [element("Heading", "section_header", 0),
                               element("A paragraph containing enough detail to stay separate from the heading. " * 2, "text", 1),
                               element("Short ending.", "paragraph", 2)], "tables": []}
        chunks = ChunkingProcessor().process(parsed)["chunks"]
        self.assertEqual(len(chunks), 1)
        self.assertEqual({s["index"] for s in chunks[0]["metadata"]["source_elements"]}, {0, 1, 2})


if __name__ == "__main__":
    unittest.main()
