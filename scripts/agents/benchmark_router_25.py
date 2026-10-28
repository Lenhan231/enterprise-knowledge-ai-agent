#!/usr/bin/env python3
"""Reproducible, appendable 50-case router-only benchmark for the current router."""

from __future__ import annotations

import asyncio
import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env", override=True)
os.environ["LANGSMITH_TRACING"] = "false"

from core.agents.intent_classifier import IntentClassifier  # noqa: E402
from core.agents.router import AgentRouter  # noqa: E402
from core.llm.groq_provider import GroqProvider  # noqa: E402
from core.models.agents import AgentRequest, AgentResult  # noqa: E402
from core.models.intent import IntentResult  # noqa: E402
from core.prompts.intent import INTENT_CLASSIFIER_PROMPT  # noqa: E402

DATASET = ROOT / "data/evaluation/router_benchmark_50.json"
OUT = ROOT / "artifacts/evaluation/router-benchmark-50-2026-10-25"
PREVIOUS_OUT = ROOT / "artifacts/evaluation/router-benchmark-25-2026-10-25"
LABELS = ("knowledge", "analytics", "hybrid")
FILES = ("scripts/agents/benchmark_router_25.py", "src/core/agents/intent_classifier.py",
         "src/core/agents/router.py", "src/core/prompts/intent.py", "src/core/models/intent.py")


class Target:
    def __init__(self, name: str):
        self.name = name

    async def run(self, _request: AgentRequest) -> AgentResult:
        return AgentResult(answer="", agent=self.name)


class TrackedProvider:
    def __init__(self, provider):
        self.provider = provider
        self.model_name = provider.model_name
        self.last_error = None
        self.last_raw = None

    def generate(self, prompt):
        self.last_error = None
        self.last_raw = None
        try:
            self.last_raw = self.provider.generate(prompt)
            return self.last_raw
        except Exception as error:
            self.last_error = type(error).__name__
            raise

    def close(self):
        self.provider.close()


def parse_raw(raw):
    try:
        payload = json.loads((raw or "").strip().removeprefix("```json").removesuffix("```").strip())
        return IntentResult.model_validate(payload), None
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"


def route_intent(intent):
    if intent is None:
        return None
    if intent.output_mode == "dashboard" or intent.intent in {"dashboard", "report"}:
        return intent.intent
    if intent.needs_knowledge and intent.needs_sql:
        return "hybrid"
    return "analytics" if intent.needs_sql else "knowledge"


def scores(rows):
    matrix = {actual: {pred: 0 for pred in LABELS} for actual in LABELS}
    out_of_scope = {actual: {} for actual in LABELS}
    for row in rows:
        expected, predicted = row["expected_route"], row["predicted_route"]
        if expected not in LABELS:
            raise ValueError(f"Unscorable route: {expected!r} -> {predicted!r}")
        if predicted in LABELS:
            matrix[expected][predicted] += 1
        else:
            key = str(predicted or "unclassified")
            out_of_scope[expected][key] = out_of_scope[expected].get(key, 0) + 1
    total = len(rows)
    correct = sum(matrix[label][label] for label in LABELS)
    per_class = {}
    for label in LABELS:
        support = sum(matrix[label].values()) + sum(out_of_scope[label].values())
        predicted_n = sum(matrix[x][label] for x in LABELS)
        tp = matrix[label][label]
        precision = tp / predicted_n if predicted_n else None
        recall = tp / support if support else None
        f1 = (2 * precision * recall / (precision + recall)
              if precision is not None and recall is not None and precision + recall else 0.0
              if precision is not None and recall is not None else None)
        per_class[label] = {"support": support, "precision": precision, "recall": recall, "f1": f1}
    macro = [v["f1"] for v in per_class.values() if v["f1"] is not None]
    weighted = [v["f1"] * v["support"] for v in per_class.values() if v["f1"] is not None]
    return {"n": total, "correct": correct, "incorrect": total - correct,
            "accuracy": correct / total if total else None, "confusion_matrix": matrix,
            "out_of_scope_predictions_by_expected": out_of_scope,
            "per_class": per_class, "macro_f1": statistics.mean(macro) if macro else None,
            "weighted_f1": sum(weighted) / sum(v["support"] for v in per_class.values()) if total else None,
            "zero_division": "precision/recall undefined as null when denominator is zero; F1 is 0 when both are defined and sum to zero"}


def latency_stats(rows):
    values = sorted(x["latency_ms"] for x in rows)
    if not values:
        return None
    p95 = values[max(0, math.ceil(.95 * len(values)) - 1)]
    return {"mean_ms": statistics.mean(values), "median_ms": statistics.median(values),
            "p95_ms_nearest_rank": p95, "min_ms": values[0], "max_ms": values[-1]}


