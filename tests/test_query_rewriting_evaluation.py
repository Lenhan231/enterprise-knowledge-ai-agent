import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_query_rewriting import expand_metric_labels


class QueryRewritingEvaluationTest(unittest.TestCase):
    def test_expands_vietnamese_financial_metric_to_canonical_english_labels(self):
        question = "Doanh thu thuần và lợi nhuận sau thuế năm 2024 là bao nhiêu?"
        rewritten = expand_metric_labels(question)

        self.assertEqual(
            rewritten,
            question + " Net revenue; Profit after tax",
        )

    def test_does_not_repeat_metric_label_already_present(self):
        question = "What was net revenue and profit after tax in 2024?"

        self.assertEqual(expand_metric_labels(question), question)

    def test_leaves_non_metric_queries_unchanged(self):
        question = "Which factories publish greenhouse gas inventories?"

        self.assertEqual(expand_metric_labels(question), question)


if __name__ == "__main__":
    unittest.main()
