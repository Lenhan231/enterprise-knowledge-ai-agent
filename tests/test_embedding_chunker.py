import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.tokenization.embedding_chunker import build_embedding_chunks
from core.tokenization.token_counter import TokenCounter


class CharacterTokenizer:
    def num_special_tokens_to_add(self, pair=False):
        return 2

    def __call__(self, text, **kwargs):
        return {"offset_mapping": [(i, i + 1) for i in range(len(text))]}

    def encode(self, text, add_special_tokens=False):
        return list(text)


class SourceMappingTest(unittest.TestCase):
    def setUp(self):
        self.counter = TokenCounter.__new__(TokenCounter)
        self.counter.tokenizer = CharacterTokenizer()

    def check_mapping(self, source, chunks):
        for chunk in chunks:
            meta, text = chunk["metadata"], chunk["text"]
            self.assertEqual(meta["source_content_sha256"], hashlib.sha256(source.encode()).hexdigest())
            covered = set()
            for span in meta["source_spans"]:
                a, b = span["source_start"], span["source_end"]
                c, d = span["chunk_start"], span["chunk_end"]
                self.assertEqual(text[c:d], source[a:b])
                self.assertEqual(b - a, d - c)
                covered.update(range(c, d))
            self.assertTrue(all(i in covered or ch.isspace() for i, ch in enumerate(text)))
            self.assertLessEqual(self.counter.count(text) + 2, 96)

    def test_repeated_text_and_unicode_have_actual_offsets_not_first_substring_match(self):
        source = "mã SKU giống nhau " * 20
        pieces = self.counter.split_text_with_offsets(source, 96)
        self.assertEqual(self.counter.split_text(source, 96), [p[0] for p in pieces])
        self.assertGreater(len(pieces), 1)
        self.assertGreater(pieces[1][1], 0)
        for text, a, b in pieces:
            self.assertEqual(text, source[a:b])
        parents = [{"content": source, "parser_chunk_index": 17,
                    "metadata": {"document_id": "DOC", "chunk_index": 99, "page_number": 3}}]
        original = copy.deepcopy(parents)
        chunks = build_embedding_chunks(parents, self.counter, 96, "test")
        self.check_mapping(source, chunks)
        self.assertEqual(parents, original)
        for i, chunk in enumerate(chunks):
            meta = chunk["metadata"]
            self.assertEqual((meta["chunk_index"], meta["source_parser_index"], meta["source_child_index"], meta["source_child_count"]),
                             (i, 17, i, len(chunks)))
            self.assertEqual((meta["document_id"], meta["page_number"]), ("DOC", 3))

    def test_repeated_table_headers_do_not_claim_omitted_body_rows(self):
        prefix = "Section: Inventory\nColumns: SKU | Qty"
        source = prefix + "\n" + "ROW_A 10 ROW_B 20 ROW_C 30 " * 12
        chunks = build_embedding_chunks([{"text": source, "chunk_index": 7}], self.counter, 96, "test")
        self.assertGreater(len(chunks), 1)
        self.check_mapping(source, chunks)
        second = chunks[1]
        self.assertTrue(second["text"].startswith(prefix + "\n"))
        spans = second["metadata"]["source_spans"]
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0]["source_start"], 0)
        self.assertEqual(spans[0]["source_end"], len(prefix) + 1)
        self.assertGreater(spans[1]["source_start"], spans[0]["source_end"])

    def test_crlf_header_normalization_maps_only_real_source_characters(self):
        source = "Section: Bảng\r\nColumns: SKU | Qty\r\n" + "Dòng 1 có số 10\r\n" * 15
        chunks = build_embedding_chunks([{"text": source}], self.counter, 96, "test")
        self.check_mapping(source, chunks)
        self.assertTrue(all("\r" not in chunk["text"] for chunk in chunks))

    def test_source_index_survives_final_renumbering_and_skipped_empty_input(self):
        parents = [{"text": "", "chunk_index": 6}, {"text": "one", "chunk_index": 8},
                   {"content": "two", "metadata": {"chunk_index": 12}}, {"text": "three"}]
        chunks = build_embedding_chunks(parents, self.counter, 96, "test")
        self.assertEqual([x["metadata"]["chunk_index"] for x in chunks], [0, 1, 2])
        self.assertEqual([x["metadata"]["source_parser_index"] for x in chunks], [8, 12, 3])
        self.assertTrue(all(x["metadata"]["source_child_count"] == 1 for x in chunks))


if __name__ == "__main__":
    unittest.main()
