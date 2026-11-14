import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.chunking.config import ChunkingConfig
from core.chunking.processor import ChunkingProcessor
from core.chunking.router import build_chunks
from document_processing.document_processor import DocumentProcessor
from core.tokenization.embedding_chunker import build_embedding_chunks
from core.tokenization.token_counter import TokenCounter


class _CharacterTokenizer:
    def num_special_tokens_to_add(self, pair=False):
        return 2

    def __call__(self, text, **kwargs):
        return {"offset_mapping": [(index, index + 1) for index in range(len(text))]}

    def encode(self, text, add_special_tokens=False):
        return list(text)


class DocumentProcessingChunkContextTest(unittest.TestCase):
    def test_table_fragments_repeat_section_title_and_column_headers(self):
        config = ChunkingConfig(strategy="sentence", size=75, overlap=0)
        chunks = build_chunks({
            "table_index": 0,
            "columns": ["Account", "Amount"],
            "rows": [
                {"Account": f"Operating cash row {index}", "Amount": str(index * 1000)}
                for index in range(5)
            ],
            "metadata": {"table_title": "Cash balances"},
        }, config, kind="table", metadata={"section_title": "Assets"})

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertEqual(chunk["text"].count("Section: Assets"), 1)
            self.assertEqual(chunk["text"].count("Table: Cash balances"), 1)
            self.assertEqual(chunk["text"].count("Columns: Account | Amount"), 1)

    def test_token_splits_repeat_context_once_and_respect_limit(self):
        counter = TokenCounter.__new__(TokenCounter)
        counter.tokenizer = _CharacterTokenizer()
        source = {
            "text": (
                "Section: Operations\nTable: Cash balances\nColumns: Account | Amount\n"
                + "\n".join(f"Row {index}: Account: cash balance {index} | Amount: {index * 1000}" for index in range(4))
            ),
            "metadata": {"section_title": "Operations", "layout_type": "table"},
        }

        chunks = build_embedding_chunks([source], counter, 100, "test-model")

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertTrue(chunk["text"].startswith(
                "Section: Operations\nTable: Cash balances\nColumns: Account | Amount\n"
            ))
            self.assertEqual(chunk["text"].count("Section: Operations"), 1)
            self.assertLessEqual(chunk["metadata"]["token_count"], 98)

    def test_upload_test_does_not_send_table_fragments_through_text_chunker(self):
        parsed = {
            "elements": [{"text": "source table element", "table_ref": 0, "metadata": {
                "element_type": "table", "layout_type": "table", "table_index": 0,
                "section_title": "Finance", "section_path": ["Finance"],
            }}],
            "tables": [{"table_index": 0, "columns": ["Year", "Amount"],
                "rows": [{"Year": "2024", "Amount": "100"}],
                "metadata": {"table_title": "Revenue"}}],
        }
        result = ChunkingProcessor({"chunk_size": 24, "chunk_overlap": 0}).process(parsed)

        self.assertEqual(len(result["chunks"]), 1)
        self.assertIn("Table: Revenue", result["chunks"][0]["text"])
        self.assertEqual(result["chunks"][0]["metadata"]["chunking_method"], "table_row_groups")


if __name__ == "__main__":
    unittest.main()
