import asyncio
import importlib.util
import json
import sys
import tempfile
import unittest
import inspect
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preflight import PreflightBlocked, collect_preflight
SPEC = importlib.util.spec_from_file_location("sql_agent_business_runner", ROOT / "runner.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
REFERENCE_SPEC = importlib.util.spec_from_file_location(
    "sql_agent_business_reference_runner", ROOT / "reference_runner.py"
)
REFERENCE = importlib.util.module_from_spec(REFERENCE_SPEC)
REFERENCE_SPEC.loader.exec_module(REFERENCE)


def case_set(question="test query"):
    return {"cases": [{"id": "T01", "question": question, "supported": True}]}


class FakeAgent:
    repository = None

    def __init__(self, outcome=None, *, error=None, generation_count=0):
        self.outcome = outcome or {"ok": True, "query_status": "executed", "rows": [{"n": 1}],
                                   "sql": "SELECT 1 AS n LIMIT 1", "parameters": [], "metadata": {}}
        self.error = error
        self.generation_count = generation_count
        self.generation_entries = 0

    async def _generate_sql(self, prompt):
        self.generation_entries += 1
        return "SELECT 1 AS n LIMIT 1"

    async def run_payload(self, _request):
        if self.error:
            raise self.error
        for index in range(self.generation_count):
            await self._generate_sql(f"attempt {index}")
        return self.outcome


class SQLBenchmarkRunnerTest(unittest.TestCase):
    def make_store(self, directory, *, resume=False, cases=None):
        manifest = {"configuration_fingerprint": "stable-test-config", "application_revision": "test"}
        return RUNNER.ExperimentStore(directory, manifest, cases or case_set(), resume=resume)

    def test_valid_sql_execution_is_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory) / "run")
            data = asyncio.run(RUNNER.run_cases(FakeAgent(), case_set(), store))
            self.assertEqual(data["cases"][0]["status"], "executed")
            self.assertEqual(data["cases"][0]["sql"], "SELECT 1 AS n LIMIT 1")

    def test_incorrect_sql_generation_is_preserved_for_scoring(self):
        wrong = {"ok": True, "query_status": "executed", "rows": [],
                 "sql": "SELECT 0 AS n LIMIT 1", "parameters": [], "metadata": {}}
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory) / "run")
            data = asyncio.run(RUNNER.run_cases(FakeAgent(wrong), case_set(), store))
            self.assertEqual(data["cases"][0]["sql"], "SELECT 0 AS n LIMIT 1")

    def test_validator_rejection_retains_sql_and_failure_reason(self):
        blocked = {"ok": False, "sql": "SELECT * FROM commerce.orders LIMIT 1", "parameters": [],
                   "limitations": ["The ranking contract changed the requested TOP-N limit."],
                   "metadata": {"status": "failed", "error_type": "SQLValidationError"}}
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory) / "run")
            data = asyncio.run(RUNNER.run_cases(FakeAgent(blocked), case_set(), store))
            outcome = data["cases"][0]
            self.assertEqual(outcome["status"], "failed")
            self.assertEqual(outcome["failure_class"], "sql_validation_failure")
            self.assertIn("TOP-N", outcome["error_detail"])
            self.assertIn("SELECT *", outcome["sql"])

    def test_bounded_repair_success_is_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory) / "run")
            data = asyncio.run(RUNNER.run_cases(FakeAgent(generation_count=2), case_set(), store))
            self.assertEqual(data["cases"][0]["calls"]["sql_repair"], 1)

    def test_bounded_repair_failure_is_saved_as_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory) / "run")
            agent = FakeAgent({"ok": False, "sql": "SELECT 1 LIMIT 1", "parameters": [],
                               "limitations": ["repair exhausted"],
                               "metadata": {"status": "failed", "error_type": "SQLValidationError"}},
                              generation_count=2)
            data = asyncio.run(RUNNER.run_cases(agent, case_set(), store))
            self.assertEqual(data["cases"][0]["status"], "failed")
            self.assertEqual(data["cases"][0]["failure_class"], "sql_validation_failure")

    def test_provider_outage_is_recorded_without_aborting_remaining_cases(self):
        cases = {"cases": [*case_set()["cases"],
                           {"id": "T02", "question": "second query", "supported": True}]}

        class FirstFails(FakeAgent):
            calls = 0

            async def run_payload(self, request):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("provider outage")
                return await super().run_payload(request)

        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory) / "run", cases=cases)
            data = asyncio.run(RUNNER.run_cases(FirstFails(), cases, store))
            self.assertEqual(data["cases"][0]["status"], "provider_error")
            self.assertEqual(data["cases"][1]["status"], "executed")

    def test_jev_http_error_is_counted_and_classified(self):
        from core.agents.sql import agent as sql_module

        class CallsJev(FakeAgent):
            async def run_payload(self, _request):
                sql_module.select_jev_schema_tables("synthetic question", {"commerce.orders": ["order_id"]})

        error = HTTPError("https://provider.invalid", 402, "payment required", {}, None)
        with tempfile.TemporaryDirectory() as directory, patch.object(
            sql_module, "select_jev_schema_tables", side_effect=error
        ):
            store = self.make_store(Path(directory) / "run")
            data = asyncio.run(RUNNER.run_cases(CallsJev(), case_set(), store))
            selection = data["cases"][0]["schema_selection"]
            self.assertEqual(selection["jev_status"], "failed")
            self.assertEqual(selection["jev_http_status"], 402)
            self.assertEqual(data["cases"][0]["calls"]["jev_attempts"], 1)

    def test_valid_clarification_is_a_nonexecution_outcome(self):
        result = {"ok": False, "metadata": {"status": "clarification_required"},
                  "answer": "Which table should define this metric?"}
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory) / "run")
            data = asyncio.run(RUNNER.run_cases(FakeAgent(result), case_set(), store))
            self.assertEqual(data["cases"][0]["status"], "clarification_required")
            self.assertEqual(data["cases"][0]["execution_events"], [])

    def test_unsupported_case_is_persisted_without_gold_sql(self):
        cases = {"cases": [{"id": "T01", "question": "unsupported", "supported": False}]}
        result = {"ok": False, "metadata": {"status": "unsupported"},
                  "answer": "The schema does not contain the requested dimension."}
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory) / "run", cases=cases)
            data = asyncio.run(RUNNER.run_cases(FakeAgent(result), cases, store))
            self.assertEqual(data["cases"][0]["status"], "unsupported")
            self.assertIsNone(data["cases"][0]["sql"])

    def test_interrupted_case_is_atomically_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory) / "run"
            store = self.make_store(run_path)
            with self.assertRaises(KeyboardInterrupt):
                asyncio.run(RUNNER.run_cases(FakeAgent(error=KeyboardInterrupt()), case_set(), store))
            persisted = json.loads((run_path / "data.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["cases"][0]["status"], "INTERRUPTED")
            self.assertEqual(persisted["cases"][0]["attempts"][0]["status"], "INTERRUPTED")

    def test_cancelled_case_is_persisted_as_interrupted(self):
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory) / "run"
            store = self.make_store(run_path)
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(RUNNER.run_cases(FakeAgent(error=asyncio.CancelledError()), case_set(), store))
            persisted = json.loads((run_path / "data.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["cases"][0]["status"], "INTERRUPTED")

    def test_completed_experiment_cannot_be_resumed_or_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run"
            store = self.make_store(path)
            asyncio.run(RUNNER.run_cases(FakeAgent(), case_set(), store))
            with self.assertRaises(FileExistsError):
                self.make_store(path, resume=True)

    def test_provider_instrumentation_preserves_runtime_generate_signature(self):
        from core.agents.sql import agent as sql_module

        original = sql_module.generate
        agent = FakeAgent()
        restore = RUNNER.instrument_agent(agent, RUNNER.Instrumentation())
        try:
            self.assertEqual(inspect.signature(sql_module.generate), inspect.signature(original))
        finally:
            restore()

    def test_sql_provider_fallback_calls_are_counted_by_stage(self):
        from core.agents.sql import agent as sql_module

        async def generate(provider, prompt, *, timeout=15, max_output_tokens=None):
            if provider == "primary":
                raise RuntimeError("primary provider unavailable")
            return "fallback SQL"

        class FallbackAgent:
            async def _generate_sql(self, prompt):
                try:
                    return await sql_module.generate("primary", prompt, timeout=75)
                except RuntimeError:
                    return await sql_module.generate("secondary", prompt, timeout=75)

        with patch.object(sql_module, "generate", new=generate):
            instrumentation = RUNNER.Instrumentation()
            agent = FallbackAgent()
            restore = RUNNER.instrument_agent(agent, instrumentation)
            try:
                result = asyncio.run(agent._generate_sql("prompt"))
            finally:
                restore()

        self.assertEqual(result, "fallback SQL")
        self.assertEqual(instrumentation.calls["general_sql_generation"], 2)
        self.assertEqual(instrumentation.calls["provider_fallback_calls"], 1)
        self.assertEqual(instrumentation.calls["local_codex_fallback_calls"], 0)

    def test_local_codex_fallback_is_counted_separately(self):
        from core.agents.sql import agent as sql_module

        async def generate(_provider, _prompt, *, timeout=15, max_output_tokens=None):
            raise RuntimeError("primary provider unavailable")

        async def local_codex(_prompt, _provider_error):
            return "local SQL"

        class LocalFallbackAgent:
            async def _generate_sql(self, prompt):
                try:
                    return await sql_module.generate("primary", prompt, timeout=75)
                except RuntimeError as error:
                    return await sql_module.generate_with_local_codex(prompt, error)

        with patch.object(sql_module, "generate", new=generate), \
             patch.object(sql_module, "generate_with_local_codex", new=local_codex):
            instrumentation = RUNNER.Instrumentation()
            agent = LocalFallbackAgent()
            restore = RUNNER.instrument_agent(agent, instrumentation)
            try:
                result = asyncio.run(agent._generate_sql("prompt"))
            finally:
                restore()

        self.assertEqual(result, "local SQL")
        self.assertEqual(instrumentation.calls["general_sql_generation"], 1)
        self.assertEqual(instrumentation.calls["provider_fallback_calls"], 0)
        self.assertEqual(instrumentation.calls["local_codex_fallback_calls"], 1)

    def test_compiler_matches_and_generated_plans_are_counted_from_typed_stages(self):
        from core.agents.sql import agent as sql_module
        from core.agents.sql.metric_mapping import MetricMapping, MetricTime

        agent = FakeAgent()
        instrumentation = RUNNER.Instrumentation()
        restore = RUNNER.instrument_agent(agent, instrumentation)
        try:
            match = sql_module.match_fixed_query(
                "What was total revenue for 2025?", today=date(2026, 11, 20)
            )
            selection = sql_module.compile_fixed_query(match)
            self.assertTrue(match.matched)
            self.assertEqual(match.compiler.value, "annual_revenue")
            self.assertEqual(selection.plan.parameters, (date(2025, 1, 1), date(2026, 1, 1)))
            unmatched = sql_module.match_fixed_query("show all revenue")
            self.assertFalse(unmatched.matched)
            sql_module.compile_fixed_query(unmatched)
            inventory_selection = sql_module.compile_inventory_mapping(
                MetricMapping(
                    metrics=["stock_on_hand"], time=MetricTime(mode="snapshot", start="2026-11-13"),
                    representation="product",
                )
            )
            self.assertIsNotNone(inventory_selection.plan)
        finally:
            restore()

        self.assertEqual(instrumentation.calls["fixed_match_calls"], 2)
        self.assertEqual(instrumentation.calls["fixed_compiler_matches"], 1)
        self.assertEqual(instrumentation.calls["fixed_compilation_calls"], 2)
        self.assertEqual(instrumentation.calls["fixed_compiler_plans"], 1)
        self.assertEqual(instrumentation.calls["inventory_compilation_calls"], 1)
        self.assertEqual(instrumentation.calls["inventory_compiler_plans"], 1)

    def test_execution_attempts_are_separate_from_successful_repository_queries(self):
        class Repository:
            async def get_schema(self):
                return {"tables": {}}

            async def execute_approved_query(self, _sql, *_parameters):
                return [{"n": 1}]

            async def execute_unverified_query(self, _sql, *_parameters):
                return [{"n": 1}]

        class Executes(FakeAgent):
            def __init__(self):
                super().__init__()
                self.repository = RUNNER.CountingRepository(Repository())

            async def run_payload(self, _request):
                await self.repository.get_schema()
                rows = await self.repository.execute_approved_query("SELECT 1")
                return {**self.outcome, "rows": rows}

        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory) / "run")
            data = asyncio.run(RUNNER.run_cases(Executes(), case_set(), store))

        calls = data["cases"][0]["calls"]
        self.assertEqual(calls["schema_discovery"], 1)
        self.assertEqual(calls["repository_execution_attempts"], 1)
        self.assertEqual(calls["repository_execution"], 1)
        self.assertEqual(calls["approved_repository_execution"], 1)
        self.assertEqual(data["cases"][0]["execution_events"], [
            {"kind": "approved", "security_validated": True, "semantic_approval": True}
        ])

    def test_failed_repository_attempt_is_not_reported_as_successful_execution(self):
        class Repository:
            async def get_schema(self):
                return {"tables": {}}

            async def execute_approved_query(self, _sql, *_parameters):
                raise RuntimeError("database connection failed")

            async def execute_unverified_query(self, _sql, *_parameters):
                raise RuntimeError("database connection failed")

        class HandlesFailure(FakeAgent):
            def __init__(self):
                super().__init__()
                self.repository = RUNNER.CountingRepository(Repository())

            async def run_payload(self, _request):
                await self.repository.get_schema()
                try:
                    await self.repository.execute_approved_query("SELECT 1")
                except RuntimeError:
                    return {"ok": False, "query_status": "error", "sql": "SELECT 1", "rows": [],
                            "metadata": {"status": "failed", "error_type": "DatabaseError",
                                         "error": "database connection failed"}}

        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory) / "run")
            data = asyncio.run(RUNNER.run_cases(HandlesFailure(), case_set(), store))

        record = data["cases"][0]
        self.assertEqual(record["calls"]["repository_execution_attempts"], 1)
        self.assertEqual(record["calls"]["repository_execution"], 0)
        self.assertEqual(record["execution_events"], [])

    def test_jev_selection_and_repository_schema_discovery_are_distinct(self):
        from core.agents.sql import agent as sql_module

        class Selects(FakeAgent):
            async def run_payload(self, _request):
                sql_module.select_jev_schema_tables("question", {"commerce.orders": ["order_id"]})
                return self.outcome

        with tempfile.TemporaryDirectory() as directory, patch.object(
            sql_module, "select_jev_schema_tables", return_value={"commerce.orders"}
        ):
            store = self.make_store(Path(directory) / "run")
            data = asyncio.run(RUNNER.run_cases(Selects(), case_set(), store))

        calls = data["cases"][0]["calls"]
        self.assertEqual(calls["schema_selection"], 1)
        self.assertEqual(calls["jev_attempts"], 1)
        self.assertEqual(calls["schema_discovery"], 0)

    def test_database_preflight_never_reuses_analytics_url(self):
        with patch.dict("os.environ", {"ANALYTICS_DATABASE_URL": "postgresql://same-host/production"}, clear=True):
            with self.assertRaisesRegex(RUNNER.PreflightBlocked, "SQL_BENCHMARK_DATABASE_URL is not configured"):
                RUNNER.validate_database_environment()

    def test_source_manifest_includes_typed_compiler_and_repository_paths(self):
        hashes = RUNNER.source_manifest()
        self.assertIn("src/core/agents/sql/compiler_dispatch.py", hashes)
        self.assertIn("src/core/agents/sql/agent.py", hashes)
        self.assertIn("src/core/database/commerce_repository.py", hashes)

    def test_preflight_records_and_requires_the_frozen_order_date_type(self):
        class PreflightRepository:
            def __init__(self, order_date_type="date"):
                self.order_date_type = order_date_type

            async def get_schema(self):
                return {
                    "tables": {
                        "commerce.sales": (), "commerce.orders": (),
                        "commerce.order_items": (), "commerce.inventory": (),
                    },
                    "column_types": {"commerce.orders": {"order_date": self.order_date_type}},
                    "date_columns": (("commerce.orders", "order_date"),),
                }

            async def execute_approved_query(self, sql, *parameters):
                if "delivered_orders" in sql:
                    return [{"delivered_orders": 3}]
                if "commerce.sales" in sql and "SUM(s.revenue)" in sql:
                    return [{"rows": 4, "revenue": 25}]
                if "commerce.sales" in sql:
                    return [{"rows": 4, "date_min": "2025-01-01", "date_max": "2026-11-13"}]
                if "commerce.orders" in sql:
                    return [{"rows": 4, "date_min": "2025-01-01", "date_max": "2026-11-13"}]
                if "MIN(i.snapshot_date)" in sql:
                    return [{"rows": 4, "snapshot_min": "2026-01-01", "snapshot_max": "2026-11-13",
                             "snapshot_count": 3}]
                return [{"rows": 2}]

        result = asyncio.run(collect_preflight(PreflightRepository()))
        self.assertEqual(result["verified_column_types"], {"commerce.orders.order_date": "date"})
        self.assertEqual(result["coverage"]["commerce.orders"]["order_date_type"], "date")
        with self.assertRaisesRegex(PreflightBlocked, "Frozen case requires commerce.orders.order_date to be date"):
            asyncio.run(collect_preflight(PreflightRepository("timestamp without time zone")))
        missing_type = PreflightRepository()
        async def schema_without_column_type():
            schema = await PreflightRepository.get_schema(missing_type)
            schema["column_types"]["commerce.orders"].pop("order_date")
            return schema
        missing_type.get_schema = schema_without_column_type
        with self.assertRaisesRegex(PreflightBlocked, "Could not verify live database type"):
            asyncio.run(collect_preflight(missing_type))

    def test_reference_runner_recreates_gold_rows_and_skips_unsupported_sql(self):
        cases = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))

        class ReferenceRepository:
            def __init__(self):
                self.queries = []

            async def execute_approved_query(self, sql, *parameters):
                self.queries.append((sql, parameters))
                for case in cases["cases"]:
                    if case["gold"].get("sql") == sql:
                        return case["gold"]["rows"]
                return []

        repository = ReferenceRepository()
        with patch.object(REFERENCE, "collect_preflight", return_value={"fingerprint_sha256": "fixture"}):
            result = asyncio.run(REFERENCE.generate_reference(cases, repository))
        self.assertTrue(result["all_supported_references_match_frozen_gold"])
        self.assertEqual(len(result["cases"]), 5)
        self.assertEqual(sum(case["id"] == "P05" for case in result["cases"]), 1)
        self.assertNotIn(cases["cases"][4]["gold"]["sql"], {sql for sql, _ in repository.queries})

    def test_reference_snapshot_change_stops_before_generation(self):
        cases = case_set()
        reference = {"environment": {"fingerprint_sha256": "same"},
                     "all_supported_references_match_frozen_gold": True,
                     "cases": [{"id": "T01", "matches_frozen_gold": True, "result_sha256": "old"}]}
        RUNNER.validate_reference_snapshot(reference, reference, cases)
        changed = {**reference, "cases": [{"id": "T01", "matches_frozen_gold": True, "result_sha256": "new"}]}
        with self.assertRaisesRegex(ValueError, "rows for T01 changed"):
            RUNNER.validate_reference_snapshot(reference, changed, cases)


if __name__ == "__main__":
    unittest.main()
