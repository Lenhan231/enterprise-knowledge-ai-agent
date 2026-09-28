import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_agent_routes import prepare_output_path, score_routes


class AgentRouteEvaluationTest(unittest.TestCase):
    def test_output_path_preflight_creates_parent_and_checks_writability(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "nested" / "report.json"
            self.assertEqual(prepare_output_path(output), output)
            self.assertTrue(output.parent.is_dir())
            self.assertFalse(output.exists())

    def test_output_path_preflight_rejects_a_directory_as_target(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "report.json"
            target.mkdir()
            with self.assertRaises(OSError):
                prepare_output_path(target)

    def test_output_path_preflight_checks_space_when_target_already_exists(self):
        from unittest.mock import Mock, patch

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "report.json"
            target.touch()
            probe = Mock()
            probe.__enter__ = Mock(return_value=probe)
            probe.__exit__ = Mock(return_value=False)
            probe.write.side_effect = OSError("disk quota exceeded")
            with patch("evaluate_agent_routes.tempfile.NamedTemporaryFile", return_value=probe):
                with self.assertRaisesRegex(OSError, "disk quota exceeded"):
                    prepare_output_path(target)

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
