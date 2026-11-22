import asyncio
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[1]
V31 = PACKAGE_ROOT / "40-case-v3-1"
sys.path[:0] = [str(REPO_ROOT / "src"), str(PACKAGE_ROOT)]
spec = importlib.util.spec_from_file_location("sql_benchmark_runner_v33", PACKAGE_ROOT / "runner.py")
RUNNER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RUNNER)


class RunnerV33Tests(unittest.TestCase):
    def _input_files(self, directory):
        cases = json.loads((V31 / "cases_v3_1_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((V31 / "gold_sql_v3_1_draft.json").read_text(encoding="utf-8"))
        reference = json.loads((V31 / "gold_results_v3_1_provisional.json").read_text(encoding="utf-8"))
        cases_path, gold_path = Path(directory) / "cases.json", Path(directory) / "gold.json"
        reference_path, scorer_path = Path(directory) / "reference.json", Path(directory) / "scorer.py"
        cases_path.write_text(json.dumps(cases), encoding="utf-8")
        gold_path.write_text(json.dumps(gold), encoding="utf-8")
        reference_path.write_text(json.dumps(reference), encoding="utf-8")
        shutil.copyfile(V31 / "scorer_v3_1.py", scorer_path)
        manifest = {
            "freeze_status": "FROZEN",
            "database_fingerprint_sha256": reference["database_fingerprint_sha256"],
            "case_set_sha256": RUNNER._canonical_hash(cases),
            "gold_sql_definition_sha256": RUNNER._canonical_hash([
                {"id": item["id"], "sql": item["sql"], "parameters": item["parameters"]}
                for item in gold["cases"]
            ]),
            "artifacts_sha256": {
                name: RUNNER.sha256_file(path) for name, path in (
                    ("cases_v3_1_draft.json", cases_path),
                    ("gold_sql_v3_1_draft.json", gold_path),
                    ("gold_results_v3_1_provisional.json", reference_path),
                    ("scorer_v3_1.py", scorer_path),
                )
            },
        }
        return cases, gold, reference, cases_path, gold_path, reference_path, scorer_path, manifest

    def test_frozen_cohort_and_gold_hashes_validate_without_database_access(self):
        with tempfile.TemporaryDirectory() as directory:
            cases, _gold, reference, cases_path, gold_path, reference_path, scorer_path, manifest = (
                self._input_files(directory)
            )
            result = RUNNER.validate_v31_contract(
                cases, reference, manifest, cases_path=cases_path,
                gold_sql_path=gold_path, reference_path=reference_path, scorer_path=scorer_path,
            )
        self.assertEqual(result["distribution"], {
            "execute": 30, "clarify": 5, "abstain_without_query": 5,
        })

    def test_changed_case_hash_or_database_fingerprint_stops_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            cases, _gold, reference, cases_path, gold_path, reference_path, scorer_path, manifest = (
                self._input_files(directory)
            )
            with self.assertRaisesRegex(ValueError, "canonical hash"):
                RUNNER.validate_v31_contract(
                    cases, reference, dict(manifest, case_set_sha256="0" * 64),
                    cases_path=cases_path, gold_sql_path=gold_path,
                    reference_path=reference_path, scorer_path=scorer_path,
                )
            with self.assertRaisesRegex(ValueError, "database fingerprint"):
                RUNNER.validate_v31_contract(
                    cases, dict(reference, database_fingerprint_sha256="0" * 64), manifest,
                    cases_path=cases_path, gold_sql_path=gold_path,
                    reference_path=reference_path, scorer_path=scorer_path,
                )

    def test_score_only_reads_saved_run_and_does_not_connect_or_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            run_dir.mkdir()
            cases_path, reference_path, scorer_path = root / "cases.json", root / "reference.json", root / "scorer.py"
            cases = {"cases": [{"id": "B40-001", "expected_behavior": "execute"}]}
            reference = {"database_fingerprint_sha256": "frozen-db", "cases": [{"id": "B40-001", "rows": []}]}
            cases_path.write_text(json.dumps(cases), encoding="utf-8")
            reference_path.write_text(json.dumps(reference), encoding="utf-8")
            scorer_path.write_text("# fixture\n", encoding="utf-8")
            data = {
                "case_set_sha256": RUNNER._canonical_hash(cases),
                "manifest": {"dataset_fingerprint_sha256": "frozen-db"},
                "cases": [{"id": "B40-001", "status": "executed", "sql": "SELECT 1", "rows": []}],
            }
            (run_dir / "data.json").write_text(json.dumps(data), encoding="utf-8")
            audits_path = root / "audits.json"
            audits_path.write_text(json.dumps([{"case_id": "B40-001", "decision": "PASS"}]), encoding="utf-8")

            class Scorer:
                SCORER_VERSION = "3.3.0"
                PROTOCOL_VERSION = "3.3.0"

                def score(self, case_doc, reference_doc, experiment):
                    self.experiment = experiment
                    return {"scorer_version": self.SCORER_VERSION,
                            "protocol_version": self.PROTOCOL_VERSION, "metrics": {}}

            scorer = Scorer()
            with patch.object(RUNNER, "_load_scorer", return_value=scorer), patch.object(
                RUNNER, "benchmark_repository", side_effect=AssertionError("score-only must not connect")
            ):
                scores, report = RUNNER.score_saved_run(
                    cases_path=cases_path, reference_path=reference_path, run_dir=run_dir,
                    scorer_path=scorer_path, semantic_audit_path=audits_path,
                )
            self.assertEqual(scorer.experiment["independent_semantic_audits"][0]["case_id"], "B40-001")
            self.assertEqual(scores["scoring_input_hashes"]["raw_observations_sha256"],
                             RUNNER.sha256_file(run_dir / "data.json"))
            self.assertTrue(report.is_file())
            with self.assertRaises(FileExistsError):
                RUNNER.score_saved_run(
                    cases_path=cases_path, reference_path=reference_path, run_dir=run_dir,
                    scorer_path=scorer_path,
                )

    def test_provider_fallback_records_model_usage(self):
        from core.agents.sql import agent as sql_module

        class Provider:
            def __init__(self, name):
                self.model_name = f"model-{name}"
                self.last_usage = None

        primary, secondary = Provider("primary"), Provider("secondary")

        async def generate(provider, _prompt, *, timeout=15, max_output_tokens=None):
            if provider is primary:
                raise RuntimeError("primary unavailable")
            provider.last_usage = {"input_tokens": 11, "output_tokens": 5, "total_tokens": 16}
            return "fallback SQL"

        class Agent:
            async def _generate_sql(self, prompt):
                try:
                    return await sql_module.generate(primary, prompt, timeout=75)
                except RuntimeError:
                    return await sql_module.generate(secondary, prompt, timeout=75)

        instrumentation = RUNNER.Instrumentation()
        agent = Agent()
        with patch.object(sql_module, "generate", new=generate):
            restore = RUNNER.instrument_agent(agent, instrumentation)
            try:
                self.assertEqual(asyncio.run(agent._generate_sql("query")), "fallback SQL")
            finally:
                restore()
        self.assertEqual([item["status"] for item in instrumentation.provider_calls], ["failed", "completed"])
        self.assertEqual(instrumentation.provider_calls[1]["model"], "model-secondary")
        self.assertEqual(instrumentation.provider_calls[1]["usage"]["total_tokens"], 16)


if __name__ == "__main__":
    unittest.main()
