"""Run the 75 supplied agent cases and save grounded, rate-limited Ragas scores."""

from __future__ import annotations

import asyncio
import argparse
import json
import math
import os
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.agents.main import create_app
from core.models.agents import AgentRequest, VerifiedIdentity
from evaluation.ragas_judge import build_ragas_metrics

DATA = ROOT / "evaluation/agent_benchmarks"
OUTPUT_DIR = ROOT / "artifacts/evaluation/agent-benchmarks-rerun-2026-10-23"
IDENTITY = VerifiedIdentity(subject="agent-benchmark", permissions={"analytics:read"})
METRIC_NAMES = ("faithfulness", "answer_relevancy", "context_precision")


class CaseTrace(BaseCallbackHandler):
    def __init__(self):
        self.events = 0

    def on_chain_start(self, *args, **kwargs):
        self.events += 1


def _load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _report_template(fixture):
    headings = fixture["required_sections"]
    tables = fixture.get("tables", [])
    parts = [f"# {fixture['name']}\n"]
    for heading in headings:
        parts.append(f"## {heading}\n")
        for table in tables:
            if heading.casefold() == table["name"].casefold():
                columns = table["columns"]
                parts.extend(("| " + " | ".join(columns) + " |",
                              "| " + " | ".join("---" for _ in columns) + " |"))
    return ("\n".join(parts) + "\n").encode()


def _sql_checks_match(rows, checks):
    if not checks:
        return None
    for check in checks:
        if "row_count" in check and len(rows) != check["row_count"]:
            return False
        if "field" in check:
            values = [row.get(check["field"]) for row in rows]
            if check.get("non_null") and not any(value is not None for value in values):
                return False
            if "equals" in check and not any(
                value is not None and math.isclose(float(value), float(check["equals"]), rel_tol=1e-6, abs_tol=1e-6)
                for value in values
            ):
                return False
    return True


def _plain_report(payload, media_type):
    if media_type.startswith("text/"):
        return payload.decode("utf-8", errors="replace")
    from docx import Document
    from io import BytesIO
    document = Document(BytesIO(payload))
    return "\n".join([p.text for p in document.paragraphs] + [
        " | ".join(cell.text for cell in row.cells)
        for table in document.tables for row in table.rows
    ])


async def _generate_case(app, router, group, case, fixture, request, config):
    if group == "report":
        async def generate(_input):
            return await app.state.report_agent.generate_from_template(
                request, "benchmark.md", _report_template(fixture),
            )
        runnable = RunnableLambda(generate)
        report_result, payload, media = await runnable.ainvoke({}, config=config)
        return {
            "answer": _plain_report(payload, media),
            "contexts": [item.content or json.dumps(item.metadata, ensure_ascii=False, default=str)
                         for item in report_result.evidence],
            "evidence_sources": [item.source for item in report_result.evidence],
            "agent_metadata": report_result.metadata,
        }

    mode = "knowledge" if group == "knowledge" else "sql"
    result = await router.run_mode(request, mode, config=config)
    contexts = [item.content or json.dumps(item.metadata, ensure_ascii=False, default=str)
                for item in result.evidence]
    rows = []
    semantic = None
    if group == "sql":
        rows = (result.data or {}).get("rows", [])
        if result.data:
            contexts.append(json.dumps(rows, ensure_ascii=False, default=str))
        semantic = _sql_checks_match(rows, case.get("expected_result_checks", []))
    return {
        "answer": result.answer,
        "contexts": contexts,
        "evidence_sources": [item.source for item in result.evidence],
        "agent_metadata": result.metadata,
        "sql_semantic_correctness": semantic,
        "sql_rows": rows,
    }


def _is_transient_error(error):
    if isinstance(error, (TimeoutError, asyncio.TimeoutError, ConnectionError)):
        return True
    status = getattr(error, "status_code", None) or getattr(error, "status", None)
    text = str(error).casefold()
    if any(token in text for token in ("tokens per day", "daily quota", "quota exceeded", "insufficient_quota")):
        return False
    if status in (408, 409, 429, 500, 502, 503, 504):
        return True
    return any(token in text for token in (
        "http 408", "http 409", "http 429", "http 500", "http 502", "http 503", "http 504",
        "error code: 408", "error code: 409", "error code: 429", "error code: 500",
        "error code: 502", "error code: 503", "error code: 504",
        "rate_limit_exceeded", "temporarily unavailable", "service unavailable",
        "connection error", "connection reset", "connection refused", "timed out", "timeout",
    ))


