import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
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


    def test_minute_limit_waits_and_retries_day_limit_stops_and_retry_errors_reruns(self):
        class RateLimitError(Exception):
            def __init__(self, message):
                super().__init__(message)
                self.response = type("R", (), {"headers": {"retry-after": "2"}})()

        class Limited(FakeRunner):
            errors = []

            def run(self, case, roles):
                if Limited.errors:
                    raise Limited.errors.pop(0)
                return super().run(case, roles)

        cases = {"dataset_id": "d", "status": "s", "cases": [{"id": "L01", "type": "lookup", "question": "q"},
                                                                {"id": "L02", "type": "lookup", "question": "q"}]}
        with tempfile.TemporaryDirectory() as folder:
            path, out = Path(folder, "q.json"), Path(folder, "B0.json")
            path.write_text(json.dumps(cases))
            argv = ["x", "--arm", "B0", "--cases", str(path), "--output", str(out)]
            Limited.errors, FakeRunner.calls = [RateLimitError("tokens per minute")], []
            with mock.patch.object(arm, "InProcess", Limited), mock.patch.object(sys, "argv", argv), \
                    mock.patch("builtins.print"), mock.patch.object(arm.time, "sleep") as slept:
                arm.main()
            self.assertEqual(slept.call_args[0][0], 3.0)
            self.assertEqual([c[0] for c in FakeRunner.calls], ["L01", "L02"])
            rows = json.loads(out.read_text())["results"]
            self.assertEqual(rows[1]["error_type"], "ValueError")  # L02 fails in FakeRunner
            Limited.errors, FakeRunner.calls = [RateLimitError("tokens per day") for _ in range(6)], []
            with mock.patch.object(arm, "InProcess", Limited), mock.patch.object(sys, "argv", [*argv, "--resume", "--retry-errors"]), \
                    mock.patch("builtins.print"), mock.patch.object(arm.time, "sleep"), self.assertRaises(SystemExit):
                arm.main()
            self.assertEqual(Limited.errors, [])  # L02 (the error row) was attempted again, L01 was not
            self.assertEqual(json.loads(out.read_text())["results"], rows)  # stopping never rewrites the file


    def test_only_unrouted_router_failures_are_retried(self):
        self.assertTrue(arm.failed_row({"metadata": {"status": "failed", "selected_route": "unrouted"}}))
        self.assertFalse(arm.failed_row({"metadata": {"status": "failed", "selected_route": "knowledge"}}))  # grounded refusal
        self.assertTrue(arm.failed_row({"error_type": "ValueError"}))


    def test_five_failures_in_a_row_stop_the_arm_after_saving(self):
        class AlwaysFails(FakeRunner):
            def run(self, case, roles):
                raise ValueError("503")

        cases = {"dataset_id": "d", "status": "s", "cases": [{"id": f"L{i:02}", "type": "lookup", "question": "q"}
                                                                for i in range(1, 9)]}
        with tempfile.TemporaryDirectory() as folder:
            path, out = Path(folder, "q.json"), Path(folder, "B4.json")
            path.write_text(json.dumps(cases))
            with mock.patch.object(arm, "InProcess", AlwaysFails), mock.patch.object(sys, "argv", ["x", "--arm", "B4", "--cases", str(path),
                    "--output", str(out)]), mock.patch("builtins.print"), self.assertRaises(SystemExit):
                arm.main()
            self.assertEqual(len(json.loads(out.read_text())["results"]), 5)

    def test_http_logs_in_again_when_the_session_expires(self):
        class Response:
            def __init__(self, status, body=None, token=None):
                self.status_code, self._body, self.cookies = status, body or {}, {"enterprise_session": token} if token else {}

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(self.status_code)

            def json(self):
                return self._body

        class Client:
            def __init__(self, **_):
                self.headers, self.chat = {}, [Response(401), Response(200, {"answer": "ok", "metadata": {}})]
                self.logins = 0

            def post(self, url, json):
                if url.endswith("login"):
                    self.logins += 1
                    return Response(200, token=f"t{self.logins}")
                return self.chat.pop(0)

        fake = type(sys)("httpx")
        fake.Client = Client
        env = {"DEMO_VIEWER_USERNAME": "u", "DEMO_VIEWER_PASSWORD": "p"}
        with mock.patch.dict(sys.modules, {"httpx": fake}), mock.patch.dict(arm.os.environ, env):
            runner = arm.Http(type("A", (), {"base_url": "http://x", "role": "employee"}), "knowledge")
            self.assertEqual(runner.run({"id": "L01", "question": "q"}, ["employee"])["answer"], "ok")
        self.assertEqual((runner.client.logins, runner.client.headers["Authorization"]), (2, "Bearer t2"))


if __name__ == "__main__":
    unittest.main()
