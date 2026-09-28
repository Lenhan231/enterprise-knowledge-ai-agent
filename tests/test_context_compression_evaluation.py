import unittest

from scripts.evaluate_context_compression import compress_extractively, _fact_groups_present, _fact_coverage


class ContextCompressionEvaluationTests(unittest.TestCase):
    def test_keeps_relevant_source_sentence_verbatim_and_reduces_context(self):
        source = (
            "The factory opened in 1998. The 2024 report states revenue was 61,824 billion VND. "
            "A different section discusses packaging design."
        )
        compressed = compress_extractively("What was revenue in 2024?", source, 0.8)

        self.assertIn("The 2024 report states revenue was 61,824 billion VND.", compressed)
        self.assertNotIn("packaging design", compressed)
        self.assertLess(len(compressed), len(source))

    def test_keeps_all_evidence_when_query_has_no_sentence_match(self):
        source = "Vinamilk publishes annual reports. The document contains audited financial statements."
        self.assertEqual(compress_extractively("What is the moon made of?", source), source)

    def test_fact_phrase_matching_accepts_separator_variants(self):
        self.assertEqual(_fact_groups_present([["59 723 billion VND"]], "Revenue: 59,723 billion VND."), [True])

    def test_baseline_misses_are_not_reported_as_expected_fact_coverage(self):
        coverage = _fact_coverage([["expected value"]], "different source value", "different source value")

        self.assertTrue(coverage["baseline_unchanged"])
        self.assertFalse(coverage["all_expected_present_before"])
        self.assertFalse(coverage["all_expected_present_after"])

    def test_rejects_invalid_target_ratio(self):
        with self.assertRaises(ValueError):
            compress_extractively("question", "A. B.", 1)


if __name__ == "__main__":
    unittest.main()
