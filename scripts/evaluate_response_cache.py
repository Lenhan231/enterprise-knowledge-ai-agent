#!/usr/bin/env python3
"""Verify grounded-answer cache behavior through authenticated /api/ask."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from dotenv import load_dotenv
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.main import app  # noqa: E402
from core.agents.intent_classifier import IntentClassifier as IntentClassifierImpl  # noqa: E402
from core.rag.rag_service import _RESPONSE_CACHE, _RESPONSE_CACHE_LOCK  # noqa: E402

CASES = ROOT / "data/evaluation/vinamilk_qa_cases.json"
OUTPUT = ROOT / "artifacts/evaluation/vinamilk-response-cache-api-smoke.json"


class CitationStub:
    model_name = "deterministic-response-cache-evaluation-stub"
    reasoning_effort = "none"
    calls = 0

    def generate(self, prompt: str) -> str:
        type(self).calls += 1
        return "The retrieved source provides evidence relevant to the question [S1]."

    def close(self) -> None:
        pass


class FallbackClassifier:
    def classify(self, question: str):
        return IntentClassifierImpl.fallback(question)

    def close(self) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    load_dotenv(ROOT / ".env", override=True)
    username, password = os.getenv("DEMO_VIEWER_USERNAME"), os.getenv("DEMO_VIEWER_PASSWORD")
    if not username or not password:
        parser.error("DEMO_VIEWER_USERNAME and DEMO_VIEWER_PASSWORD are required")
    cases_data = json.loads(CASES.read_text(encoding="utf-8"))
    case = next(item for item in cases_data["cases"] if item["id"] == "employee-product-nutrition")
    CitationStub.calls = 0
    with _RESPONSE_CACHE_LOCK:
        _RESPONSE_CACHE.clear()

    results = []
    patchers = [
        patch("core.rag.rag_service.GroqProvider", CitationStub),
        patch("core.agents.sql_analytics_agent.GroqProvider", CitationStub),
        patch("core.agents.report_agent.GroqProvider", CitationStub),
        patch("app.main.IntentClassifier", FallbackClassifier),
        patch("app.main.AgentRunRepository", return_value=Mock()),
    ]
    try:
        for item in patchers:
            item.start()
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": username, "password": password})
            if login.status_code != 200:
                raise RuntimeError(f"Viewer login failed with HTTP {login.status_code}")
            for attempt in ("miss", "hit"):
                started = time.perf_counter()
                response = client.post("/api/ask", json={"question": case["question"]})
                elapsed = time.perf_counter() - started
                payload = response.json()
                answer = payload.get("answer", "")
                results.append({
                    "attempt": attempt,
                    "status_code": response.status_code,
                    "latency_ms": round(elapsed * 1000, 2),
                    "agent": payload.get("agent"),
                    "citation_count": len(payload.get("citations", [])),
                    "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
                })
            client.post("/api/auth/logout")
    finally:
        for item in reversed(patchers):
            item.stop()

    passed = (
        all(item["status_code"] == 200 for item in results)
        and all(item["citation_count"] > 0 for item in results)
        and results[0]["answer_sha256"] == results[1]["answer_sha256"]
        and CitationStub.calls == 1
    )
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "route": "POST /api/ask",
        "case_id": case["id"],
        "case_sha256": hashlib.sha256(json.dumps(case, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "actor_role": "employee",
        "database_retrieval": "live role-filtered retrieval; no database writes (agent telemetry mocked)",
        "intent_classifier": "deterministic fallback stub",
        "answer_model": "deterministic citation stub; not a provider-quality or provider-latency benchmark",
        "response_cache_ttl_seconds": 60,
        "results": results,
        "model_generation_calls": CitationStub.calls,
        "cache_hit_verified": passed,
        "limitations": "The repeated request re-runs authentication, routing, database retrieval and embedding. The deterministic answer model isolates cache wiring only; timing does not estimate real provider latency savings. This run is a single-process authenticated integration smoke, not a concurrent load benchmark.",
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "cache_hit_verified": passed, "model_generation_calls": CitationStub.calls, "latencies_ms": [item["latency_ms"] for item in results]}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
