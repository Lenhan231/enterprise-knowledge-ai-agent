import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import evaluate_embeddings
from evaluate_embeddings import MODELS, _load_public_corpus, _sample_per_document, _visible


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

    def test_public_corpus_loader_preserves_roles_and_rejects_unknown_documents(self):
        row = {"document_id": "VNM-AR-2024-VI", "allowed_roles": ["finance_analyst"], "content": "revenue"}
        with tempfile.TemporaryDirectory() as temp_dir:
            corpus_path = Path(temp_dir) / "corpus.jsonl"
            corpus_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            self.assertEqual(_load_public_corpus(corpus_path, {"VNM-AR-2024-VI"}), [row])
            with self.assertRaisesRegex(ValueError, "not allowlisted"):
                _load_public_corpus(corpus_path, {"OTHER"})

    def test_public_corpus_cli_runs_without_database_credentials(self):
        import numpy as np

        cases_path = Path(__file__).resolve().parents[1] / "data/evaluation/vinamilk_retrieval_cases.json"
        case = json.loads(cases_path.read_text(encoding="utf-8"))["cases"][0]
        document_id = case["relevant_document_ids"][0]
        row = {"document_id": document_id, "allowed_roles": case["allowed_roles"], "content": "annual financial results"}

        class Model:
            max_seq_length = 512

            def __getitem__(self, _index):
                return SimpleNamespace(auto_model=SimpleNamespace(config=SimpleNamespace(_commit_hash="fixture")))

            def encode(self, texts, **_kwargs):
                return np.tile(np.array([[1.0, 0.0]]), (len(texts), 1))

        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus_path = root / "corpus.jsonl"
            corpus_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            cases_fixture = root / "cases.json"
            cases_fixture.write_text(json.dumps({"cases": [case]}), encoding="utf-8")
            output_path = root / "report.json"
            with (
                patch.dict(sys.modules, {
                    "sentence_transformers": MagicMock(SentenceTransformer=lambda *_args, **_kwargs: Model()),
                    "torch": torch,
                    "dotenv": None,
                }),
                patch.dict(os.environ, {"DATABASE_URL": ""}),
                patch.object(evaluate_embeddings, "REPO_ROOT", Path(__file__).resolve().parents[1]),
                patch.object(sys, "argv", [
                    "evaluate_embeddings.py", "--model", "bge-m3", "--cases", str(cases_fixture),
                    "--corpus", str(corpus_path), "--device", "cpu", "--output", str(output_path),
                ]),
            ):
                self.assertEqual(evaluate_embeddings.main(), 0)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["corpus_source"], "public_manifest_jsonl")
            self.assertEqual(report["environment"]["gpu_name"], None)
            self.assertEqual(report["aggregate"]["recall@1"], 1.0)
            self.assertTrue(report["all_corpus_chunks_included"])
            self.assertIn("all eligible passages", report["configuration"]["sample_strategy"])
            self.assertNotIn("not full-corpus retrieval", report["limitations"])


if __name__ == "__main__":
    unittest.main()