async def _retry_operation(name, operation, *, retry_delay=2, timeout=180):
    attempts = []
    for number in (1, 2):
        started = time.perf_counter()
        try:
            value = await asyncio.wait_for(operation(), timeout=timeout)
            attempts.append({"attempt": number, "success": True, "transient_failure": False,
                             "elapsed_seconds": round(time.perf_counter() - started, 3), "error": None})
            return value, {"operation": name, "attempts": attempts,
                           "first_attempt_success": attempts[0]["success"], "final_success": True}, None
        except Exception as error:
            transient = _is_transient_error(error)
            attempts.append({"attempt": number, "success": False, "transient_failure": transient,
                             "elapsed_seconds": round(time.perf_counter() - started, 3),
                             "error": f"{type(error).__name__}: {str(error)[:500]}"})
            if number == 1 and transient:
                await asyncio.sleep(retry_delay)
                continue
            return None, {"operation": name, "attempts": attempts,
                          "first_attempt_success": False, "final_success": False}, error


def _metric_eligibility(record):
    answered = isinstance(record.get("answer"), str) and bool(record["answer"].strip())
    contexts = bool(record.get("contexts"))
    reference = isinstance(record.get("reference"), str) and bool(record["reference"].strip())
    return {
        "faithfulness": answered and contexts,
        "answer_relevancy": answered,
        "context_precision": answered and contexts and reference,
    }


def _standardize_record(record):
    result = {
        "case_id": None, "agent": None, "model": None, "question": None,
        "answer": None, "contexts": [], "reference": None, "evidence_sources": [],
        "agent_metadata": {}, "latency_seconds": None, "total_case_seconds": None,
        "langchain_callback_events": 0, "scores": {name: None for name in METRIC_NAMES},
        "metric_eligibility": {name: False for name in METRIC_NAMES},
        "score_errors": {name: None for name in METRIC_NAMES}, "sql_safety_pass": None,
        "sql_semantic_correctness": None, "sql_rows": [], "abstention_expected": False,
        "abstention_observed": None, "hallucination_rate": None,
        "hallucination_review": "manual claim-level review required", "status": "run_error",
        "scoring_status": "not_scored", "error": None, "operation_attempts": [],
    }
    result.update(record)
    for name in ("scores", "metric_eligibility", "score_errors"):
        if not isinstance(result[name], dict):
            result[name] = {}
    for name in METRIC_NAMES:
        result["scores"].setdefault(name, None)
        result["metric_eligibility"].setdefault(name, False)
        result["score_errors"].setdefault(name, None)
    for name in ("contexts", "evidence_sources", "sql_rows", "operation_attempts"):
        if not isinstance(result[name], list):
            result[name] = []
    for name in ("agent_metadata",):
        if not isinstance(result[name], dict):
            result[name] = {}
    for name in ("answer", "reference", "error"):
        if result[name] is not None and not isinstance(result[name], str):
            result[name] = str(result[name])
    if not isinstance(result["langchain_callback_events"], int):
        result["langchain_callback_events"] = 0
    return result


async def _score(metrics, case, answer, contexts, reference, *, judge_enabled=True):
    record = {"answer": answer, "contexts": contexts, "reference": reference}
    eligibility = _metric_eligibility(record)
    values, errors, operations = {name: None for name in METRIC_NAMES}, {name: None for name in METRIC_NAMES}, []
    arguments = {
        "faithfulness": {"user_input": case["question"], "response": answer,
                         "retrieved_contexts": contexts},
        "answer_relevancy": {"user_input": case["question"], "response": answer},
        "context_precision": {"user_input": case["question"], "reference": reference,
                              "retrieved_contexts": contexts},
    }
    for name in METRIC_NAMES:
        if not eligibility[name]:
            continue
        if not judge_enabled or metrics is None:
            errors[name] = "judge_skipped" if not judge_enabled else "judge_unavailable"
            continue
        metric = metrics.get(name)
        if metric is None:
            continue

        async def run_metric():
            result = await metric.ascore(**arguments[name])
            score = float(result.value)
            if not math.isfinite(score):
                raise ValueError("RAGAS returned a non-finite score")
            return score

        value, attempt_log, error = await _retry_operation(
            f"judge.{name}", run_metric,
        )
        operations.append(attempt_log)
        if error is None:
            values[name] = round(value, 4)
        else:
            errors[name] = f"{type(error).__name__}: {str(error)[:500]}"
    return values, eligibility, errors, operations


