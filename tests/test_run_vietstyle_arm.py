import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
spec = importlib.util.spec_from_file_location("run_vietstyle_arm", ROOT / "scripts/agents/run_vietstyle_arm.py")
arm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arm)


class FakeRunner:
    calls = []

    def __init__(self, *args):
        pass

    def run(self, case, roles):
        FakeRunner.calls.append((case["id"], roles))
        if case["id"] == "L02":
            raise ValueError("Generated answer contains no source citations")
        return {"answer": "ok"}

    def close(self):
        pass


class RunVietstyleArmTest(unittest.TestCase):
    def test_generation_without_verifier_and_unsupported_verified_arm(self):
        runner = arm.InProcess.__new__(arm.InProcess)
        runner.arm = arm.ARMS["B4"]
        result = type("Result", (), dict(answer="ok", contexts=[], source_ids=[],
                                         insufficient_context=False, prompt_sha256="hash"))()

        class Rag:
            def generate_answer(self, question, roles, retrieval_method):
                return result

        runner.rag = Rag()
        self.assertIsNone(runner._run({"question": "q"}, ["employee"])["verification"])
        runner.arm = arm.ARMS["B2"]
        with self.assertRaisesRegex(SystemExit, "does not support claim verification"):
            runner._run({"question": "q"}, ["employee"])

    def run_main(self, *argv):
        with mock.patch.object(arm, "InProcess", FakeRunner), mock.patch.object(sys, "argv", ["x", *argv]), \
                mock.patch("builtins.print"):
            arm.main()

    def test_skips_errors_resume_and_no_overwrite(self):
        cases = {"dataset_id": "d", "status": "s", "cases": [
            {"id": "L01", "type": "lookup", "question": "q"},
            {"id": "L02", "type": "lookup", "question": "q"},
            {"id": "F01", "type": "follow_up", "question": "q", "history": ["h"]},
            {"id": "R01", "type": "rbac", "question": "q", "role": "NO_ACCESS_ROLE"}]}
        with tempfile.TemporaryDirectory() as folder:
            path, out = Path(folder, "q.json"), Path(folder, "runs/B4.json")
            path.write_text(json.dumps(cases))
            FakeRunner.calls = []
            self.run_main("--arm", "B4", "--cases", str(path), "--output", str(out), "--only", "L01,F01,R01")
            rows = {row["id"]: row for row in json.loads(out.read_text())["results"]}
            self.assertEqual(rows["F01"]["skipped"], "multi_turn_needs_router")
            self.assertEqual(rows["R01"]["skipped"], "rbac_role_not_set")
            self.assertEqual(FakeRunner.calls, [("L01", ["employee"])])
            with self.assertRaises(SystemExit):
                self.run_main("--arm", "B4", "--cases", str(path), "--output", str(out))
            self.run_main("--arm", "B4", "--cases", str(path), "--output", str(out), "--resume")
            rows = json.loads(out.read_text())["results"]
            self.assertEqual([row["id"] for row in rows], ["L01", "F01", "R01", "L02"])
            self.assertEqual(rows[-1]["error_type"], "ValueError")
            self.assertEqual(FakeRunner.calls, [("L01", ["employee"]), ("L02", ["employee"])])
            with self.assertRaises(SystemExit):
                self.run_main("--arm", "B2", "--cases", str(path), "--output", str(out), "--resume")


if __name__ == "__main__":
    unittest.main()
