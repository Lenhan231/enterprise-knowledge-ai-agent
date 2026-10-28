"""Two sequential passes of ten review questions against the local Docker API."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CASES = [
    ("K1", "knowledge", "According to the inventory policy, what checks are required before transferring stock between locations?"),
    ("K2", "knowledge", "What is the cycle-count procedure when counted stock differs from the system quantity?"),
    ("K3", "knowledge", "What approvals and evidence are required before a stock adjustment?"),
    ("K4", "knowledge", "How should overlapping stockout and overstock flags be interpreted under the inventory policy?"),
    ("S1", "analytics", "What is the stockout rate by category in the latest inventory snapshot?"),
    ("S2", "analytics", "List the five products with the highest days of supply in the latest inventory snapshot."),
    ("S3", "analytics", "What were total sales revenue and units sold in 2024?"),
    ("M1", "both", "Using the latest inventory data, identify the category with the highest stockout rate, then explain the inventory policy checks before reallocating its stock."),
    ("M2", "both", "List products with overlapping stockout and overstock flags in the latest snapshot, then explain the policy guidance for resolving those overlaps."),
    ("M3", "both", "Show the latest products with reorder flags and explain which inventory-policy checks should precede a replenishment recommendation."),
]


def distribution(values):
    return {"n": len(values), "median_ms": round(statistics.median(values), 2),
            "min_ms": round(min(values), 2), "max_ms": round(max(values), 2)} if values else {"n": 0}


def summarize(rows):
    stages = sorted({k for row in rows for k in (row.get("latency") or {}).get("stages_ms", {})})
    return {
        "requests": len(rows),
        "http_200": sum(row.get("status") == 200 for row in rows),
        "http_e2e": distribution([r["http_elapsed_ms"] for r in rows]),
        "stages": {stage: distribution([r["latency"]["stages_ms"][stage] for r in rows
                    if (r.get("latency") or {}).get("stages_ms", {}).get(stage) is not None]) for stage in stages},
    }


def sample_resources(stop, samples, started):
    while not stop.is_set():
        try:
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}",
                 "enterprise-knowledge-ai-agent-backend-api-1",
                 "enterprise-knowledge-ai-agent-embeddings-1",
                 "enterprise-knowledge-ai-agent-reranker-1",
                 "enterprise-knowledge-ai-agent-document-processing-1"],
                capture_output=True, text=True, check=True, timeout=10,
            )
            samples.append({"elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                            "containers": [json.loads(line) for line in result.stdout.splitlines() if line.strip()]})
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            samples.append({"error_type": type(error).__name__})
        stop.wait(3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/evaluation/docker/review-pipeline-latency-20261026.json")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    username, password = os.environ["DEMO_ADMIN_USERNAME"], os.environ["DEMO_ADMIN_PASSWORD"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": "http://127.0.0.1:8000", "mode": "agentic",
        "retrieval_method": "translated_hybrid_rerank", "role": "admin",
        "configuration": {"concurrency": 1, "passes": 2, "cases_per_pass": 10, "timeout_seconds": 180},
        "boundaries": {
            "http_e2e": "Client HTTP request through authentication, routing, agents and telemetry; login excluded",
            "request_total_ms": "Handler wall time before persistence of the agent event; authentication excluded",
            "stages": "Wall times; null means skipped. Nested stages overlap; parallel agent durations must not be added to infer E2E",
            "first_pass": "First pass after restart; models preloaded. Only the first relevant request is first inference, not all ten",
            "warm_pass": "Same questions and order; includes the existing query-translation cache",
        },
        "results": [], "resource_samples": [],
    }
    started = time.perf_counter()
    stop = threading.Event()
    sampler = threading.Thread(target=sample_resources, args=(stop, report["resource_samples"], started), daemon=True)
    sampler.start()
    try:
        with httpx.Client(base_url=report["base_url"], timeout=180) as client:
            response = client.post("/api/auth/login", json={"username": username, "password": password})
            response.raise_for_status()
            for phase in ("first_pass", "warm_pass"):
                for case_id, expected_route, question in CASES:
                    row = {"phase": phase, "case_id": case_id, "expected_route": expected_route, "question": question}
                    request_started = time.perf_counter()
                    try:
                        response = client.post("/api/agents/chat", json={
                            "question": question, "agent_mode": "agentic", "retrieval_method": report["retrieval_method"],
                        })
                        data = response.json()
                        metadata = data.get("metadata") or {}
                        row.update(status=response.status_code, agent=data.get("agent"),
                                   selected_route=metadata.get("selected_route"), application_ok=metadata.get("ok"),
                                   citation_count=len(data.get("evidence", [])), latency=metadata.get("latency"),
                                   answer_characters=len(data.get("answer", "")), error=data.get("detail"))
                    except (httpx.HTTPError, ValueError) as error:
                        row["error_type"] = type(error).__name__
                    row["http_elapsed_ms"] = round((time.perf_counter() - request_started) * 1000, 2)
                    report["results"].append(row)
                    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                    print(json.dumps({k: row.get(k) for k in ["phase", "case_id", "status", "selected_route", "http_elapsed_ms", "citation_count", "application_ok"]}), flush=True)
    finally:
        stop.set()
        sampler.join(timeout=12)
        report["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        report["summary"] = {phase: summarize([r for r in report["results"] if r["phase"] == phase])
                             for phase in ("first_pass", "warm_pass")}
        report["limitations"] = "Timing smoke, not a quality or load benchmark. No OCR/upload work occurs during chat. Provider/network variance and translation caching affect results. Resource peaks are sampled container-wide, not attributed to E5."
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": report["summary"]}), flush=True)
    return int(any(r.get("status") != 200 or r.get("latency") is None for r in report["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
