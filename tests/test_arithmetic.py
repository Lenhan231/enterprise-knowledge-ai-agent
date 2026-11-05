import unittest
from core.rag.arithmetic import check_equalities, verified_results


class ExactArithmeticTest(unittest.TestCase):
    def test_supported_operations_and_precedence_use_exact_values(self):
        for text in (
            "90 + 15 = 105", "1. 90 + 15 = 105 [S1].", "90 + 10 = 100", "20 - 3 = 17", "6 * 7 = 42",
            "6 × 7 = 42", "10 ÷ 4 = 2.5", "0.1 + 0.2 = 0.3", "0,1 + 0,2 = 0,3",
            "2 + 3 * 4 = 14", "(2 + 3) * 4 = 20", "-5 + 2 = -3", "5 − 2 = 3",
            "1 / 3 = 2 / 6", "1 + 2 = 3 = 6 / 2", "5.000.001 + 1 = 5.000.002",
            "Không hợp lệ vì 90 + 15 = 105, lớn hơn lượng giao 100 [S1].",
            "Tổng chấp nhận và từ chối (90 + 15 = 105) lớn hơn 100 [S1].", "((2 + 3) * 4 = 20)",
        ):
            with self.subTest(text=text):
                self.assertEqual(check_equalities(text), (1, None))

    def test_generated_integer_equalities_and_mutations(self):
        import operator
        import random
        randomizer = random.Random(20261103)
        for _ in range(200):
            a, b = randomizer.randint(-100, 100), randomizer.randint(-100, 100)
            symbol, operation = randomizer.choice((("+", operator.add), ("-", operator.sub), ("*", operator.mul)))
            result = operation(a, b)
            correct = f"{a} {symbol} {b} = {result}"
            wrong = f"{a} {symbol} {b} = {result + 1}"
            self.assertEqual(check_equalities(correct), (1, None), correct)
            self.assertEqual(check_equalities(wrong)[1], "arithmetic_mismatch", wrong)

    def test_false_equalities_are_rejected_including_chains(self):
        for text in ("90 + 15 = 95", "Hợp lệ vì 90 + 15 = 95, không vượt 100 [S1].", "6 * 7 = 41", "2 + 3 * 4 = 20", "10 / 4 = 3",
                     "(2 + 3) * 4 = 14", "90 + 15 = 105 = 100", "1 / 3 = 0.33", "(90 + 15 = 95)"):
            with self.subTest(text=text):
                self.assertEqual(check_equalities(text)[1], "arithmetic_mismatch")

    def test_more_than_one_equality_and_comma_sentence_separator(self):
        self.assertEqual(check_equalities("1 + 2 = 3, 3 + 4 = 7 [S1]."), (2, None))
        self.assertEqual(check_equalities("1 + 2 = 3; 3 + 4 = 8 [S1]."), (2, "arithmetic_mismatch"))

    def test_plain_values_thresholds_and_assignments_are_not_calculations(self):
        for text in ("Revenue in 2024 = 100 [S1].", "Quantity > 0 [S1].", "Accepted + rejected <= delivered.",
                     "VND 50,000,001-200,000,000 requires approval [S1].", "Profit is 20 billion [S1]."):
            with self.subTest(text=text):
                self.assertEqual(check_equalities(text), (0, None))

    def test_ambiguous_numbers_powers_and_division_by_zero_never_pass_as_checked(self):
        self.assertEqual(check_equalities("1,000 + 1 = 1,001")[1], "unverified_arithmetic")
        self.assertEqual(check_equalities("2 ** 1000000 = 1")[1], "unverified_arithmetic")
        self.assertEqual(check_equalities("2 ^ 3 = 8")[1], "unverified_arithmetic")
        self.assertEqual(check_equalities("Làm tròn: 1 / 3 = 0.33")[1], "unverified_arithmetic")
        self.assertEqual(check_equalities("1 / 0 = 0")[1], "invalid_arithmetic")
        for mixed in ("1.5 × 300.000 = 450.000", ".5 × 2.000 = 1000", "1234.567 + 1.000 = 2234.567"):
            with self.subTest(text=mixed):
                self.assertEqual(check_equalities(mixed)[1], "unverified_arithmetic")

    def test_vietnamese_dot_thousands_are_exact(self):
        for text in ("4 × 300.000 = 1.200.000 VND [S1].", "2.000 × 25.000 = 50.000.000 VND [S1].",
                     "(3 × 200.000 = 600.000)", "12 × 0,5 = 6"):
            with self.subTest(text=text):
                self.assertEqual(check_equalities(text), (1, None))
        self.assertEqual(check_equalities("4 × 300.000 = 1.300.000")[1], "arithmetic_mismatch")
        self.assertEqual(check_equalities("1+" * 120 + "1 = 121")[1], "unverified_arithmetic")


class VerifiedResultsTest(unittest.TestCase):
    def test_only_exactly_checked_results_are_returned(self):
        self.assertEqual(verified_results("Tổng là 3 × 18.000.000 = 54.000.000 VND [S1]."), ["54.000.000"])
        self.assertEqual(verified_results("3 × 18.000.000 = 55.000.000"), [])
        self.assertEqual(verified_results("Ngưỡng 50.000.001 = 50.000.001"), [])


class DevelopmentProbeArithmeticTest(unittest.TestCase):
    def test_new_supported_probes_are_not_blocked_by_exact_arithmetic_guard(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "data/evaluation"
        for filename in ("knowledge_claim_verification_cases.json", "knowledge_verifier_transfer_v2.json",
                         "knowledge_verifier_finance_probe_v2.json"):
            dataset = json.loads((root / filename).read_text())
            for case in dataset["cases"]:
                checked, issue = check_equalities(case["answer"])
                if case["expected"] == "supported":
                    with self.subTest(file=filename, case=case["id"]):
                        self.assertIsNone(issue)
                if case["topic"] == "wrong_arithmetic":
                    self.assertEqual(issue, "arithmetic_mismatch")
