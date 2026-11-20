import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.retrieval.evaluate_rerankers import (
    MODELS,
    _available_memory_mb,
    _candidate_sha256,
    _load_candidate_bundle,
    _metrics,
    _passage_cutoffs,
    _ranked_documents,
    _ranked_passages,
)


class RerankerEvaluationTest(unittest.TestCase):
    def test_proposal_reranker_ids_are_explicit(self):
        self.assertEqual(MODELS["bge-reranker-v2-m3"], "BAAI/bge-reranker-v2-m3")
        self.assertEqual(MODELS["qwen3-reranker-0.6b"], "Qwen/Qwen3-Reranker-0.6B")

    def test_available_memory_reader_allows_genuine_zero_when_host_is_exhausted(self):
        value = _available_memory_mb()
        if value is not None:
            self.assertGreaterEqual(value, 0)
            self.assertLess(value, 1024 * 1024)

    def test_available_memory_reader_converts_kib_to_mib(self):
        with patch("scripts.retrieval.evaluate_rerankers.Path.read_text", return_value="MemAvailable: 2048 kB\n"):
            self.assertEqual(_available_memory_mb(), 2)

    def test_chunk_ranking_collapses_to_first_document_occurrence(self):
        chunks = [
            {"document_id": "report-2024", "chunk_id": "a"},
            {"document_id": "report-2024", "chunk_id": "b"},
            {"document_id": "report-2023", "chunk_id": "c"},
        ]
        self.assertEqual(_ranked_documents(chunks), ["report-2024", "report-2023"])

    def test_metrics_score_relevant_document_at_rank_one(self):
        metrics = _metrics({"report-2024"}, ["report-2024", "other"])
        self.assertEqual(metrics["precision@1"], 1.0)
        self.assertEqual(metrics["mrr"], 1.0)
        self.assertEqual(metrics["ndcg@3"], 1.0)

    def test_passage_metrics_can_detect_a_reranking_improvement(self):
        candidates = [
            {"chunk_id": "irrelevant", "document_id": "report-2024"},
            {"chunk_id": "evidence", "document_id": "report-2024"},
        ]
        baseline = _ranked_passages(candidates)
        reranked = _ranked_passages(list(reversed(candidates)))
        relevant = {"evidence"}

        self.assertEqual(_metrics(relevant, baseline)["mrr"], 0.5)
        self.assertEqual(_metrics(relevant, reranked)["mrr"], 1.0)
        self.assertEqual(_metrics(relevant, baseline, cutoffs=(1, 2))["precision@2"], 0.5)

    def test_passage_cutoffs_are_shared_and_never_exceed_candidate_depth(self):
        self.assertEqual(_passage_cutoffs([2, 1, 2]), (1,))
        self.assertEqual(_passage_cutoffs([2, 2]), (1, 2))
        self.assertEqual(_passage_cutoffs([30, 30]), (1, 3, 5))
        self.assertEqual(_passage_cutoffs([0, 2]), ())

    def test_candidate_bundle_requires_matching_case_labels_and_content_hash(self):
        case = {
            "id": "case-a", "question": "Find the source passage", "role": "finance_analyst",
            "relevant_document_ids": ["report-2024"], "relevant_chunk_ids": ["report-2024::chunk::2"],
        }
        candidates = [{
            "id": case["id"], "query": case["question"], "role": case["role"],
            "relevant_document_ids": case["relevant_document_ids"],
            "relevant_passage_ids": case["relevant_chunk_ids"], "retrieval_latency_ms": 12.5,
            "items": [{"chunk_id": "report-2024::chunk::2", "text": "Source text", "dense_score": 0.9}],
        }]
        cases_bytes = b'{"cases":["frozen labels"]}'
        bundle = {
            "schema": "vinamilk-role-filtered-reranker-candidates-v1",
            "case_file_sha256": hashlib.sha256(cases_bytes).hexdigest(),
            "candidate_sha256": _candidate_sha256(candidates),
            "cases": candidates,
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.json"
            path.write_text(json.dumps(bundle), encoding="utf-8")
            loaded, digest = _load_candidate_bundle(path, [case], cases_bytes, candidate_k=30)

        self.assertEqual(loaded, candidates)
        self.assertEqual(digest, bundle["candidate_sha256"])

    def test_candidate_bundle_rejects_hash_mismatch_and_missing_cases(self):
        case = {
            "id": "case-a", "question": "Find the source passage", "role": "finance_analyst",
            "relevant_document_ids": ["report-2024"], "relevant_chunk_ids": [],
        }
        bundle = {
            "schema": "vinamilk-role-filtered-reranker-candidates-v1",
            "case_file_sha256": "wrong", "candidate_sha256": "wrong", "cases": [],
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.json"
            path.write_text(json.dumps(bundle), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different labeled case file"):
                _load_candidate_bundle(path, [case], b"labels", candidate_k=30)


if __name__ == "__main__":
    unittest.main()
