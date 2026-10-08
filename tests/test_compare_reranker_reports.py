import sys
import json
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.retrieval.compare_reranker_reports import compare_reports


def report(model, reranked_mrr, candidate_hash="candidate-hash"):
    metric = {"mrr": reranked_mrr, "recall@2": 0.5}
    dense = {"mrr": 0.5, "recall@2": 0.5}
    return {
        "model_key": model,
        "model_id": model,
        "model_revision": "rev-1",
        "case_count": 1,
        "case_file_sha256": "case-hash",
        "candidate_sha256": candidate_hash,
        "candidate_k": 30,
        "max_sequence_length": 256,
        "environment": {"device": "cuda", "platform": "Kaggle Linux", "python": "3.12", "peak_rss_mb": 1000},
        "aggregate": {"reranked": {"mrr": reranked_mrr}},
        "passage_aggregate": {"dense": dense, "reranked": metric},
        "timing_seconds": {"mean_rerank": 1.5},
        "results": [{
            "id": "case-a", "role": "employee", "candidate_count": 30,
            "relevant_document_ids": ["doc"], "relevant_passage_ids": ["p1"],
            "dense_ranked_document_ids": ["doc"], "dense_ranked_passage_ids": ["p2", "p1"],
            "dense_metrics": {"mrr": 1.0}, "dense_passage_metrics": dense,
            "reranked_passage_metrics": metric,
        }],
    }


class CompareRerankerReportsTest(unittest.TestCase):
    def test_pair_summarizes_paired_metric_gain_and_source_hashes(self):
        report_a, report_b = report("model-a", 0.25), report("model-b", 0.75)
        with TemporaryDirectory() as directory:
            left_path, right_path = Path(directory) / "a.json", Path(directory) / "b.json"
            left_path.write_text(json.dumps(report_a), encoding="utf-8")
            right_path.write_text(json.dumps(report_b), encoding="utf-8")
            result = compare_reports(report_a, report_b, left_path, right_path, "Tesla T4")

        self.assertEqual(result["paired_passage_metric_deltas"]["mrr"]["right_minus_left_mean"], 0.5)
        self.assertEqual(result["paired_passage_metric_deltas"]["mrr"]["right_wins"], 1)
        self.assertEqual(result["environment"]["device_name"], "Tesla T4")
        self.assertIn("excluded", result["timing_scope"])

    def test_pair_rejects_different_candidates_or_dense_baselines(self):
        with self.assertRaisesRegex(ValueError, "candidate_sha256"):
            compare_reports(report("model-a", 0.25), report("model-b", 0.75, "other"), Path("a"), Path("b"))

        other = report("model-b", 0.75)
        other["results"][0]["dense_ranked_passage_ids"] = ["different"]
        with self.assertRaisesRegex(ValueError, "Dense candidate baseline differs"):
            compare_reports(report("model-a", 0.25), other, Path("a"), Path("b"))


if __name__ == "__main__":
    unittest.main()