def _save(records, output, model_key, model_name):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    payload = {"dataset": "commerce-agent-benchmarks-v1", "model_key": model_key,
               "model": model_name, "judge_model": "Luna 5.6 Medium (Codex CLI)",
               "run_date": date.today().isoformat(),
               "evaluation_config": {"cases_per_agent": 25, "agents": ["knowledge", "sql", "report"],
                                     "metrics": list(METRIC_NAMES),
                                     "retry_policy": "one retry for transient failures; two attempts maximum"},
               "summary": _summary(records), "results": records}
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False, default=str), encoding="utf-8")
    temporary.replace(output)


def _summary(records):
    summary = {"case_count": len(records), "by_agent": {}}
    for agent in sorted({record["agent"] for record in records}):
        subset = [record for record in records if record["agent"] == agent]
        metrics = {}
        for name in METRIC_NAMES:
            eligible = [record for record in subset if record["metric_eligibility"][name]]
            values = [record["scores"][name] for record in eligible
                      if isinstance(record["scores"][name], (int, float))
                      and not isinstance(record["scores"][name], bool)
                      and math.isfinite(record["scores"][name])]
            metrics[name] = {"mean": round(sum(values) / len(values), 4) if values else None,
                             "scored_cases": len(values), "eligible_cases": len(eligible),
                             "coverage": round(len(values) / len(eligible), 4) if eligible else None,
                             "score_errors": sum(record["score_errors"][name] is not None for record in eligible)}
        latencies = [record["latency_seconds"] for record in subset
                     if isinstance(record.get("latency_seconds"), (int, float)) and math.isfinite(record["latency_seconds"])]
        summary["by_agent"][agent] = {
            "case_count": len(subset),
            "answered_cases": sum(record.get("status") == "completed" for record in subset),
            "run_errors": sum(record.get("status") == "run_error" for record in subset),
            "mean_agent_latency_seconds": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "latency_cases": len(latencies),
            "ragas": metrics,
        }
    summary["ragas"] = {}
    for name in METRIC_NAMES:
        eligible = [record for record in records if record["metric_eligibility"][name]]
        values = [record["scores"][name] for record in eligible
                  if isinstance(record["scores"][name], (int, float))
                  and not isinstance(record["scores"][name], bool)
                  and math.isfinite(record["scores"][name])]
        summary["ragas"][name] = {"mean": round(sum(values) / len(values), 4) if values else None,
                                   "scored_cases": len(values), "eligible_cases": len(eligible),
                                   "coverage": round(len(values) / len(eligible), 4) if eligible else None,
                                   "score_errors": sum(record["score_errors"][name] is not None for record in eligible)}
    sql_cases = [record for record in records if record["agent"] == "sql"]
    safety = [record["sql_safety_pass"] for record in sql_cases if isinstance(record.get("sql_safety_pass"), bool)]
    semantic = [record["sql_semantic_correctness"] for record in sql_cases if isinstance(record.get("sql_semantic_correctness"), bool)]
    abstention = [record for record in sql_cases if isinstance(record.get("abstention_observed"), bool)]
    summary["sql"] = {
        "safety_pass_rate": round(sum(safety) / len(safety), 4) if safety else None,
        "safety_cases": len(safety),
        "semantic_correctness_rate": round(sum(semantic) / len(semantic), 4) if semantic else None,
        "semantic_cases": len(semantic),
        "abstention_accuracy": round(sum(record["abstention_expected"] == record["abstention_observed"]
                                           for record in abstention) / len(abstention), 4)
        if abstention else None,
        "abstention_cases": len(abstention),
    }
    summary["hallucination_rate"] = None
    summary["hallucination_note"] = "Requires manual claim-level review; not inferred from faithfulness."
    return summary


