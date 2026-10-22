import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/retrieval"))
import evaluate_fresh_retrieval_metrics as runner


class FreshMetricsTest(unittest.TestCase):
    def test_known_ranking_values_and_duplicates(self):
        score = runner.ranking_metrics({"a", "b"}, ["x", "b", "a"])
        self.assertAlmostEqual(score["precision_at_10"], .2)
        self.assertEqual(score["recall_at_10"], 1)
        self.assertEqual(score["mrr_at_10"], .5)
        self.assertAlmostEqual(score["ndcg_at_10"], 0.6934264036172708)
        with self.assertRaises(ValueError):
            runner.ranking_metrics({"a"}, ["a", "a"])
        self.assertEqual(runner.ranking_metrics({"a"}, [])["recall_at_10"], 0)
        self.assertEqual(runner.ranking_metrics({"a"}, [str(i) for i in range(10)] + ["a"])["mrr_at_10"], 0)
        self.assertEqual(runner.ranking_metrics({"a"}, [str(i) for i in range(10)] + ["a"])["mrr_at_10"], 0)

    def test_partial_or_alternative_overlap_is_relevant_not_full_evidence(self):
        scored = {"span_coverage": {"alt1": {"covered_characters": 0}, "alt2": {"covered_characters": 2}},
                  "full_evidence_success": False}
        self.assertTrue(runner.support_relevance(scored))
        scored["span_coverage"]["alt2"]["covered_characters"] = 0
        self.assertFalse(runner.support_relevance(scored))

    def test_clipped_source_coordinates_match_exact_prefix(self):
        row = {"content": "abcdef", "metadata": {"source_spans": [
            {"source_start": 10, "source_end": 16, "chunk_start": 0, "chunk_end": 6}]}}
        clipped = runner.clipped_chunk(row, "abc")
        self.assertEqual(clipped["metadata"]["source_spans"][0]["source_end"], 13)
        self.assertEqual(clipped["metadata"]["source_spans"][0]["chunk_end"], 3)
        self.assertEqual(row["metadata"]["source_spans"][0]["source_end"], 16)
        with self.assertRaises(ValueError):
            runner.clipped_chunk(row, "xyz")

    def test_bootstrap_resamples_intents_not_48_independent_cases(self):
        records = [{"intent_id": str(intent), "methods": {"a": {"metric": 0}, "b": {"metric": float(intent == 0 and direction == 0)}}}
                   for intent in range(12) for direction in range(4)]
        result = runner.cluster_bootstrap(records, "a", "b", "metric", samples=2000)
        self.assertEqual(result["intent_clusters"], 12)
        self.assertAlmostEqual(result["delta"], 1/48)
        self.assertEqual(result["percentile_ci95"][0], 0)

    def test_actual_rag_packing_can_remove_gold_without_calling_llm(self):
        rows = []; sources = {}
        for i, text in enumerate(["x" * 600, "gold"]):
            sources[("DOC", i)] = text
            rows.append({"document_name": "doc.txt", "document_id": "DOC", "chunk_index": i,
                "content": text, "metadata": {"document_id": "DOC", "source_parser_index": i,
                    "source_content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "source_spans": [{"source_start": 0, "source_end": len(text), "chunk_start": 0, "chunk_end": len(text)}]}})
        labels = {"sources": {"vi": []}, "intents": [{"id": "TEST", "requirements": [{"id": "r", "required": True,
            "status": "ready", "evidence_by_language": {"vi": {"alternatives": [{"all_of": ["s"]}]}}}]}],
            "spans": {"s": {"language": "vi", "document_id": "DOC", "source_parser_index": 1,
                "source_content_sha256": hashlib.sha256(b"gold").hexdigest(), "start_char": 0, "end_char": 4, "quote": "gold"}}}
        data = {"rows": rows, "labels": labels, "sources": {"vi": sources}}
        case = {"intent_id": "TEST", "target_language": "vi", "question": "Question?", "allowed_roles": ["admin"]}
        self.assertTrue(runner.evidence(data, case, [runner.chunk(data, i) for i in (0,1)])["full_evidence_success"])
        with patch("core.rag.rag_service.MAX_CONTEXT_CHARS", 200):
            result = runner.context_probe(data, case, [0,1])
        self.assertTrue(result["packing_applied"])
        self.assertFalse(result["full_evidence"])
        self.assertEqual(result["missing_components"], ["r"])


if __name__ == "__main__":
    unittest.main()
