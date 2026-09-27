import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_agent_routes import score_routes


class AgentRouteEvaluationTest(unittest.TestCase):
    def test_confusion_metrics_cover_expected_and_predicted_routes(self):
        metrics = score_routes([
            {"expected_route": "knowledge", "actual_route": "knowledge"},
            {"expected_route": "hybrid", "actual_route": "knowledge"},
            {"expected_route": "report", "actual_route": "report"},
        ])

        self.assertEqual(metrics["case_count"], 3)
        self.assertEqual(metrics["correct"], 2)
        self.assertEqual(metrics["accuracy"], 0.6667)
        self.assertEqual(metrics["confusion_matrix"]["hybrid"]["knowledge"], 1)
        self.assertEqual(metrics["per_route"]["knowledge"]["precision"], 0.5)
        self.assertEqual(metrics["per_route"]["hybrid"]["recall"], 0.0)
        self.assertIsNone(metrics["per_route"]["dashboard"]["recall"])

    def test_unknown_route_label_fails_instead_of_silently_scoring(self):
        with self.assertRaisesRegex(ValueError, "Unknown route"):
            score_routes([{"expected_route": "sql", "actual_route": "analytics"}])


if __name__ == "__main__":
    unittest.main()
