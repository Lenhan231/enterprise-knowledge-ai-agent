"""Run the 75 supplied agent cases and save grounded, rate-limited Ragas scores."""

from __future__ import annotations

import asyncio
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.main import create_app
from core.models.agents import AgentRequest, VerifiedIdentity
from evaluation.ragas_judge import build_ragas_metrics

DATA = ROOT / "evaluation/agent_benchmarks"
OUTPUT_DIR = ROOT / "artifacts/evaluation/agent-benchmarks-2026-10-25"
IDENTITY = VerifiedIdentity(subject="agent-benchmark", permissions={"analytics:read"})
JUDGE_QUOTA_EXHAUSTED = False


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


async def _score(metrics, case, answer, contexts, reference):
    global JUDGE_QUOTA_EXHAUSTED
    if not answer.strip():
        return {name: None for name in metrics}, {name: "no answer" for name in metrics}
    values, errors = {}, {}
    arguments = {
        "faithfulness": {"user_input": case["question"], "response": answer,
                         "retrieved_contexts": contexts},
        "answer_relevancy": {"user_input": case["question"], "response": answer},
        "context_precision": {"user_input": case["question"], "reference": reference,
                              "retrieved_contexts": contexts},
    }
    for name, metric in metrics.items():
        if JUDGE_QUOTA_EXHAUSTED:
            values[name] = None
            errors[name] = "deferred: Groq judge quota was exhausted"
            continue
        for attempt in range(2):
            try:
                value = await metric.ascore(**arguments[name])
                values[name] = round(float(value.value), 4)
                break
            except Exception as error:
                message = str(error)
                lowered = message.casefold()
                if "429" in lowered or "rate_limit" in lowered or "tokens per day" in lowered:
                    JUDGE_QUOTA_EXHAUSTED = True
                    values[name] = None
                    errors[name] = "deferred: " + message[:450]
                    break
                if attempt == 1 or not any(token in lowered for token in
                                           ("503", "unavailable", "timed out")):
                    values[name] = None
                    errors[name] = type(error).__name__ + ": " + message[:500]
                    break
                await asyncio.sleep(15)
    return values, errors


def _save(records, output, model_key, model_name):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"dataset": "commerce-agent-benchmarks-v1",
                                    "model_key": model_key,
                                    "model": model_name,
                                    "judge_model": os.getenv("RAGAS_JUDGE_MODEL", "openai/gpt-oss-20b"),
                                    "summary": _summary(records),
                                    "results": records},
                                    ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(output)


