import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluate_api_load.py"
SPEC = importlib.util.spec_from_file_location("evaluate_api_load", SCRIPT)
evaluate_api_load = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate_api_load)


class ApiLoadEvaluationTest(unittest.TestCase):
    def test_percentile_uses_sorted_latency_values(self):
        self.assertEqual(evaluate_api_load.percentile([9, 1, 5], 0.5), 5)
        self.assertEqual(evaluate_api_load.percentile([1, 5, 9], 0.95), 9)

    def test_percentile_handles_empty_samples(self):
        self.assertIsNone(evaluate_api_load.percentile([], 0.95))


if __name__ == "__main__":
    unittest.main()
