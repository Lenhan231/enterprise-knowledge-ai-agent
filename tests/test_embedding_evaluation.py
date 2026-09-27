import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate_embeddings import MODELS, _sample_per_document, _visible


class EmbeddingEvaluationTest(unittest.TestCase):
    def test_proposal_model_ids_are_explicit(self):
        self.assertEqual(MODELS["bge-m3"]["model_id"], "BAAI/bge-m3")
        self.assertEqual(MODELS["qwen3-embedding"]["model_id"], "Qwen/Qwen3-Embedding-0.6B")
        self.assertEqual(MODELS["e5-large-v2"]["model_id"], "intfloat/e5-large-v2")

    def test_role_filter_is_applied_before_scoring(self):
        row = {"allowed_roles": ["finance_analyst"]}
        self.assertTrue(_visible(row, ["finance_analyst"]))
        self.assertTrue(_visible(row, ["admin"]))
        self.assertFalse(_visible(row, ["employee"]))

    def test_e5_uses_query_and_passage_prefixes(self):
        self.assertEqual(MODELS["e5-large-v2"]["query_prefix"], "query: ")
        self.assertEqual(MODELS["e5-large-v2"]["passage_prefix"], "passage: ")

    def test_sampling_is_even_and_keeps_each_document(self):
        rows = [
            {"document_id": "A", "content": str(index)} for index in range(10)
        ] + [{"document_id": "B", "content": "only"}]
        sampled = _sample_per_document(rows, 3)
        self.assertEqual([row["content"] for row in sampled if row["document_id"] == "A"], ["0", "4", "9"])
        self.assertEqual([row["content"] for row in sampled if row["document_id"] == "B"], ["only"])


if __name__ == "__main__":
    unittest.main()