def _summary(records):
    summary = {"case_count": len(records), "by_agent": {}}
    for agent in sorted({record["agent"] for record in records}):
        subset = [record for record in records if record["agent"] == agent]
        metrics = {}
        for name in ("faithfulness", "answer_relevancy", "context_precision"):
            values = [record.get("scores", {}).get(name) for record in subset
                      if isinstance(record.get("scores", {}).get(name), (int, float))]
            metrics[name] = {"mean": round(sum(values) / len(values), 4) if values else None,
                             "scored_cases": len(values)}
        latencies = [record["latency_seconds"] for record in subset
                     if isinstance(record.get("latency_seconds"), (int, float))]
        summary["by_agent"][agent] = {
            "case_count": len(subset),
            "status_counts": {status: sum(record.get("status") == status for record in subset)
                              for status in sorted({record.get("status", "unknown") for record in subset})},
            "mean_agent_latency_seconds": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "ragas": metrics,
        }
    sql_cases = [record for record in records if record["agent"] == "sql"]
    safety = [record["sql_safety_pass"] for record in sql_cases if record.get("sql_safety_pass") is not None]
    abstention = [record for record in sql_cases if record.get("abstention_observed") is not None]
    summary["sql"] = {
        "safety_pass_rate": round(sum(safety) / len(safety), 4) if safety else None,
        "safety_cases": len(safety),
        "semantic_correctness_rate": round(sum(record["sql_semantic_correctness"]
                                                  for record in sql_cases
                                                  if record.get("sql_semantic_correctness") is not None) /
                                            sum(record.get("sql_semantic_correctness") is not None
                                                for record in sql_cases), 4)
        if any(record.get("sql_semantic_correctness") is not None for record in sql_cases) else None,
        "semantic_cases": sum(record.get("sql_semantic_correctness") is not None for record in sql_cases),
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
    parser.add_argument("--judge-model", default=os.getenv("RAGAS_JUDGE_MODEL", "openai/gpt-oss-20b"))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR),
                        help="Use a separate directory to preserve prior benchmark runs")
    parser.add_argument("--agent", choices=("knowledge", "sql", "report"),
                        help="Limit the benchmark to one agent's questions")
    parser.add_argument("--skip-scoring", action="store_true",
                        help="Run remaining agents without Ragas calls after judge quota is exhausted")
    parser.add_argument("--score-only", action="store_true",
                        help="Retry missing/failed Ragas metrics from saved agent outputs")
    args = parser.parse_args()
    os.environ["RAGAS_JUDGE_MODEL"] = args.judge_model
    model_config = models[args.model]
    model_name = model_config["model"]
    output = Path(args.output_dir) / f"results-{model_name.replace('@', '').replace('/', '-')}.json"

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
            scores, errors = await _score(selected, record, record["answer"],
                                          record.get("contexts", []), record.get("reference", ""))
            record.setdefault("scores", {}).update(scores)
            record.setdefault("score_errors", {}).update(errors)
            record["status"] = "scored" if all(record["scores"].get(name) is not None for name in metrics) else "score_partial"
            _save(records, output, args.model, model_name)
            if JUDGE_QUOTA_EXHAUSTED:
                break
        print(output)
        return

    datasets = {
        "knowledge": _load("knowledge_agent_benchmark.json")["cases"],
        "sql": _load("sql_analytics_agent_benchmark.json")["cases"],
        "report": _load("report_agent_benchmark.json")["cases"],
    }
    if args.agent:
        datasets = {args.agent: datasets[args.agent]}
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
    completed = {record["case_id"] for record in records if record.get("answer")}
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
                record = {"case_id": case["id"], "agent": group, "question": case["question"],
                          "model": model_name}
                try:
                    agent_start = time.perf_counter()
                    if group == "report":
                        fixture = fixtures[case["template_fixture_id"]]
                        async def generate(_input):
                            return await app.state.report_agent.generate_from_template(
                                request, "benchmark.md", _report_template(fixture),
                            )
                        runnable = RunnableLambda(generate)
                        report_result, payload, media = await runnable.ainvoke({}, config=config)
                        answer = _plain_report(payload, media)
                        contexts = [item.content or json.dumps(item.metadata, ensure_ascii=False, default=str)
                                    for item in report_result.evidence]
                        result_metadata = report_result.metadata
                        evidence = [item.source for item in report_result.evidence]
                    else:
                        mode = "knowledge" if group == "knowledge" else "sql"
                        result = await router.run_mode(request, mode, config=config)
                        answer = result.answer
                        contexts = [item.content or json.dumps(item.metadata, ensure_ascii=False, default=str)
                                    for item in result.evidence]
                        if group == "sql" and result.data:
                            contexts.append(json.dumps(result.data.get("rows", []), ensure_ascii=False, default=str))
                        if group == "sql":
                            rows = result.data.get("rows", [])
                            record["sql_semantic_correctness"] = _sql_checks_match(
                                rows, case.get("expected_result_checks", []),
                            )
                            record["sql_rows"] = rows
                        evidence = [item.source for item in result.evidence]
                        result_metadata = result.metadata
                    agent_latency = round(time.perf_counter() - agent_start, 3)
                    expected = case.get("expected_facts") or case.get("expected_result_checks") or []
                    reference = json.dumps(expected, ensure_ascii=False, default=str)
                    if metrics is None:
                        scores = {"faithfulness": None, "answer_relevancy": None, "context_precision": None}
                        score_errors = {name: "deferred: manual scoring required; Ragas was skipped" for name in scores}
                    else:
                        scores, score_errors = await _score(metrics, case, answer, contexts, reference)
                    record.update({
                        "answer": answer,
                        "contexts": contexts,
                        "reference": reference,
                        "evidence_sources": evidence,
                        "agent_metadata": result_metadata,
                        "latency_seconds": agent_latency,
                        "total_case_seconds": round(time.perf_counter() - start, 3),
                        "langchain_callback_events": trace.events,
                        "scores": scores,
                        "score_errors": score_errors,
                        "sql_safety_pass": (result_metadata.get("ok") if group == "sql" else None),
                        "abstention_expected": case.get("expected_behavior") == "abstain",
                        "abstention_observed": (not result_metadata.get("ok", True) if group == "sql" else None),
                        "hallucination_rate": None,
                        "hallucination_review": "manual claim-level review required",
                        "status": ("generated" if args.skip_scoring else
                                   "scored" if not score_errors else "score_partial"),
                    })
                except Exception as error:
                    record.update({"latency_seconds": round(time.perf_counter() - start, 3),
                                   "error": type(error).__name__ + ": " + str(error)[:500],
                                   "langchain_callback_events": trace.events, "status": "run_error"})
                records.append(record)
                _save(records, output, args.model, model_name)
                print(f"{case['id']}: {record['status']}", flush=True)
    print(output)


if __name__ == "__main__":
    asyncio.run(main())
