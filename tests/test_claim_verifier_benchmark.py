import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.rag.claim_verification import VerificationOutcome

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verifier_benchmark", ROOT / "scripts/agents/benchmark_knowledge_verifier.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class VerifierBenchmarkTest(unittest.TestCase):
    def test_fixed_cases_flushed_with_provenance_and_unavailable_is_not_correct(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "diagnostic.jsonl"
            llm = Mock(model_name="test-model", last_usage=None)
            llm._last_rate_error = None
            with patch.object(benchmark, "AuditRecorder", return_value=llm), \
                 patch.object(benchmark, "verify_answer", side_effect=[
                     VerificationOutcome(status="supported", reason="all_claims_supported", claim_count=1),
                     VerificationOutcome(status="unavailable", reason="RateLimitError")]) as verify, \
                 patch.object(benchmark.time, "sleep"), patch("builtins.print"), \
                 patch("sys.argv", ["benchmark", "--limit", "2", "--output", str(output)]):
                self.assertEqual(benchmark.main(), 1)
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(rows[0]["model"], "test-model")
            self.assertEqual(len(rows[0]["prompt_sha256"]), 64)
            self.assertEqual(rows[-1]["summary"]["unsupported_rejected"], 0)
            self.assertEqual(rows[-1]["summary"]["unavailable"], 1)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual([c["source_id"] for c in verify.call_args.args[3]], ["S1"])
            llm.close.assert_called_once()

    def test_quota_details_are_safe_and_distinguish_minute_from_day(self):
        for kind in ("TPM", "TPD", "RPM", "RPD"):
            provider = Mock()
            provider._last_rate_error.body = {"message": (
                f"Rate limit reached in organization org_PRIVATE on tokens ({kind}): "
                "Limit 200000, Used 199146, Requested 1789. secret gsk_PRIVATE")}
            provider._last_rate_error.response.headers = {"retry-after": "404"}
            result = benchmark.rate_limit_details(provider)
            self.assertEqual(result, {"kind": kind, "retry_after": "404", "limit": "200000",
                                      "used": "199146", "requested": "1789"})
            self.assertNotIn("PRIVATE", json.dumps(result))
        provider._last_rate_error.body = {"error": {"message": "TPM: Limit 8000, Used 7900, Requested 3500."}}
        self.assertEqual(benchmark.rate_limit_details(provider)["kind"], "TPM")

    def test_explicit_key_selection_is_process_local_and_not_written_to_report(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "selected.jsonl"
            llm = Mock(model_name="test-model", last_usage=None)
            with patch.dict(os.environ, {"GROQ_API_KEY_2": "fake-secret"}), \
                 patch.object(benchmark, "AuditRecorder", return_value=llm) as factory, \
                 patch.object(benchmark, "verify_answer", return_value=VerificationOutcome(
                     status="supported", reason="all_claims_supported", claim_count=1)), \
                 patch.object(benchmark.time, "sleep"), patch("builtins.print"), \
                 patch("sys.argv", ["benchmark", "--limit", "1", "--api-key-env", "GROQ_API_KEY_2",
                                    "--output", str(output)]):
                self.assertEqual(benchmark.main(), 0)
                factory.assert_called_once_with(api_keys=["fake-secret"])
                self.assertEqual(os.environ["GROQ_API_KEY_2"], "fake-secret")
            self.assertNotIn("fake-secret", output.read_text())
            self.assertEqual(json.loads(output.read_text().splitlines()[0])["api_key_env"], "GROQ_API_KEY_2")

    def test_key_selector_rejects_unrelated_or_empty_env_before_creating_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            for key_name, env in (("OTHER_SECRET", {"OTHER_SECRET": "fake-secret"}),
                                  ("GROQ_API_KEY_2", {"GROQ_API_KEY_2": ""})):
                with patch.dict(os.environ, env), patch.object(benchmark, "AuditRecorder") as factory, \
                     patch("sys.argv", ["benchmark", "--api-key-env", key_name,
                                        "--output", str(Path(folder) / "unused.jsonl")]), \
                     patch("sys.stderr"):
                    with self.assertRaises(SystemExit) as error:
                        benchmark.main()
                    self.assertEqual(error.exception.code, 2)
                    factory.assert_not_called()

    def test_recorder_preserves_raw_return_and_never_retries(self):
        with patch("core.llm.groq_provider.OpenAI"):
            recorder = benchmark.AuditRecorder(api_keys=["fake"])
            try:
                with patch.object(benchmark.GroqProvider, "generate", side_effect=["raw JSON", RuntimeError("failed")]) as generate:
                    self.assertEqual(recorder.generate("audit", max_output_tokens=3072), "raw JSON")
                    self.assertEqual(recorder.audit_raw, "raw JSON")
                    with self.assertRaises(RuntimeError):
                        recorder.generate("next audit")
                    self.assertIsNone(recorder.audit_raw)
                    self.assertEqual(generate.call_count, 2)
            finally:
                recorder.close()

    def test_replay_identifies_quote_coverage_and_schema_errors(self):
        from test_claim_verification import ANSWER, SOURCE, review
        self.assertIsNone(benchmark.validation_error(json.dumps(review()), ANSWER, [SOURCE]))
        self.assertIsNone(benchmark.validation_error("```json\n" + json.dumps(review()) + "\n```", ANSWER, [SOURCE]))
        self.assertEqual(benchmark.validation_error("invalid", ANSWER, [SOURCE]), "invalid_review_schema")
        self.assertEqual(benchmark.validation_error(json.dumps(review()), ANSWER + " Extra claim [S1].", [SOURCE]),
                         "incomplete_claim_coverage")
        self.assertEqual(benchmark.validation_error(json.dumps(review(quote="Invented quote")), ANSWER, [SOURCE]),
                         "fabricated_source_quote")
        self.assertEqual(benchmark.validation_error(json.dumps(review(quote=None)), ANSWER, [SOURCE]),
                         "missing_cited_source_quotes")

    def test_filter_runs_only_requested_cases_and_saves_raw_audit(self):
        from test_claim_verification import ANSWER, review
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "filtered.jsonl"
            llm = Mock(model_name="test-model", last_usage=None)
            wanted = []
            def audit(provider, question, answer, contexts):
                wanted.append(answer)
                provider.audit_raw = json.dumps(review(verdict="contradicted", quote=None))
                return VerificationOutcome(status="rejected", reason="contradicted", claim_count=1)
            with patch.object(benchmark, "AuditRecorder", return_value=llm), \
                 patch.object(benchmark, "verify_answer", side_effect=audit), \
                 patch.object(benchmark.time, "sleep"), patch("builtins.print") as printed, \
                 patch("sys.argv", ["benchmark", "--case-ids", "F02", "F03", "--output", str(output)]):
                self.assertEqual(benchmark.main(), 0)
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(rows[0]["case_ids"], ["F02", "F03"])
            self.assertEqual(len(wanted), 2)
            self.assertIn("audit_raw", rows[1])
            self.assertIsNone(rows[1]["validation_error"])
            self.assertNotIn("audit_raw", printed.call_args_list[0].args[0])

    def test_unknown_case_id_stops_before_provider_creation(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(benchmark, "AuditRecorder") as factory, patch("sys.stderr"), \
             patch("sys.argv", ["benchmark", "--case-ids", "NOT_A_CASE",
                                "--output", str(Path(folder) / "unused.jsonl")]):
            with self.assertRaises(SystemExit) as error:
                benchmark.main()
            self.assertEqual(error.exception.code, 2)
            factory.assert_not_called()

    def test_script_copied_directly_to_tmp_can_start(self):
        script = ROOT / "scripts/agents/benchmark_knowledge_verifier.py"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", dir="/tmp") as copied:
            copied.write(script.read_text())
            copied.flush()
            result = subprocess.run(
                [sys.executable, copied.name, "--help"], cwd="/tmp",
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                capture_output=True, text=True, timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--cases", result.stdout)

    def test_all_fixture_labels_and_citations_are_explicit(self):
        dataset = json.loads((ROOT / "data/evaluation/knowledge_claim_verification_cases.json").read_text())
        self.assertEqual(len({c["id"] for c in dataset["cases"]}), len(dataset["cases"]))
        for c in dataset["cases"]:
            self.assertIn(c["expected"], {"supported", "rejected"})
            self.assertIn(c["context"], dataset["contexts"])
            self.assertRegex(c["answer"], r"\[S\d+\]")
