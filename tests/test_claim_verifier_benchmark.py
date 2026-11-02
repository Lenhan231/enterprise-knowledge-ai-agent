import importlib.util
import json
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
            with patch.object(benchmark, "GroqProvider", return_value=llm), \
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

    def test_all_fixture_labels_and_citations_are_explicit(self):
        dataset = json.loads((ROOT / "data/evaluation/knowledge_claim_verification_cases.json").read_text())
        self.assertEqual(len({c["id"] for c in dataset["cases"]}), len(dataset["cases"]))
        for c in dataset["cases"]:
            self.assertIn(c["expected"], {"supported", "rejected"})
            self.assertIn(c["context"], dataset["contexts"])
            self.assertRegex(c["answer"], r"\[S\d+\]")
