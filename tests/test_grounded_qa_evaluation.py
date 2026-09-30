import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.agents.run_review1_grounded_qa import case_passed, citation_metrics, cited_sources, missing_expected_facts
from scripts.agents.score_qa_artifact import summarize_human_reviews


class GroundedQAEvaluationTest(unittest.TestCase):
    def test_case_requires_expected_source_and_normalized_facts(self):
        case = {
            "expect_insufficient": False,
            "expected_document_id": "VNM-AR-2024-VI",
            "expected_key_facts": ["61 824", "9 453"],
        }
        result = SimpleNamespace(
            insufficient_context=False,
            source_ids=["S1"],
            answer="Revenue was 61\u202f824 and profit was 9\u202f453. [S1]",
        )
        sources = [{"source_id": "S1", "document_id": "VNM-AR-2024-VI"}]

        self.assertEqual(missing_expected_facts(case, result.answer), [])
        self.assertEqual(case_passed(case, result, sources), (True, "Answer cites the expected document"))

    def test_case_fails_when_key_fact_is_missing(self):
        case = {
            "expect_insufficient": False,
            "expected_document_id": "VNM-AR-2024-VI",
            "expected_key_facts": ["61 824", "9 453"],
        }
        result = SimpleNamespace(
            insufficient_context=False,
            source_ids=["S1"],
            answer="Revenue was 61 824. [S1]",
        )
        sources = [{"source_id": "S1", "document_id": "VNM-AR-2024-VI"}]

        passed, reason = case_passed(case, result, sources)
        self.assertFalse(passed)
        self.assertIn("9 453", reason)

    def test_numeric_separators_are_format_independent(self):
        case = {"expected_key_facts": ["59 723", "3,0 g", "100%"]}

        self.assertEqual(
            missing_expected_facts(case, "59.723 tỷ, 3.0 g, 100 %"),
            [],
        )

    def test_financial_anchors_require_correct_magnitude_units(self):
        case = {
            "expect_insufficient": False,
            "expected_document_id": "VNM-AR-2024-VI",
            "expected_key_facts": ["61 824", "9 453"],
            "expected_key_fact_groups": [
                ["61 824 tỷ đồng", "61 824 billion VND"],
                ["9 453 tỷ đồng", "9 453 billion VND"],
            ],
        }
        correct = SimpleNamespace(
            insufficient_context=False,
            source_ids=["S1"],
            answer="Doanh thu 61\u202f824 tỷ đồng và lợi nhuận 9\u202f453 tỷ đồng. [S1]",
        )
        wrong_unit = SimpleNamespace(
            insufficient_context=False,
            source_ids=["S1"],
            answer="Doanh thu 61\u202f824 triệu đồng và lợi nhuận 9\u202f453 triệu đồng. [S1]",
        )
        sources = [{"source_id": "S1", "document_id": "VNM-AR-2024-VI"}]

        self.assertEqual(case_passed(case, correct, sources), (True, "Answer cites the expected document"))
        passed, reason = case_passed(case, wrong_unit, sources)
        self.assertFalse(passed)
        self.assertIn("tỷ đồng", reason)

    def test_expected_fact_groups_accept_source_equivalent_wording(self):
        case = {"expected_key_fact_groups": [
            ["100%", "all of its factories and all of its farms"],
            ["factories and farms", "all of its factories and all of its farms"],
        ]}

        self.assertEqual(
            missing_expected_facts(case, "All of its factories and all of its farms."),
            [],
        )
        self.assertEqual(
            missing_expected_facts(case, "All factories have an inventory."),
            [
                "100% or all of its factories and all of its farms",
                "factories and farms or all of its factories and all of its farms",
            ],
        )

    def test_negative_control_requires_refusal_without_sources(self):
        case = {"expect_insufficient": True, "expected_document_id": None}
        result = SimpleNamespace(insufficient_context=True, source_ids=[], answer="Insufficient.")

        self.assertEqual(case_passed(case, result, []), (True, "Correctly refused unsupported question"))

    def test_citation_metrics_use_relevant_document_labels(self):
        case = {"relevant_document_ids": ["D1"]}
        sources = [
            {"source_id": "S1", "document_id": "D1"},
            {"source_id": "S2", "document_id": "D2"},
        ]
        metrics = citation_metrics(case, "Claim one. [S1]\nClaim two. [S2]\nUnsupported claim.", sources)
        self.assertEqual(metrics["context_precision_at_cited_sources"], 0.5)
        self.assertAlmostEqual(metrics["citation_covered_line_fraction"], 2 / 3, places=4)
        self.assertEqual(metrics["claim_count"], 3)
        self.assertTrue(metrics["answer_has_valid_citation"])

    def test_expected_facts_must_appear_in_the_cited_source_excerpt(self):
        case = {"expected_key_facts": ["61 824", "9 453"]}
        cited_sources = [{
            "source_id": "S1",
            "document_id": "D1",
            "content_preview": "Consolidated revenue 61.824 billion VND.",
        }]
        metrics = citation_metrics(case, "Revenue 61 824 and profit 9 453. [S1]", cited_sources)

        self.assertEqual(metrics["expected_fact_count"], 2)
        self.assertEqual(metrics["expected_facts_literal_in_cited_evidence"], 1)
        self.assertEqual(metrics["expected_fact_cited_evidence_rate"], 0.5)
        self.assertIn("not semantic entailment", metrics["expected_fact_cited_evidence_definition"])

    def test_expected_fact_in_uncited_source_does_not_count_as_supported(self):
        case = {"expected_key_facts": ["61 824"]}
        sources = [{"source_id": "S1", "content_preview": "Revenue 61.824"}]

        metrics = citation_metrics(case, "Revenue 61 824. [S2]", sources)

        self.assertEqual(metrics["expected_facts_literal_in_cited_evidence"], 0)

    def test_cited_table_evidence_can_separate_a_shared_unit_from_values(self):
        case = {"expected_key_fact_groups": [["61 824 tỷ đồng", "61 824 billion VND"]]}
        sources = [{
            "source_id": "S1",
            "evidence": "Consolidated revenue 2024; net profit 2024; tỷ đồng tỷ đồng 9.453 61.824",
        }]

        metrics = citation_metrics(case, "Revenue 61 824 tỷ đồng. [S1]", sources)

        self.assertEqual(metrics["expected_facts_literal_in_cited_evidence"], 1)
        self.assertEqual(metrics["expected_fact_cited_evidence_rate"], 1.0)

    def test_cited_source_record_keeps_full_evidence_and_bounded_preview(self):
        content = "x" * 700 + " final evidence"
        result = SimpleNamespace(
            source_ids=["S1"],
            contexts=[{
                "source_id": "S1", "content": content, "document_name": "report.pdf",
                "chunk_index": 2, "retrieval_score": 0.8, "retrieval_method": "hybrid",
                "metadata": {"document_id": "D1"},
            }],
        )

        default_source = cited_sources(result)[0]
        source = cited_sources(result, include_full_evidence=True)[0]

        self.assertNotIn("evidence", default_source)
        self.assertEqual(source["evidence"], content)
        self.assertEqual(len(source["content_preview"]), 500)

    def test_missing_fact_in_capped_preview_is_unverifiable_not_unsupported(self):
        case = {"expected_key_facts": ["100%", "factories and farms"]}
        sources = [{"source_id": "S1", "content_preview": "x" * 499 + " "}]

        metrics = citation_metrics(case, "100% of factories and farms. [S1]", sources)

        self.assertEqual(metrics["expected_facts_unverifiable_due_to_truncated_preview"], 2)
        self.assertEqual(metrics["expected_facts_not_supported_by_cited_evidence"], 0)
        self.assertIsNone(metrics["expected_fact_cited_evidence_rate"])

    def test_full_cited_evidence_resolves_a_truncated_preview(self):
        case = {"expected_key_facts": ["100%", "factories and farms"]}
        sources = [{
            "source_id": "S1",
            "evidence": "100% of factories and farms now implement an inventory.",
            "content_preview": "x" * 500,
        }]

        metrics = citation_metrics(case, "100% of factories and farms. [S1]", sources)

        self.assertEqual(metrics["expected_facts_literal_in_cited_evidence"], 2)
        self.assertEqual(metrics["expected_facts_unverifiable_due_to_truncated_preview"], 0)
        self.assertEqual(metrics["expected_fact_cited_evidence_rate"], 1.0)

    def test_citation_metrics_accept_zero_width_and_localized_source_markers(self):
        sources = [{"source_id": "S1", "document_id": "D1"}]
        metrics = citation_metrics(
            {"relevant_document_ids": ["D1"]},
            "Claim [\u200bS1]\nMore evidence [Nguồn: S1].",
            sources,
        )

        self.assertTrue(metrics["answer_has_valid_citation"])
        self.assertEqual(metrics["claims_with_valid_citations"], 2)

    def test_bullets_share_following_sentence_citation_without_label_only_claims(self):
        case = {"relevant_document_ids": ["D1"]}
        sources = [{"source_id": "S1", "document_id": "D1"}]
        metrics = citation_metrics(case, "- Energy: 68.2 kcal\n- Protein: 3.0 g\n- Sugar: 7.3 g【S1】", sources)
        self.assertEqual(metrics["claim_count"], 3)
        self.assertAlmostEqual(metrics["citation_covered_line_fraction"], 1 / 3, places=4)

    def test_correct_abstention_is_not_scored_as_uncited_answer_claim(self):
        metrics = citation_metrics({"relevant_document_ids": []}, "Insufficient information.", [], insufficient_context=True)
        self.assertIsNone(metrics["citation_covered_line_fraction"])
        self.assertEqual(metrics["claim_count"], 0)

    def test_human_review_summary_uses_reviewed_cases_only(self):
        results = [
            {"human_review": {
                "reviewer": "R1", "faithfulness": 4, "answer_relevancy": 5,
                "context_precision": 3, "hallucinated_claim_count": 1,
                "factual_claim_count": 4,
            }},
            {"human_review": {
                "reviewer": None, "faithfulness": None, "answer_relevancy": None,
                "context_precision": None, "hallucinated_claim_count": None,
                "factual_claim_count": None,
            }},
        ]

        summary = summarize_human_reviews(results)
        self.assertEqual(summary["reviewed_case_count"], 1)
        self.assertEqual(summary["mean_faithfulness"], 4.0)
        self.assertEqual(summary["hallucinated_claim_count"], 1)
        self.assertEqual(summary["factual_claim_count"], 4)
        self.assertEqual(summary["hallucination_rate"], 0.25)

    def test_human_review_summary_excludes_invalid_claim_counts(self):
        result = {"human_review": {
            "reviewer": "R1", "faithfulness": 6, "answer_relevancy": 3,
            "context_precision": 2, "hallucinated_claim_count": 3,
            "factual_claim_count": 2,
        }}

        summary = summarize_human_reviews([result])
        self.assertEqual(summary["mean_faithfulness"], None)
        self.assertEqual(summary["claim_review_case_count"], 0)
        self.assertIsNone(summary["hallucination_rate"])


if __name__ == "__main__":
    unittest.main()
