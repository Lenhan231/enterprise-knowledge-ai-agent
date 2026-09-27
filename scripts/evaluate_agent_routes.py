#!/usr/bin/env python3
"""Measure live classifier-to-agent routing on the proposal's 12 business cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.agents.intent_classifier import IntentClassifier  # noqa: E402
from core.agents.router import AgentRouter  # noqa: E402
from core.llm.groq_provider import GroqProvider  # noqa: E402
from core.models.agents import AgentRequest, AgentResult  # noqa: E402

_DATASET = REPO_ROOT / "data/evaluation/proposal_business_route_cases.json"
_OUTPUT = REPO_ROOT / "artifacts/evaluation/proposal-business-route-evaluation.json"
_ROUTES = ("knowledge", "analytics", "hybrid", "dashboard", "report")


def score_routes(results: list[dict]) -> dict:
    confusion = {route: {predicted: 0 for predicted in _ROUTES} for route in _ROUTES}
    for result in results:
        expected, predicted = result["expected_route"], result["actual_route"]
        if expected not in confusion or predicted not in _ROUTES:
            raise ValueError(f"Unknown route in evaluation: {expected!r} -> {predicted!r}")
        confusion[expected][predicted] += 1

    total = len(results)
    correct = sum(confusion[route][route] for route in _ROUTES)
    per_route = {}
    for route in _ROUTES:
        support = sum(confusion[route].values())
        predicted = sum(confusion[actual][route] for actual in _ROUTES)
        route_correct = confusion[route][route]
        per_route[route] = {
            "support": support,
            "predicted": predicted,
            "precision": round(route_correct / predicted, 4) if predicted else None,
            "recall": round(route_correct / support, 4) if support else None,
        }
    return {
        "case_count": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else None,
        "confusion_matrix": confusion,
        "per_route": per_route,
    }


class _RouteTarget:
    def __init__(self, name: str):
        self.name = name

    def run(self, _request: AgentRequest) -> AgentResult:
        return AgentResult(answer="", agent=self.name)


class _TrackedProvider:
    def __init__(self, provider):
        self.provider = provider
        self.model_name = provider.model_name
        self.last_error_type = None
        self.last_output = None

    def generate(self, prompt: str) -> str:
        self.last_error_type = None
        self.last_output = None
        try:
            self.last_output = self.provider.generate(prompt)
            return self.last_output
        except Exception as error:
            self.last_error_type = type(error).__name__
            raise

    def close(self) -> None:
        close = getattr(self.provider, "close", None) or getattr(self.provider.client, "close", None)
        if close:
            close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", action="append", help="Run selected case IDs; may be repeated")
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    args = parser.parse_args()
    load_dotenv(REPO_ROOT / ".env", override=True)
    dataset_bytes = _DATASET.read_bytes()
    dataset = json.loads(dataset_bytes)
    cases = dataset["cases"]
    if args.case_id:
        unknown = set(args.case_id) - {case["id"] for case in cases}
        if unknown:
            parser.error(f"unknown case IDs: {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case["id"] in set(args.case_id)]
    provider = _TrackedProvider(GroqProvider())
    classifier = IntentClassifier(llm=provider)
    current_case = None
    fallback_cases: set[str] = set()
    original_fallback = classifier.fallback

    def record_fallback(question: str):
        if current_case:
            fallback_cases.add(current_case)
        return original_fallback(question)

    classifier.fallback = record_fallback
    targets = {route: _RouteTarget(route) for route in _ROUTES}
    router = AgentRouter(
        classifier, targets["knowledge"], targets["analytics"],
        targets["hybrid"], targets["dashboard"], targets["report"],
    )
    results = []
    try:
        for case in cases:
            current_case = case["id"]
            provider.last_error_type = None
            provider.last_output = None
            started = time.perf_counter()
            routed = router.route(AgentRequest(question=case["question"]))
            elapsed = time.perf_counter() - started
            try:
                model_payload = json.loads(
                    (provider.last_output or "").strip()
                    .removeprefix("```json").removesuffix("```").strip()
                )
                model_intent = model_payload.get("intent")
            except (json.JSONDecodeError, AttributeError):
                model_intent = None
            results.append({
                "id": case["id"],
                "category": case["category"],
                "expected_route": case["expected_route"],
                "actual_route": router.last_destination,
                "model_intent": model_intent,
                "passed": router.last_destination == case["expected_route"],
                "fallback_used": case["id"] in fallback_cases,
                "provider_error_type": provider.last_error_type,
                "latency_seconds": round(elapsed, 3),
            })
            print(
                f"{case['id']}: {router.last_destination} "
                f"({'PASS' if results[-1]['passed'] else 'FAIL'}, {elapsed:.1f}s)",
                file=sys.stderr, flush=True,
            )
            if routed.agent != router.last_destination:
                raise RuntimeError("Router destination and selected agent differ")
    finally:
        classifier.close()

    metrics = score_routes(results)
    direct_results = [row for row in results if not row["fallback_used"]]
    fallback_results = [row for row in results if row["fallback_used"]]
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=False,
    ).stdout.strip() or None
    git_dirty = bool(subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=False,
    ).stdout.strip())
    implementation_files = (
        "scripts/evaluate_agent_routes.py",
        "src/core/agents/intent_classifier.py",
        "src/core/agents/router.py",
        "src/core/prompts/intent.py",
    )
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(_DATASET.relative_to(REPO_ROOT)),
        "dataset_id": dataset["dataset_id"],
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "selected_case_ids": [case["id"] for case in cases],
        "label_method": dataset["label_method"],
        "classifier_model": provider.model_name,
        "provider": "Groq Responses API",
        "software_version": git_commit,
        "working_tree_dirty": git_dirty,
        "implementation_sha256": {
            str(Path(path)): hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()
            for path in implementation_files
        },
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "route_metrics": metrics,
        "direct_model_route_metrics": score_routes(direct_results),
        "fallback_route_metrics": score_routes(fallback_results),
        "fallback_count": sum(row["fallback_used"] for row in results),
        "provider_error_count": sum(row["provider_error_type"] is not None for row in results),
        "mean_latency_seconds": round(sum(row["latency_seconds"] for row in results) / len(results), 3) if results else None,
        "limitations": "Measures classifier/router selection against manually mapped proposal-task labels only. Agent tools and answer generation are stubbed; it does not establish task completion, answer quality, domain evidence, or coverage for private enterprise cases.",
        "results": results,
    }
    output = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **metrics, "fallback_count": report["fallback_count"]}, indent=2))
    return 0 if metrics["correct"] == metrics["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
