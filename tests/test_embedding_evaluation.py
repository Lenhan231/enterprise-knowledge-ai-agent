import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.retrieval.evaluate_embeddings as evaluate_embeddings
from app.main import ROLE_PERMISSIONS
from scripts.retrieval.evaluate_embeddings import MODELS, _load_public_corpus, _sample_per_document, _visible


class EmbeddingEvaluationTest(unittest.TestCase):
    def test_commerce_retrieval_labels_cover_each_decision_case_with_active_sources(self):
        root = Path(__file__).resolve().parents[1]
        cases = json.loads((root / "data/evaluation/commerce_retrieval_cases.json").read_text())
        decision_data = json.loads((root / "data/evaluation/commerce_decision_benchmark.json").read_text())
        manifest = json.loads((root / "data/commerce_knowledge/manifest.json").read_text())
        active_sources = {
            source["source_id"]: source for source in manifest["sources"]
            if source.get("retrieval_status") == "active"
        }
        decision_case_ids = {
            case["id"]
            for domain in decision_data["domains"].values()
            for case in domain["cases"]
        }

        retrieval_case_ids = {case["id"] for case in cases["cases"]}
        self.assertTrue(decision_case_ids <= retrieval_case_ids)
        self.assertEqual(retrieval_case_ids - decision_case_ids, {"INV-MAN-01", "PROMO-MAN-01", "LOG-MAN-01"})
        self.assertTrue(all(case["relevant_document_ids"] for case in cases["cases"]))
        self.assertTrue(all(
            set(case["relevant_document_ids"]) <= active_sources.keys()
            and all(case["domain"] in active_sources[source_id]["domains"]
                    for source_id in case["relevant_document_ids"])
            for case in cases["cases"]
        ))

    def test_commerce_retrieval_cases_use_real_application_roles(self):
        root = Path(__file__).resolve().parents[1]
        cases = json.loads((root / "data/evaluation/commerce_retrieval_cases.json").read_text())
        for case in cases["cases"]:
            with self.subTest(case=case["id"]):
                self.assertIn(case["role"], ROLE_PERMISSIONS)
                self.assertEqual(case["allowed_roles"], [case["role"]])

    def test_promotion_roi_case_distinguishes_gross_profit_proxy_from_roi(self):
        root = Path(__file__).resolve().parents[1]
        decision_data = json.loads((root / "data/evaluation/commerce_decision_benchmark.json").read_text())
        case = next(
            case for case in decision_data["domains"]["promotion_planning"]["cases"]
            if case["id"] == "PROMO-03"
        )

        self.assertIn("catalog COGS", " ".join(case["gold_observations"][0]["available"]))
        self.assertIn("must not call it contribution margin", case["expected_behavior"])
        self.assertIn("ROI", case["expected_behavior"])

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
        row = {"document_id": "DOC-1", "allowed_roles": ["analyst"], "content": "inventory location"}
        with tempfile.TemporaryDirectory() as temp_dir:
            corpus_path = Path(temp_dir) / "corpus.jsonl"
            corpus_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            self.assertEqual(_load_public_corpus(corpus_path, {"DOC-1"}), [row])
            with self.assertRaisesRegex(ValueError, "not allowlisted"):
                _load_public_corpus(corpus_path, {"OTHER"})

    def test_public_corpus_cli_runs_without_database_credentials(self):
        import numpy as np

        case = {
            "id": "INV-01", "role": "analyst", "allowed_roles": ["analyst"],
            "question": "What inventory evidence is needed across locations?",
            "relevant_document_ids": ["SHOPIFY-MULTI-LOCATION-INVENTORY-2026"],
        }
        document_id = case["relevant_document_ids"][0]
        row = {"document_id": document_id, "allowed_roles": case["allowed_roles"], "content": "inventory location"}

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
                    "scripts.retrieval.evaluate_embeddings.py", "--model", "bge-m3", "--cases", str(cases_fixture),
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
