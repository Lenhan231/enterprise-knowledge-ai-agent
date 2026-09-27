import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_review1_grounded_qa import case_passed, citation_metrics, missing_expected_facts
from score_qa_artifact import summarize_human_reviews


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
