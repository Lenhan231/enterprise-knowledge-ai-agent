import unittest

from scripts.evaluate_rerankers import (
    MODELS,
    _available_memory_mb,
    _metrics,
    _passage_cutoffs,
    _ranked_documents,
    _ranked_passages,
)


class RerankerEvaluationTest(unittest.TestCase):
    def test_proposal_reranker_ids_are_explicit(self):
        self.assertEqual(MODELS["bge-reranker-v2-m3"], "BAAI/bge-reranker-v2-m3")
        self.assertEqual(MODELS["qwen3-reranker-0.6b"], "Qwen/Qwen3-Reranker-0.6B")

    def test_available_memory_reader_returns_positive_value_when_procfs_exists(self):
        value = _available_memory_mb()
        if value is not None:
            self.assertGreater(value, 0)
            self.assertLess(value, 1024 * 1024)

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


if __name__ == "__main__":
    unittest.main()
