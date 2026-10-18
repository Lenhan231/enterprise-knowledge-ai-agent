import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("candidates", ROOT / "scripts/retrieval/evaluate_embedding_candidates.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CandidateBenchmarkTest(unittest.TestCase):
    def test_prefixes_and_instruction_are_model_specific_without_changing_chunks(self):
        rows, cases = [{"content": "source"}], [{"question": "question"}]
        self.assertEqual(module.inputs_for(module.MODELS["multilingual-e5-base"], rows, cases),
                         (["passage: source"], ["query: question"]))
        passages, queries = module.inputs_for(module.MODELS["qwen3-embedding-0.6b"], rows, cases)
        self.assertEqual(passages, ["source"])
        self.assertTrue(queries[0].startswith("Instruct:"))
        self.assertEqual(rows[0]["content"], "source")

    def test_score_uses_cosine_order_trusted_roles_and_preserves_missing_readme(self):
        rows = [{"content": "hidden", "document_id": "H", "chunk_index": 0, "document_name": "hidden.pdf", "allowed_roles": ["admin"]},
                {"content": "text", "document_id": "D", "chunk_index": 0, "document_name": "source.pdf", "allowed_roles": ["employee"]}]
        vectors = module.unit_vectors([[10, 0], [1, 1]])
        case = {"id": "Q", "question": "question", "allowed_roles": ["employee"],
                "expected_sources": ["source.pdf", "README.txt"], "unavailable_expected_sources": ["README.txt"]}
        result = module.score_case(rows, vectors, np.array([1, 0]), case)
        self.assertEqual(result["ranked_chunk_ids"], ["D::chunk::0"])
        self.assertEqual(result["source_recall_at_10"], 0.5)
        with self.assertRaises(ValueError):
            module.unit_vectors([[0, 0]])

    def test_page_evidence_deduplicates_hits_and_keeps_document_identity(self):
        rows = [{"document_id": doc, "chunk_index": idx, "document_name": doc + ".pdf",
                 "allowed_roles": ["admin"], "metadata": {"page_number": 1}}
                for doc, idx in [("A", 0), ("A", 1), ("B", 0)]]
        case = {"id": "Q", "question": "q", "allowed_roles": ["admin"],
                "expected_sources": ["A.pdf"], "unavailable_expected_sources": [],
                "gold_pages": ["A::page::1", "B::page::2"], "direction": "vi->en"}
        result = module.score_case(rows, np.array([[1, 0], [0.9, 0], [0.8, 0]]), np.array([1, 0]), case)
        self.assertEqual(result["evidence_page_recall_at_10"], 0.5)
        self.assertEqual(result["evidence_page_reciprocal_rank_at_10"], 1.0)

    def test_overlength_prefixed_inputs_fail_instead_of_truncating(self):
        def tokenizer(texts, **kwargs):
            self.assertFalse(kwargs["truncation"])
            return {"input_ids": [list(range(len(text) + 2)) for text in texts]}
        with self.assertRaisesRegex(ValueError, "exceed"):
            module.token_lengths(tokenizer, ["passage: long source"], 10)


if __name__ == "__main__":
    unittest.main()