def draw_confusion(matrix, path):
    # A compact 3x3 raster avoids adding a plotting dependency to the repository.
    from PIL import Image, ImageDraw, ImageFont
    cell, margin = 140, 120
    image = Image.new("RGB", (margin + cell * 3 + 20, margin + cell * 3 + 20), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=14)
    draw.text((12, 10), "Expected rows / predicted columns", fill="black", font=small)
    for j, label in enumerate(LABELS):
        draw.text((margin + j * cell + 20, margin - 28), label, fill="black", font=small)
    for i, actual in enumerate(LABELS):
        draw.text((8, margin + i * cell + 55), actual, fill="black", font=small)
        for j, predicted in enumerate(LABELS):
            x, y = margin + j * cell, margin + i * cell
            count = matrix[actual][predicted]
            draw.rectangle((x, y, x + cell, y + cell), fill="#dcefe4" if i == j else "#f4e4e2", outline="#555")
            draw.text((x + 60, y + 48), str(count), fill="black", font=font)
    image.save(path)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--append", action="store_true",
                        help="run only cases absent from the saved results, then recompute combined metrics")
    args = parser.parse_args()
    dataset_bytes = DATASET.read_bytes()
    cases = json.loads(dataset_bytes)["cases"]
    previous = None
    previous_path = OUT / "results.json"
    if args.append and not previous_path.is_file():
        previous_path = PREVIOUS_OUT / "results.json"
    if args.append:
        if not previous_path.is_file():
            parser.error(f"--append requires existing results at {previous_path}")
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        already_run = {row["case_id"] for row in previous["records"]["production"]}
        dataset_ids = {case["id"] for case in cases}
        if not already_run <= dataset_ids:
            parser.error("saved results contain cases missing from the current dataset")
        cases = [case for case in cases if case["id"] not in already_run]
        if not cases:
            parser.error("no new cases to append")
    provider = TrackedProvider(GroqProvider())
    classifier = IntentClassifier(llm=provider)
    targets = {label: Target(label) for label in (*LABELS, "dashboard", "report")}
    router = AgentRouter(classifier, targets["knowledge"], targets["analytics"],
                         dashboard_agent=targets["dashboard"], report_agent=targets["report"])
    runs = {name: [] for name in ("rule_based_only", "raw_llm", "production")}
    raw_payload_errors = 0
    normalization_count = 0
    normalization_reasons = {}
    try:
        for case in cases:
            q = case["question"]
            t0 = time.perf_counter_ns()
            rule_intent = classifier.fallback(q)
            rule_ms = (time.perf_counter_ns() - t0) / 1e6
            runs["rule_based_only"].append(record(case, route_intent(rule_intent), rule_intent, rule_intent,
                                                   rule_ms, False, False, None))

            provider.last_error = provider.last_raw = None
            t0 = time.perf_counter_ns()
            raw_text = None
            parse_error = None
            try:
                raw_text = provider.generate(INTENT_CLASSIFIER_PROMPT.format(question=q))
                raw_intent, parse_error = parse_raw(raw_text)
            except Exception as error:
                raw_intent = None
                parse_error = f"{type(error).__name__}: {error}"
            raw_ms = (time.perf_counter_ns() - t0) / 1e6
            if parse_error:
                raw_payload_errors += 1
            runs["raw_llm"].append(record(case, route_intent(raw_intent), raw_intent, raw_intent,
                                          raw_ms, False, False, provider.last_error or parse_error))

            provider.last_error = provider.last_raw = None
            original_classify = classifier.classify
            captured = {}
            def timed_classify(question):
                started = time.perf_counter_ns()
                classified = original_classify(question)
                captured["intent"] = classified
                captured["classifier_latency_ms"] = (time.perf_counter_ns() - started) / 1e6
                captured["raw_text"] = provider.last_raw
                captured["provider_error"] = provider.last_error
                return classified
            classifier.classify = timed_classify
            route_started = time.perf_counter_ns()
            await router.route(AgentRequest(question=q))
            route_ms = (time.perf_counter_ns() - route_started) / 1e6
            classifier.classify = original_classify
            intent = captured["intent"]
            classified_ms = captured["classifier_latency_ms"]
            # Raw-call data and production-call data are captured independently.
            prod_raw, prod_parse_error = parse_raw(captured["raw_text"])
            normalization_override = bool(prod_raw and not captured["provider_error"] and intent.fallback)
            normalization_count += normalization_override
            if normalization_override:
                normalization_reasons[case["id"]] = {
                    "raw_intent": prod_raw.intent, "normalized_intent": intent.intent,
                    "reason": "The rule-based result replaced the parsed model result; this was not a provider failure.",
                }
            runs["production"].append(record(case, router.last_destination, intent, prod_raw,
                route_ms, intent.fallback, normalization_override,
                captured["provider_error"] or (prod_parse_error if prod_raw is None and not intent.fallback else None),
                classifier_latency_ms=classified_ms, route_latency_ms=route_ms))
            print(f"{case['id']}: rule={runs['rule_based_only'][-1]['predicted_route']}; raw={runs['raw_llm'][-1]['predicted_route']}; production={router.last_destination}", file=sys.stderr, flush=True)
    finally:
        await router.close()

    for records in runs.values():
        for row in records:
            row["correct"] = row["predicted_route"] == row["expected_route"]
    for name, records in runs.items():
        for row in records:
            row["configuration"] = name
    if previous:
        combined = {name: previous["records"][name] + runs[name] for name in runs}
    else:
        combined = runs
    metrics = {name: scores(rows) for name, rows in combined.items()}
    production = combined["production"]
    fallbacks = [r for r in production if r["fallback_used"]]
    nonfallbacks = [r for r in production if not r["fallback_used"]]
    difficulties = {}
    for level in ("easy", "medium", "hard"):
        subset = [r for r in production if r["difficulty"] == level]
        difficulties[level] = {"n": len(subset), "correct": sum(r["correct"] for r in subset),
                               "accuracy": sum(r["correct"] for r in subset) / len(subset) if subset else None}
    confidences = {}
    for name, rows in combined.items():
        confidences[name] = {key: (statistics.mean([r["confidence"] for r in rows if r["correct"] == correct and r["confidence"] is not None])
                                   if any(r["correct"] == correct and r["confidence"] is not None for r in rows) else None)
                             for key, correct in (("correct", True), ("incorrect", False))}
    now = datetime.now(timezone.utc).isoformat()
    run_history = (previous.get("run_history") or [{
        "created_at_utc": previous["created_at_utc"],
        "dataset_sha256": previous["dataset_sha256"],
        "case_ids": previous["selected_case_ids"],
    }]) if previous else []
    run_history.append({"created_at_utc": now, "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
                        "case_ids": [c["id"] for c in cases], "appended": bool(previous)})
    report = {
        "created_at_utc": now, "dataset_id": json.loads(dataset_bytes)["dataset_id"],
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "selected_case_ids": [c["id"] for c in json.loads(dataset_bytes)["cases"]],
        "evaluated_case_ids_this_run": [c["id"] for c in cases],
        "run_history": run_history,
        "model": provider.model_name, "provider": "Groq Responses API", "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "implementation_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES},
        "metrics": metrics, "latency": {name: latency_stats(rows) for name, rows in combined.items()},
        "fallback": {"count": len(fallbacks), "rate": len(fallbacks) / len(production),
                      "accuracy_fallback": sum(r["correct"] for r in fallbacks) / len(fallbacks) if fallbacks else None,
                      "accuracy_nonfallback": sum(r["correct"] for r in nonfallbacks) / len(nonfallbacks) if nonfallbacks else None,
                      "provider_failures": sum(r["provider_error"] is not None and r["fallback_used"] for r in production),
                      "normalization_overrides": normalization_count + (previous["fallback"]["normalization_overrides"] if previous else 0),
                      "normalization_cases": {**(previous["fallback"].get("normalization_cases", {}) if previous else {}), **normalization_reasons}},
        "difficulty": difficulties, "confidence": confidences,
        "raw_llm_payload_error_count": raw_payload_errors + (previous.get("raw_llm_payload_error_count", 0) if previous else 0),
        "records": combined,
        "limitations": ["Router-only phase uses stub destination agents; no retrieval, SQL, answer generation, evidence authorization, or answer quality was measured.",
                        "Each configuration makes an independent model call; nondeterministic provider responses can differ.",
                        "Confidence is the model-reported value and is not calibrated.",
                        "P95 uses nearest-rank method. Router production latency combines classifier and LangGraph stub dispatch; no downstream agent execution is included."]
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name in combined:
        draw_confusion(metrics[name]["confusion_matrix"], OUT / f"confusion-{name}.png")
    print(json.dumps({"output": str(OUT), "metrics": metrics, "latency": report["latency"], "fallback": report["fallback"]}, indent=2))


def record(case, predicted, intent, raw_intent, elapsed, fallback, override, error, **extra):
    return {"case_id": case["id"], "question": case["question"], "expected_route": case["expected_route"],
            "predicted_route": predicted, "raw_model_intent": raw_intent.intent if raw_intent else None,
            "normalized_intent": intent.intent if intent else None,
            "normalized_route": route_intent(intent),
            "difficulty": case["difficulty"], "language": "en", "correct": None,
            "confidence": intent.confidence if intent else None, "fallback_used": fallback,
            "normalization_override": override, "provider_error": error, "latency_ms": elapsed,
            "configuration": None, **extra}


if __name__ == "__main__":
    asyncio.run(main())
