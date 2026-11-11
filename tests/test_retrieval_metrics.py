from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.evaluation.retrieval_metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank


class RetrievalMetricsTest(unittest.TestCase):
    def test_ranking_metrics_for_one_relevant_document(self):
        relevant = {"report"}
        ranked = ["policy", "report", "product"]
        self.assertAlmostEqual(precision_at_k(relevant, ranked, 3), 1 / 3)
        self.assertEqual(recall_at_k(relevant, ranked, 3), 1.0)
        self.assertEqual(reciprocal_rank(relevant, ranked), 0.5)
        self.assertAlmostEqual(ndcg_at_k(relevant, ranked, 3), 1 / 1.584962500721156)

    def test_metrics_validate_k(self):
        with self.assertRaises(ValueError):
            precision_at_k({"doc"}, ["doc"], 0)


if __name__ == "__main__":
    unittest.main()
