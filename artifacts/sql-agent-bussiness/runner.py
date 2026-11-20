"""Run frozen SQL business cases with atomic per-case persistence."""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import functools
import hashlib
import importlib.util
import inspect
import json
import importlib.metadata
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from preflight import ROOT, PreflightBlocked, benchmark_repository, collect_preflight, validate_database_environment


DEFAULT_CASES = ROOT / "artifacts/sql-agent-bussiness/cases.json"
TERMINAL_STATUSES = {
    "executed", "executed_empty", "clarification_required", "unsupported", "failed", "provider_error",
}
SECRET_ENV_NAMES = (
    "SQL_BENCHMARK_DATABASE_URL", "ANALYTICS_DATABASE_URL", "OPENROUTER_API_KEY",
    "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_WORKERS_API", "GROQ_API_KEY",
)


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=_json_value,
                      separators=(",", ":"))


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return str(value)


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def current_revision():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _git_changed_paths():
    commands = (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    paths = set()
    for command in commands:
        output = subprocess.check_output(command, cwd=ROOT, text=True)
        paths.update(line.strip() for line in output.splitlines() if line.strip())
    return sorted(paths)


def source_manifest():
    paths = set(_git_changed_paths())
    paths.update({
        "src/core/agents/sql/agent.py",
        "src/core/agents/sql/assistant_endpoint.py",
        "src/core/agents/sql/compiler_dispatch.py",
        "src/core/agents/decision_support/intent_classifier.py",
        "src/core/agents/sql/field_retrieval.py",
        "src/core/agents/sql/intent_resolution.py",
        "src/core/agents/sql/join_validation.py",
        "src/core/agents/sql/metric_mapping.py",
        "src/core/agents/sql/metric_ontology.py",
        "src/core/agents/sql/metric_validation.py",
        "src/core/agents/sql/query_contract.py",
        "src/core/agents/sql/query_intent.py",
        "src/core/agents/sql/sql_ranking.py",
        "src/core/agents/sql/text_to_sql.py",
        "src/core/database/commerce_repository.py",
        "src/core/prompts/sql.py",
        "data/semantic/vietstyle_metrics_v1.yaml",
    })
    hashes = {}
    for relative in sorted(paths):
        path = ROOT / relative
        if path.is_file() and (relative.startswith("src/") or relative.startswith("data/semantic/")):
            hashes[relative] = sha256_file(path)
    return hashes


def build_manifest(application_revision, *, provider, model):
    head = current_revision()
    dirty_paths = [path for path in _git_changed_paths()
                   if not path.startswith("artifacts/sql-agent-bussiness/runs/")]
    if application_revision != head:
        raise ValueError(f"Pinned application revision {application_revision} does not match current HEAD {head}.")
    if dirty_paths and os.getenv("SQL_BENCHMARK_ALLOW_DIRTY", "").casefold() != "true":
        raise ValueError("The worktree is dirty; set SQL_BENCHMARK_ALLOW_DIRTY=true to record source hashes explicitly.")
    source_hashes = source_manifest()
    prompt_path = ROOT / "src/core/prompts/sql.py"
    benchmark_files = (
        "artifacts/sql-agent-bussiness/cases.json",
        "artifacts/sql-agent-bussiness/benchmark_40_plan.json",
        "artifacts/sql-agent-bussiness/failure_classes.json",
        "artifacts/sql-agent-bussiness/preflight.py",
        "artifacts/sql-agent-bussiness/reference_runner.py",
        "artifacts/sql-agent-bussiness/runner.py",
        "artifacts/sql-agent-bussiness/scorer.py",
        "artifacts/sql-agent-bussiness/PROTOCOL.md",
        "artifacts/sql-agent-bussiness/README.md",
        "artifacts/sql-agent-bussiness/THESIS_ALIGNMENT.md",
        "artifacts/sql-agent-bussiness/tests/test_runner.py",
        "artifacts/sql-agent-bussiness/tests/test_scorer.py",
    )
    config = {
        "experiment_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "application_revision": head,
        "dirty_worktree": bool(dirty_paths),
        "dirty_paths": dirty_paths,
        "source_hashes": source_hashes,
        "source_fingerprint_sha256": sha256_bytes(canonical_json(source_hashes).encode()),
        "benchmark_code_hashes": {path: sha256_file(ROOT / path) for path in benchmark_files},
        "prompt_hashes": {
            "src/core/prompts/sql.py": sha256_file(prompt_path),
            "src/core/agents/sql/metric_mapping.py": sha256_file(ROOT / "src/core/agents/sql/metric_mapping.py"),
        },
        "provider": provider,
        "model": model,
        "intent_model": "not invoked by direct SQL-agent route",
        "jev_model": "typesafe/jev-1.14",
        "provider_settings": {
            key: os.getenv(key) for key in (
                "SQL_LLM_PROVIDER", "SQL_GROQ_MODEL", "SQL_CLOUDFLARE_MODEL",
                "CODEX_CLI_SQL_FALLBACK", "SQL_INVENTORY_ONLY", "ANALYTICS_SCHEMAS",
            ) if os.getenv(key) is not None
        },
        "package_versions": _package_versions(),
        "repair_budget": 1,
        "python_version": sys.version.split()[0],
    }
    config["configuration_fingerprint"] = sha256_bytes(canonical_json(config).encode())
    return config


def _package_versions():
    package_names = ("sqlglot", "asyncpg", "supabase", "pydantic", "httpx")
    return {
        package: importlib.metadata.version(package)
        for package in package_names
        if _distribution_available(package)
    }


def _distribution_available(package):
    try:
        importlib.metadata.version(package)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, default=_json_value) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ExperimentStore:
    """Atomic run storage; completed experiments and cases are immutable."""

    def __init__(self, output_dir, manifest, case_set, *, resume=False):
        self.directory = Path(output_dir).resolve()
        self.path = self.directory / "data.json"
        self.manifest = dict(manifest)
        self.case_set = case_set
        ids = [case["id"] for case in case_set["cases"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Case IDs must be unique.")
        if self.directory.exists() and any(self.directory.iterdir()):
            if not resume or not self.path.exists():
                raise FileExistsError(f"Refusing to overwrite non-empty experiment directory: {self.directory}")
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            previous = self.data.get("manifest", {})
            if previous.get("status") in {"completed", "completed_with_failures"}:
                raise FileExistsError("A completed experiment is immutable and cannot be resumed or overwritten.")
            if previous.get("configuration_fingerprint") != manifest.get("configuration_fingerprint"):
                raise ValueError("Resume configuration does not match the original experiment manifest.")
            self.data.setdefault("cases", [])
        else:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.data = {
                "format_version": "sql-business-observations.v1",
                "manifest": {**manifest, "status": "running", "started_at": _utc_now()},
                "case_set_sha256": sha256_bytes(canonical_json(case_set).encode()),
                "cases": [],
            }
            self.persist()

    def persist(self):
        _atomic_json(self.path, self.data)

    def case_record(self, case_id):
        return next((item for item in self.data["cases"] if item["id"] == case_id), None)

    def upsert_case(self, record):
        previous = self.case_record(record["id"])
        if previous is None:
            self.data["cases"].append(record)
        else:
            if previous.get("status") in TERMINAL_STATUSES:
                raise ValueError(f"Completed case {record['id']} is immutable.")
            index = self.data["cases"].index(previous)
            self.data["cases"][index] = record
        self.persist()


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _redact(text):
    text = str(text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(postgres(?:ql)?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    for name in SECRET_ENV_NAMES:
        secret = os.getenv(name, "")
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
    return text[:2_000]


def classify_status(payload):
    metadata = payload.get("metadata") or {}
    status = metadata.get("status") or payload.get("status")
    if status in {"clarification_required", "unsupported"}:
        return status
    if payload.get("query_status") == "executed":
        return "executed_empty" if not payload.get("rows") else "executed"
    if payload.get("ok"):
        return "executed_empty" if not payload.get("rows") else "executed"
    return "failed"


def normalize_payload(case, payload, instrumentation, latency_ms):
    metadata = payload.get("metadata") or {}
    status = classify_status(payload)
    query_status = payload.get("query_status")
    if query_status == "executed" and not payload.get("rows"):
        status = "executed_empty"
    execution_events = [
        {"kind": event["kind"], "security_validated": True,
         "semantic_approval": event["kind"] == "approved"}
        for event in instrumentation.execution_events
    ]
    columns_meta = metadata.get("columns") or []
    columns = [item.get("name") if isinstance(item, dict) else str(item) for item in columns_meta]
    rows = payload.get("rows") or []
    if not columns and rows:
        columns = list(rows[0])
    error = metadata.get("error") or metadata.get("error_detail") or payload.get("error")
    if status == "failed" and not error:
        limitations = payload.get("limitations") or []
        error = limitations[0] if limitations else None
    return {
        "id": case["id"],
        "question": case["question"],
        "status": status,
        "sql": payload.get("sql") or payload.get("attempted_sql"),
        "parameters": payload.get("parameters") or payload.get("attempted_parameters") or [],
        "rows": rows,
        "columns": columns,
        "answer": _redact(payload.get("answer", "")),
        "error_type": metadata.get("error_type"),
        "error_detail": _redact(error) if error else None,
        "failure_class": classify_failure(status, metadata, error),
        "execution_events": execution_events,
        "schema_selection": {
            "method": metadata.get("schema_table_selection"),
            "candidate_tables": metadata.get("schema_table_candidates", []),
            "required_tables": metadata.get("schema_table_required", []),
            "final_selected_tables": metadata.get("schema_table_final_selected"),
            "ontology_added_sources": metadata.get("schema_ontology_added_sources", []),
            "approved_join_bridge_additions": metadata.get("schema_approved_join_bridge_additions", []),
            "failure": metadata.get("schema_selection_failure"),
            "jev_status": instrumentation.jev_status,
            "jev_http_status": instrumentation.jev_http_status,
        },
        "calls": dict(instrumentation.calls),
        "latency_ms": round(latency_ms, 3),
        "metadata": {key: metadata[key] for key in (
            "status", "query_status", "schema_table_selection", "schema_table_candidates",
            "schema_table_required", "schema_table_final_selected", "schema_ontology_added_sources",
            "schema_approved_join_bridge_additions", "schema_selection_failure",
            "semantic_interpretation", "metric_validation", "ranking_validation",
            "request_contract_status", "unverified_sql",
        ) if key in metadata},
    }


def classify_failure(status, metadata, error):
    if status in {"executed", "executed_empty", "clarification_required", "unsupported"}:
        return None
    text = str(error or "").casefold()
    error_type = str(metadata.get("error_type", "")).casefold()
    if "sqlvalidation" in error_type or "validation" in text:
        return "sql_validation_failure"
    if "provider" in text or "http 402" in text or "quota" in text:
        return "provider_failure"
    if "database" in text or "connection" in text:
        return "database_failure"
    return "agent_failure"


def validate_reference_snapshot(reference, current_reference, case_set):
    if not reference.get("all_supported_references_match_frozen_gold"):
        raise ValueError("The supplied reference artifact does not match all frozen gold contracts.")
    if reference.get("environment", {}).get("fingerprint_sha256") != current_reference.get("environment", {}).get("fingerprint_sha256"):
        raise ValueError("Database fingerprint differs from the saved reference artifact.")
    expected = {item["id"]: item for item in reference.get("cases", [])}
    current = {item["id"]: item for item in current_reference.get("cases", [])}
    for case in case_set["cases"]:
        if not case["supported"]:
            continue
        before, now = expected.get(case["id"]), current.get(case["id"])
        if (before is None or now is None or not before.get("matches_frozen_gold")
                or not now.get("matches_frozen_gold")
                or before.get("result_sha256") != now.get("result_sha256")):
            raise ValueError(
                f"Reference rows for {case['id']} changed or failed the frozen contract; stop before model calls."
            )


class CountingRepository:
    def __init__(self, repository):
        self.repository = repository
        self.calls = {
            "schema_discovery": 0,
            "approved_execution_attempts": 0,
            "unverified_execution_attempts": 0,
            "approved_executions": 0,
            "unverified_executions": 0,
        }
        self.execution_events = []

    async def get_schema(self):
        self.calls["schema_discovery"] += 1
        return await self.repository.get_schema()

    async def execute_approved_query(self, sql, *parameters):
        self.calls["approved_execution_attempts"] += 1
        result = await self.repository.execute_approved_query(sql, *parameters)
        self.calls["approved_executions"] += 1
        self.execution_events.append({"kind": "approved"})
        return result

    async def execute_unverified_query(self, sql, *parameters):
        self.calls["unverified_execution_attempts"] += 1
        result = await self.repository.execute_unverified_query(sql, *parameters)
        self.calls["unverified_executions"] += 1
        self.execution_events.append({"kind": "unverified"})
        return result

    async def close(self):
        await self.repository.close()


class Instrumentation:
    def __init__(self):
        self.calls = {
            "fixed_match_calls": 0, "fixed_compiler_matches": 0,
            "fixed_compilation_calls": 0, "fixed_compiler_plans": 0,
            "inventory_compilation_calls": 0, "inventory_compiler_plans": 0,
            "general_sql_generation": 0,
            "intent_interpretation": 0, "metric_interpretation": 0,
            "provider_fallback_calls": 0, "local_codex_fallback_calls": 0,
            "jev_attempts": 0, "jev_successes": 0, "sql_repair": 0,
            "schema_selection": 0, "schema_discovery": 0,
            "repository_execution_attempts": 0, "repository_execution": 0,
            "approved_repository_execution_attempts": 0,
            "unverified_repository_execution_attempts": 0,
            "approved_repository_execution": 0, "unverified_repository_execution": 0,
            "sql_generation_entries": 0,
        }
        self.jev_status = "not_attempted"
        self.jev_http_status = None
        self.execution_events = []


def instrument_agent(agent, instrumentation):
    """Instrument stage boundaries while retaining the provider API signatures."""
    from core.agents.sql import agent as sql_module
    original_generate = sql_module.generate
    generating_sql = contextvars.ContextVar("benchmark_generating_sql", default=False)
    sql_provider_attempts = contextvars.ContextVar("benchmark_sql_provider_attempts", default=None)

    @functools.wraps(original_generate)
    async def counted_generate(provider, prompt, *, timeout=15, max_output_tokens=None):
        if generating_sql.get():
            instrumentation.calls["general_sql_generation"] += 1
            attempts = sql_provider_attempts.get() or 0
            if attempts:
                instrumentation.calls["provider_fallback_calls"] += 1
            sql_provider_attempts.set(attempts + 1)
        else:
            instrumentation.calls["metric_interpretation"] += 1
        return await original_generate(provider, prompt, timeout=timeout,
                                       max_output_tokens=max_output_tokens)

    original_local_codex = sql_module.generate_with_local_codex

    @functools.wraps(original_local_codex)
    async def counted_local_codex(prompt, provider_error):
        instrumentation.calls["local_codex_fallback_calls"] += 1
        return await original_local_codex(prompt, provider_error)

    original_fixed_match = sql_module.match_fixed_query

    @functools.wraps(original_fixed_match)
    def counted_fixed_match(*args, **kwargs):
        instrumentation.calls["fixed_match_calls"] += 1
        match = original_fixed_match(*args, **kwargs)
        if match.matched:
            instrumentation.calls["fixed_compiler_matches"] += 1
        return match

    sql_module.match_fixed_query = counted_fixed_match

    original_fixed_compile = sql_module.compile_fixed_query

    @functools.wraps(original_fixed_compile)
    def counted_fixed_compile(*args, **kwargs):
        instrumentation.calls["fixed_compilation_calls"] += 1
        selection = original_fixed_compile(*args, **kwargs)
        if selection.plan is not None:
            instrumentation.calls["fixed_compiler_plans"] += 1
        return selection

    sql_module.compile_fixed_query = counted_fixed_compile

    original_inventory_compile = sql_module.compile_inventory_mapping

    @functools.wraps(original_inventory_compile)
    def counted_inventory_compile(*args, **kwargs):
        instrumentation.calls["inventory_compilation_calls"] += 1
        selection = original_inventory_compile(*args, **kwargs)
        if selection.plan is not None:
            instrumentation.calls["inventory_compiler_plans"] += 1
        return selection

    sql_module.compile_inventory_mapping = counted_inventory_compile

    original_sql_generation = agent._generate_sql

    # Count calls at the agent entry point as well as provider calls. The first
    # generation is not a repair; later generation entries are bounded repairs.
    @functools.wraps(original_sql_generation)
    async def counted_sql_entry(prompt):
        number_before = instrumentation.calls.get("sql_generation_entries", 0)
        instrumentation.calls["sql_generation_entries"] = number_before + 1
        if number_before:
            instrumentation.calls["sql_repair"] += 1
        token = generating_sql.set(True)
        attempts_token = sql_provider_attempts.set(0)
        try:
            return await original_sql_generation(prompt)
        finally:
            sql_provider_attempts.reset(attempts_token)
            generating_sql.reset(token)

    agent._generate_sql = counted_sql_entry
    sql_module.generate = counted_generate
    sql_module.generate_with_local_codex = counted_local_codex
    original_jev = sql_module.select_jev_schema_tables

    @functools.wraps(original_jev)
    def counted_jev(question, table_columns, metric_definitions=None, *, primary_keys=None,
                    approved_joins=(), limit=5):
        instrumentation.calls["schema_selection"] += 1
        instrumentation.calls["jev_attempts"] += 1
        try:
            result = original_jev(question, table_columns, metric_definitions,
                                  primary_keys=primary_keys, approved_joins=approved_joins, limit=limit)
        except Exception as error:
            status = getattr(error, "code", None) or getattr(error, "status", None)
            if status is None:
                status = getattr(error, "status_code", None)
            instrumentation.jev_status = "failed"
            instrumentation.jev_http_status = status
            raise
        instrumentation.calls["jev_successes"] += 1
        instrumentation.jev_status = "available"
        return result

    sql_module.select_jev_schema_tables = counted_jev

    def restore():
        sql_module.generate = original_generate
        sql_module.generate_with_local_codex = original_local_codex
        sql_module.match_fixed_query = original_fixed_match
        sql_module.compile_fixed_query = original_fixed_compile
        sql_module.compile_inventory_mapping = original_inventory_compile
        sql_module.select_jev_schema_tables = original_jev
        agent._generate_sql = original_sql_generation

    return restore


async def run_cases(agent, case_set, store):
    from core.models.agents import AgentRequest, VerifiedIdentity

    for case in case_set["cases"]:
        previous = store.case_record(case["id"])
        if previous and previous.get("status") in TERMINAL_STATUSES:
            continue
        attempts = list(previous.get("attempts", [])) if previous else []
        started = time.perf_counter()
        attempt_record = {"attempt": len(attempts) + 1, "status": "RUNNING", "started_at": _utc_now()}
        current_attempts = attempts + [attempt_record]
        running = {"id": case["id"], "status": "RUNNING", "attempts": current_attempts,
                   "route": "sql_agent", "started_at": _utc_now()}
        store.upsert_case(running)
        instrumentation = Instrumentation()
        counting_repository = getattr(agent, "repository", None)
        if isinstance(counting_repository, CountingRepository):
            repository_counters = counting_repository
            repository_before = dict(repository_counters.calls)
            event_offset = len(repository_counters.execution_events)
        else:
            repository_counters = None
            repository_before = {}
            event_offset = 0
        restore = instrument_agent(agent, instrumentation)
        try:
            request = AgentRequest(
                question=case["question"],
                identity=VerifiedIdentity(subject="sql-benchmark", permissions={"analytics:read"}),
            )
            payload = await agent.run_payload(request)
            elapsed_ms = (time.perf_counter() - started) * 1000
            record = normalize_payload(case, payload, instrumentation, elapsed_ms)
            record["route"] = "sql_agent"
            record["calls"] = dict(instrumentation.calls)
            if repository_counters is not None:
                schema_count = repository_counters.calls["schema_discovery"] - repository_before["schema_discovery"]
                approved_attempts = (repository_counters.calls["approved_execution_attempts"]
                                     - repository_before["approved_execution_attempts"])
                unverified_attempts = (repository_counters.calls["unverified_execution_attempts"]
                                       - repository_before["unverified_execution_attempts"])
                approved_count = (repository_counters.calls["approved_executions"]
                                  - repository_before["approved_executions"])
                unverified_count = (repository_counters.calls["unverified_executions"]
                                    - repository_before["unverified_executions"])
                instrumentation.calls["schema_discovery"] = schema_count
                instrumentation.calls["approved_repository_execution_attempts"] = approved_attempts
                instrumentation.calls["unverified_repository_execution_attempts"] = unverified_attempts
                instrumentation.calls["repository_execution"] = (
                    approved_count + unverified_count
                )
                instrumentation.calls["repository_execution_attempts"] = (
                    approved_attempts + unverified_attempts
                )
                instrumentation.calls["approved_repository_execution"] = approved_count
                instrumentation.calls["unverified_repository_execution"] = unverified_count
                instrumentation.execution_events = repository_counters.execution_events[event_offset:]
                record["execution_events"] = [
                    {"kind": event["kind"], "security_validated": True,
                     "semantic_approval": event["kind"] == "approved"}
                    for event in instrumentation.execution_events
                ]
                record["calls"].update(instrumentation.calls)
            attempt_record.update(status=record["status"], latency_ms=record["latency_ms"])
            record["attempts"] = current_attempts
            record["completed_at"] = _utc_now()
            store.upsert_case(record)
        except (KeyboardInterrupt, asyncio.CancelledError):
            interrupted = {**running, "status": "INTERRUPTED",
                           "failure_class": "runner_interrupted",
                           "attempts": current_attempts}
            attempt_record["status"] = "INTERRUPTED"
            attempt_record["ended_at"] = _utc_now()
            store.upsert_case(interrupted)
            raise
        except Exception as error:
            repository_calls = {}
            execution_events = []
            if repository_counters is not None:
                schema_count = repository_counters.calls["schema_discovery"] - repository_before["schema_discovery"]
                approved_attempts = (repository_counters.calls["approved_execution_attempts"]
                                     - repository_before["approved_execution_attempts"])
                unverified_attempts = (repository_counters.calls["unverified_execution_attempts"]
                                       - repository_before["unverified_execution_attempts"])
                approved_count = (repository_counters.calls["approved_executions"]
                                  - repository_before["approved_executions"])
                unverified_count = (repository_counters.calls["unverified_executions"]
                                    - repository_before["unverified_executions"])
                repository_calls = {
                    "schema_discovery": schema_count,
                    "approved_repository_execution_attempts": approved_attempts,
                    "unverified_repository_execution_attempts": unverified_attempts,
                    "approved_repository_execution": approved_count,
                    "unverified_repository_execution": unverified_count,
                    "repository_execution_attempts": approved_attempts + unverified_attempts,
                    "repository_execution": approved_count + unverified_count,
                }
                execution_events = [
                    {"kind": event["kind"], "security_validated": True,
                     "semantic_approval": event["kind"] == "approved"}
                    for event in repository_counters.execution_events[event_offset:]
                ]
            failure = {
                **running,
                "status": "provider_error" if classify_failure("failed", {}, error) == "provider_failure" else "failed",
                "error_type": type(error).__name__,
                "error_detail": _redact(error),
                "failure_class": classify_failure("failed", {}, error),
                "schema_selection": {"method": None, "candidate_tables": [],
                                     "required_tables": [], "final_selected_tables": None,
                                     "ontology_added_sources": [], "approved_join_bridge_additions": [],
                                     "failure": {"error_type": type(error).__name__},
                                     "jev_status": instrumentation.jev_status,
                                     "jev_http_status": instrumentation.jev_http_status},
                "calls": {**instrumentation.calls, **repository_calls},
                "execution_events": execution_events,
                "attempts": current_attempts,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
            attempt_record.update(status=failure["status"], error_type=type(error).__name__,
                                  latency_ms=failure["latency_ms"], ended_at=_utc_now())
            store.upsert_case(failure)
        finally:
            restore()
    store.data["manifest"]["status"] = "completed_with_failures" if any(
        case.get("status") in {"failed", "provider_error", "INTERRUPTED"} for case in store.data["cases"]
    ) else "completed"
    store.data["manifest"]["completed_at"] = _utc_now()
    store.persist()
    return store.data


def _load_scorer():
    path = ROOT / "artifacts/sql-agent-bussiness/scorer.py"
    spec = importlib.util.spec_from_file_location("sql_agent_business_scorer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run_live(args):
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    os.environ["SQL_BENCHMARK_ALLOW_DIRTY"] = "true" if args.allow_dirty else os.environ.get("SQL_BENCHMARK_ALLOW_DIRTY", "")
    if args.provider:
        os.environ["SQL_LLM_PROVIDER"] = args.provider
    if args.model:
        if os.environ.get("SQL_LLM_PROVIDER", "groq").casefold() == "cloudflare":
            os.environ["SQL_CLOUDFLARE_MODEL"] = args.model
        else:
            os.environ["SQL_GROQ_MODEL"] = args.model
    provider = os.getenv("SQL_LLM_PROVIDER", "groq")
    model = args.model or os.getenv("SQL_CLOUDFLARE_MODEL" if provider.casefold() == "cloudflare" else "SQL_GROQ_MODEL")
    manifest = build_manifest(args.application_revision, provider=provider, model=model)
    existing_data = Path(args.output) / "data.json"
    if args.resume and existing_data.exists():
        previous_manifest = json.loads(existing_data.read_text(encoding="utf-8")).get("manifest", {})
        manifest["experiment_id"] = previous_manifest.get("experiment_id", manifest["experiment_id"])
        manifest.pop("configuration_fingerprint", None)
        manifest["configuration_fingerprint"] = sha256_bytes(canonical_json(manifest).encode())
    case_set = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    expected_case_hash = sha256_bytes(canonical_json(case_set).encode())
    if reference.get("case_set_sha256") != expected_case_hash:
        raise ValueError("Reference results were generated from a different case set.")
    async with benchmark_repository() as repository:
        preflight = await collect_preflight(repository)
        if preflight["fingerprint_sha256"] != reference.get("environment", {}).get("fingerprint_sha256"):
            raise ValueError("Database fingerprint differs from the reference; regenerate and review gold results first.")
        from reference_runner import generate_reference

        current_reference = await generate_reference(case_set, repository)
        validate_reference_snapshot(reference, current_reference, case_set)
        manifest["database_classification"] = preflight["database_classification"]
        manifest["database_role_read_only"] = preflight["database_role_read_only"]
        manifest["dataset_fingerprint_sha256"] = preflight["fingerprint_sha256"]
        manifest["preflight_coverage"] = preflight["coverage"]
        manifest["reference_sha256"] = sha256_file(args.reference)
        manifest.pop("configuration_fingerprint", None)
        manifest["configuration_fingerprint"] = sha256_bytes(canonical_json(manifest).encode())
        counting_repository = CountingRepository(repository)
        from core.agents.sql.agent import SQLAnalyticsAgent

        agent = SQLAnalyticsAgent(counting_repository, inventory_only=False)
        store = ExperimentStore(args.output, manifest, case_set, resume=args.resume)
        try:
            data = await run_cases(agent, case_set, store)
        finally:
            for configured_provider in (agent.llm, getattr(agent, "_fallback_llm", None)):
                close = getattr(configured_provider, "close", None)
                if close:
                    outcome = close()
                    if inspect.isawaitable(outcome):
                        await outcome
    scorer = _load_scorer()
    scored = scorer.score_experiment(case_set, data)
    _atomic_json(Path(args.output) / "scores.json", scored)
    report = scorer.render_report(case_set, scored, data["manifest"])
    (Path(args.output) / "report.md").write_text(report, encoding="utf-8")
    print(Path(args.output) / "report.md")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application-revision", required=True)
    parser.add_argument("--provider", choices=("groq", "cloudflare", "codex_cli"))
    parser.add_argument("--model")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--resume", action="store_true")
    arguments = parser.parse_args()
    try:
        validate_database_environment()
        asyncio.run(run_live(arguments))
    except PreflightBlocked as error:
        raise SystemExit(f"NOT RUN: {error}") from error
