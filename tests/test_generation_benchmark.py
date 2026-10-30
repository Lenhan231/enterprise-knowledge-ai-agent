import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.run_generation_benchmark import load_gold_evidence, model_keys, render_retrieval_markdown, required_sources, retrieval_metrics, score_human_reviews, serialize_contexts, summarize_run, verify_sources


class GenerationBenchmarkTest(unittest.TestCase):
    def test_two_groq_models_use_distinct_keys(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "first", "GROQ_API_KEY_2": "second"}):
            keys = model_keys(["gpt_oss_20b", "qwen3"])
        self.assertEqual(keys, {"gpt_oss_20b": "first", "qwen3": "second"})

        with patch.dict(os.environ, {"GROQ_API_KEY": "same", "GROQ_API_KEY_2": "same"}):
            with self.assertRaisesRegex(ValueError, "distinct"):
                model_keys(["gpt_oss_20b", "qwen3"])

    def test_retrieval_metrics_use_gold_chunks_not_any_chunk_from_same_document(self):
        contexts = [
            {"chunk_id": "other::chunk::0", "rank": 1},
            {"chunk_id": "annual::chunk::9", "rank": 2},
            {"chunk_id": "annual::chunk::4", "rank": 3},
            {"chunk_id": "audit::chunk::8", "rank": 4},
        ]
        metrics = retrieval_metrics(contexts, {"annual::chunk::4", "audit::chunk::8"})
        self.assertEqual(metrics["recall_at_k"], 1.0)
        self.assertEqual(metrics["precision_at_k"], 0.5)
        self.assertEqual(metrics["mrr"], round(1 / 3, 4))
        self.assertGreater(metrics["ndcg_at_k"], 0.0)
        self.assertLess(metrics["ndcg_at_k"], 1.0)

    def test_context_export_preserves_full_content_and_rank(self):
        class Chunk:
            rank = 2
            chunk_id = "D::chunk::3"
            document_id = "D"
            source = "document.pdf"
            score = 0.7
            text = "full\nretrieved text"
            location = type("Location", (), {"chunk_index": 3, "page_number": 8, "section_title": "Results"})()

        rows = serialize_contexts([Chunk()])
        self.assertEqual(rows[0]["source_id"], "S1")
        self.assertEqual(rows[0]["rank"], 2)
        self.assertEqual(rows[0]["content"], "full\nretrieved text")
        self.assertEqual(rows[0]["page_number"], 8)

    def test_selected_questions_require_only_their_actual_sources(self):
        cases = [{"id": "Q13", "expected_sources": ["long_hau_fs"]}]
        self.assertEqual(required_sources(cases, {"annual_report": None, "long_hau_fs": "FS"}), {"long_hau_fs": "FS"})
        with self.assertRaisesRegex(ValueError, "annual_report"):
            required_sources([{"id": "Q23", "expected_sources": ["annual_report", "long_hau_fs"]}],
                             {"annual_report": None, "long_hau_fs": "FS"})

    def test_source_identity_uses_chunk_text_not_misleading_title(self):
        repository = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("HPT audit proposal",)
        cursor.fetchall.return_value = [("HPT audit proposal",)]
        with self.assertRaisesRegex(ValueError, "does not mention LONG HAU"):
            verify_sources(repository, {"long_hau_fs": "misnamed"})

        cursor.fetchone.return_value = ("AnnualReport 2008",)
        with self.assertRaisesRegex(ValueError, "PVFCCo"):
            verify_sources(repository, {"annual_report": "wrong-company-report"})

    def test_review_markdown_shows_rank_source_page_and_full_text(self):
        report = {"results": [{"id": "Q01", "question": "Company?", "gold_evidence": [{
            "chunk_id": "D::chunk::4", "document_name": "source.pdf", "chunk_index": 4,
            "page_number": 3, "content": "gold line",
        }], "retrieved_contexts": [{
            "source_id": "S1", "rank": 1, "document_id": "D", "document_name": "source.pdf",
            "chunk_id": "D::chunk::4", "page_number": 3, "similarity_score": 0.8, "content": "first line\nsecond line",
        }]}]}
        markdown = render_retrieval_markdown(report)
        self.assertIn("Q01", markdown)
        self.assertIn("source.pdf", markdown)
        self.assertIn("page 3", markdown)
        self.assertIn("gold line", markdown)
        self.assertIn("Retrieved: True", markdown)
        self.assertIn("    first line\n    second line", markdown)

    def test_gold_evidence_checks_index_and_page(self):
        repository = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("source.pdf", "gold text", "5")
        case = {"id": "Q01", "expected_sources": ["annual_report"],
                "evidence": [{"source": "annual_report", "chunk_index": 4, "page_number": 5}]}
        rows = load_gold_evidence(repository, case, {"annual_report": "D"})
        self.assertEqual(rows[0]["chunk_id"], "D::chunk::4")
        self.assertEqual(rows[0]["content"], "gold text")
        cursor.fetchone.return_value = ("source.pdf", "gold text", "6")
        with self.assertRaisesRegex(ValueError, "page mismatch"):
            load_gold_evidence(repository, case, {"annual_report": "D"})

    def test_manual_scores_are_aggregated_per_model(self):
        report = {"model_names": ["gpt_oss_20b"], "results": [{"models": {"gpt_oss_20b": {
            "human_reviews": [{"reviewer": "R1", "faithfulness": 4, "answer_relevancy": 5,
                               "context_precision": 3, "factual_claim_count": 4,
                               "hallucinated_claim_count": 1}],
        }}}]}
        scored = score_human_reviews(report)
        self.assertEqual(scored["gpt_oss_20b"]["mean_faithfulness"], 4.0)
        self.assertEqual(scored["gpt_oss_20b"]["hallucination_rate"], 0.25)

    def test_run_summary_keeps_latency_and_throughput_distinct(self):
        report = {"model_names": ["gpt_oss_20b"], "results": [{
            "retrieval_latency_ms": 100, "retrieval_metrics": {"recall_at_k": 1.0},
            "models": {"gpt_oss_20b": {"generation_latency_ms": 400}},
        }]}
        summary = summarize_run(report, elapsed_seconds=2)
        self.assertEqual(summary["average_retrieval_latency_ms"], 100)
        self.assertEqual(summary["average_response_time_ms"], 500)
        self.assertEqual(summary["observed_throughput_requests_per_second"], 0.5)
        self.assertEqual(summary["retrieval_metrics_mean"]["recall_at_k"], 1.0)


if __name__ == "__main__":
    unittest.main()