async def main():
    parser = argparse.ArgumentParser()
    from core.llm.models import BENCHMARK_MODELS
    models = {**BENCHMARK_MODELS, "gpt_oss_120b": {
        "model": "openai/gpt-oss-120b",
        "api_key_env": ("GROQ_API_KEY_2",),
    }, "cloudflare_gemma_4": {
        "provider": "cloudflare",
        "model": "@cf/google/gemma-4-26b-a4b-it",
        "api_key_env": ("CLOUDFLARE_API_TOKEN",),
    }}
    parser.add_argument("--model", choices=models, default="qwen3")
    parser.add_argument("--judge-model", choices=("gpt-5.6-luna",),
                        default=os.getenv("RAGAS_CODEX_MODEL", "gpt-5.6-luna"))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR),
                        help="Use a separate directory to preserve prior benchmark runs")
    parser.add_argument("--agent", choices=("knowledge", "sql", "report"),
                        help="Limit the benchmark to one agent's questions")
    parser.add_argument("--limit-cases", type=int,
                        help="Run only the first N cases per selected agent (for smoke checks)")
    parser.add_argument("--case-id", help="Run one named case (for targeted smoke checks)")
    parser.add_argument("--skip-scoring", action="store_true",
                        help="Run remaining agents without Ragas calls after judge quota is exhausted")
    parser.add_argument("--score-only", action="store_true",
                        help="Retry missing/failed Ragas metrics from saved agent outputs")
    args = parser.parse_args()
    os.environ["RAGAS_CODEX_MODEL"] = args.judge_model
    model_config = models[args.model]
    model_name = model_config["model"]
    output = Path(args.output_dir) / f"results-rerun-{date.today().isoformat()}-{model_name.replace('@', '').replace('/', '-')}.json"

    def make_provider():
        if model_config.get("provider") == "cloudflare":
            from core.llm.Cloudflare_provider import CloudflareProvider
            return CloudflareProvider(model=model_name)
        key = next((os.environ[name] for name in model_config["api_key_env"]
                    if os.environ.get(name)), None)
        if not key:
            raise RuntimeError(f"Missing model API key for {args.model}")
        from core.llm.groq_provider import GroqProvider
        return GroqProvider(model=model_name, api_key=key)

    records = []
    if output.exists():
        records = json.loads(output.read_text(encoding="utf-8")).get("results", [])
        latest = {record["case_id"]: record for record in records}
        records = list(latest.values())
        for record in records:
            if "total_case_seconds" not in record and record.get("latency_seconds") is not None:
                record["total_case_seconds"] = record["latency_seconds"]
                record["latency_seconds"] = None
                record["latency_note"] = "Legacy run included judge time; isolated agent latency was not recorded."
    if args.score_only:
        cases = _load("sql_analytics_agent_benchmark.json")["cases"]
        checks_by_id = {case["id"]: case.get("expected_result_checks", []) for case in cases}
        for record in records:
            if record.get("agent") != "sql" or record.get("sql_semantic_correctness") is not None:
                continue
            rows = record.get("sql_rows")
            if rows is None:
                try:
                    rows = json.loads(record.get("contexts", ["[]"])[-1])
                except (json.JSONDecodeError, IndexError):
                    rows = []
            record["sql_semantic_correctness"] = _sql_checks_match(rows, checks_by_id.get(record["case_id"], []))
            record["sql_rows"] = rows
        _save(records, output, args.model, model_name)
        try:
            metrics = build_ragas_metrics()
        except Exception as error:
            print(f"Ragas unavailable: {type(error).__name__}: {error}", flush=True)
            print("Generated answers will need manual scoring.", flush=True)
            return
        for record in records:
            if not record.get("answer"):
                continue
            names = [name for name in metrics if record.get("scores", {}).get(name) is None]
            if not names:
                continue
            selected = {name: metrics[name] for name in names}
            scores, eligibility, errors, operations = await _score(
                selected, record, record["answer"], record.get("contexts", []), record.get("reference", ""),
            )
            for name in selected:
                record.setdefault("scores", {})[name] = scores[name]
                record.setdefault("score_errors", {})[name] = errors[name]
            record["metric_eligibility"] = eligibility
            record["operation_attempts"] = record.get("operation_attempts", []) + operations
            record["scoring_status"] = "complete" if all(
                not eligibility[name] or record["scores"].get(name) is not None for name in METRIC_NAMES
            ) else "partial"
            record["status"] = "completed"
            record = _standardize_record(record)
            _save(records, output, args.model, model_name)
        print(output)
        return

    datasets = {
        "knowledge": _load("knowledge_agent_benchmark.json")["cases"],
        "sql": _load("sql_analytics_agent_benchmark.json")["cases"],
        "report": _load("report_agent_benchmark.json")["cases"],
    }
    if args.agent:
        datasets = {args.agent: datasets[args.agent]}
    if args.case_id:
        datasets = {group: [case for case in cases if case["id"] == args.case_id]
                    for group, cases in datasets.items()}
        datasets = {group: cases for group, cases in datasets.items() if cases}
        if not datasets:
            parser.error(f"Unknown case ID: {args.case_id}")
    if args.limit_cases is not None:
        if args.limit_cases < 1:
            parser.error("--limit-cases must be at least 1")
        datasets = {group: cases[:args.limit_cases] for group, cases in datasets.items()}
    fixtures = {item["id"]: item for item in _load("report_template_fixtures.json")["templates"]}
    try:
        metrics = None if args.skip_scoring else build_ragas_metrics()
    except Exception as error:
        metrics = None
        print(f"Ragas unavailable: {type(error).__name__}: {error}", flush=True)
        print("Generated answers will need manual scoring.", flush=True)
    provider = make_provider()
    from core.agents.knowledge_agent import KnowledgeAgent
    from core.rag.rag_service import RAGService
    app = create_app(llm=provider, knowledge_agent=KnowledgeAgent(RAGService(llm=provider)))
    completed = {record["case_id"] for record in records if record.get("status") == "completed"}
    async with app.router.lifespan_context(app):
        router = app.state.chat_agent
        for group, cases in datasets.items():
            for case in cases:
                if case["id"] in completed:
                    continue
                records = [record for record in records if record["case_id"] != case["id"]]
                trace = CaseTrace()
                config = {"callbacks": [trace], "tags": ["agent-benchmark", group, case["id"]],
                          "metadata": {"benchmark_case_id": case["id"], "agent": group}}
                request = AgentRequest(question=case["question"], identity=IDENTITY,
                                       metadata={"retrieval_method": "translated_hybrid_rerank"})
                start = time.perf_counter()
                record = _standardize_record({"case_id": case["id"], "agent": group,
                                              "question": case["question"], "model": model_name})
                fixture = fixtures.get(case.get("template_fixture_id"))
                agent_start = time.perf_counter()
                output_data, model_attempts, model_error = await _retry_operation(
                    "model_generation",
                    lambda: _generate_case(app, router, group, case, fixture, request, config),
                )
                record["operation_attempts"].append(model_attempts)
                record["latency_seconds"] = round(time.perf_counter() - agent_start, 3)
                if model_error is not None:
                    record.update({"error": f"{type(model_error).__name__}: {str(model_error)[:500]}",
                                   "langchain_callback_events": trace.events, "status": "run_error",
                                   "total_case_seconds": round(time.perf_counter() - start, 3)})
                else:
                    expected = case.get("expected_facts") or case.get("expected_result_checks") or []
                    reference = json.dumps(expected, ensure_ascii=False, default=str)
                    scoring_started = time.perf_counter()
                    scores, eligibility, score_errors, judge_attempts = await _score(
                        metrics, case, output_data["answer"], output_data["contexts"], reference,
                        judge_enabled=not args.skip_scoring,
                    )
                    record.update(output_data)
                    record["reference"] = reference
                    record["scores"] = scores
                    record["metric_eligibility"] = eligibility
                    record["score_errors"] = score_errors
                    record["operation_attempts"].extend(judge_attempts)
                    metadata = output_data.get("agent_metadata") or {}
                    record["agent_metadata"] = metadata
                    record["sql_safety_pass"] = metadata.get("ok") if group == "sql" else None
                    record["abstention_expected"] = case.get("expected_behavior") == "abstain"
                    record["abstention_observed"] = (
                        not metadata.get("ok", True) if group == "sql" else None
                    )
                    record["langchain_callback_events"] = trace.events
                    record["status"] = "completed"
                    record["scoring_status"] = (
                        "not_applicable" if not any(eligibility.values()) else
                        "complete" if all(not eligibility[name] or scores[name] is not None for name in METRIC_NAMES)
                        else "partial"
                    )
                    record["total_case_seconds"] = round(time.perf_counter() - start, 3)
                record = _standardize_record(record)
                records.append(record)
                _save(records, output, args.model, model_name)
                print(f"{case['id']}: {record['status']} ({record['scoring_status']})", flush=True)
    print(output)


if __name__ == "__main__":
    asyncio.run(main())
