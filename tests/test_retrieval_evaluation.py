from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_retrieval import parent_context_metrics, ranked_passage_ids


class RetrievalEvaluationTest(unittest.TestCase):
    def test_parent_results_expand_in_order_and_overlaps_are_deduplicated(self):
        results = [
            SimpleNamespace(document_id="DOC-A", location=SimpleNamespace(chunk_index=7), metadata={}),
            SimpleNamespace(
                document_id="DOC-B",
                location=SimpleNamespace(chunk_index=3),
                metadata={"parent_chunk_indices": [3, 4, 5]},
            ),
            SimpleNamespace(
                document_id="DOC-B",
                location=SimpleNamespace(chunk_index=4),
                metadata={"parent_chunk_indices": [4, 5, 6]},
            ),
        ]
        self.assertEqual(ranked_passage_ids(results), [
            "DOC-A::chunk::7",
            "DOC-B::chunk::3",
            "DOC-B::chunk::4",
            "DOC-B::chunk::5",
            "DOC-B::chunk::6",
        ])

    def test_parent_contexts_score_hits_and_gold_passage_coverage_by_window(self):
        results = [
            SimpleNamespace(
                document_id="DOC-A", chunk_id="DOC-A::parent::2-3",
                location=SimpleNamespace(chunk_index=2),
                metadata={"parent_id": "DOC-A::parent::2-3", "parent_chunk_indices": [2, 3]},
            ),
            SimpleNamespace(
                document_id="DOC-A", chunk_id="DOC-A::parent::4-5",
                location=SimpleNamespace(chunk_index=4),
                metadata={"parent_id": "DOC-A::parent::4-5", "parent_chunk_indices": [4, 5]},
            ),
            SimpleNamespace(
                document_id="DOC-A", chunk_id="DOC-A::parent::6-6",
                location=SimpleNamespace(chunk_index=6),
                metadata={"parent_id": "DOC-A::parent::6-6", "parent_chunk_indices": [6]},
            ),
        ]
        metrics = parent_context_metrics(results, {"DOC-A::chunk::4", "DOC-A::chunk::6"})
        self.assertEqual(metrics["context_precision@3"], 2 / 3)
        self.assertEqual(metrics["context_recall@3"], 1.0)
        self.assertEqual(metrics["context_mrr"], 0.5)
        self.assertEqual(metrics["gold_passage_coverage_recall@1"], 0.0)
        self.assertEqual(metrics["gold_passage_coverage_recall@3"], 1.0)


if __name__ == "__main__":
    unittest.main()
