"""Repeat review or VietStyle questions against the local Docker API."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import threading
import tempfile
import time
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
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
VIETSTYLE_CASES = [
    ("V1", "knowledge", "Theo Phụ lục B, khoản mua sắm 80 triệu đồng cần những bên nào phê duyệt và cần bao nhiêu báo giá?"),
    ("V2", "knowledge", "Khoản mua sắm đúng 50 triệu và 50.000.001 đồng khác nhau thế nào về phê duyệt và báo giá?"),
    ("V3", "knowledge", "Khoản mua sắm đúng 5 triệu và 5.000.001 đồng khác nhau thế nào về phê duyệt và điều kiện bổ sung?"),
    ("V4", "knowledge", "Theo Phụ lục C, số lượng bằng 0 có đạt điều kiện của yêu cầu mua sắm không? Còn phải kiểm tra gì khác?"),
    ("V5", "knowledge", "Biên bản nhận hàng có lượng giao 100, chấp nhận 90, từ chối 15 có hợp lệ về số lượng không? Vì sao?"),
    ("V6", "knowledge", "Theo Phụ lục B và C, khoản mua sắm 80 triệu cần ai duyệt, điều kiện báo giá là gì và đơn mua hàng chỉ được phát hành khi nào?"),
]


def distribution(values):
    return {"n": len(values), "median_ms": round(statistics.median(values), 2),
            "min_ms": round(min(values), 2), "max_ms": round(max(values), 2)} if values else {"n": 0}


def summarize(rows):
    stages = sorted({k for row in rows for k in (row.get("latency") or {}).get("stages_ms", {})})
    return {
        "requests": len(rows),
        "http_200": sum(row.get("status") == 200 for row in rows),
        "application_ok": sum(row.get("application_ok") is True for row in rows),
        "errors": sum(bool(row.get("error_type")) or row.get("status") != 200 for row in rows),
        "http_e2e": distribution([r["http_elapsed_ms"] for r in rows]),
        "stages": {stage: distribution([r["latency"]["stages_ms"][stage] for r in rows
                    if (r.get("latency") or {}).get("stages_ms", {}).get(stage) is not None]) for stage in stages},
    }


def save_report(path, report):
    # Replace atomically so container termination leaves the last complete report.
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(report, stream, indent=2)
        stream.write("\n")
    temporary.replace(path)


def authenticate(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    response.raise_for_status()
    token = response.cookies.get("enterprise_session")
    if not token:
        raise RuntimeError("Login did not issue a session; benchmark stopped")
    # Secure cookies are not sent over localhost HTTP; reuse the issued session as Bearer.
    client.headers["Authorization"] = "Bearer " + token
    verified = client.get("/api/auth/me")
    verified.raise_for_status()
    if verified.json().get("role") != "admin":
        raise RuntimeError("Benchmark identity is not admin")


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
    parser.add_argument("--cases", choices=("review", "vietstyle"), default="review")
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--pause", type=float, default=0, help="Seconds between requests")
    parser.add_argument("--no-resource-sampling", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.passes <= 10 or not 0 <= args.pause <= 60:
        parser.error("passes must be 1..10 and pause must be 0..60 seconds")
    if args.output.exists():
        parser.error("Choose a new output path; existing measurements are not overwritten")
    cases = VIETSTYLE_CASES if args.cases == "vietstyle" else CASES
    mode = "knowledge" if args.cases == "vietstyle" else "agentic"
    phases = ["first_pass", *["warm_pass" if i == 1 else f"warm_pass_{i}" for i in range(1, args.passes)]]
    load_dotenv(ROOT / ".env")
    username, password = os.environ["DEMO_ADMIN_USERNAME"], os.environ["DEMO_ADMIN_PASSWORD"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": "http://127.0.0.1:8000", "mode": mode,
        "retrieval_method": "translated_hybrid_rerank", "role": "admin",
        "configuration": {"concurrency": 1, "passes": args.passes, "cases_per_pass": len(cases), "timeout_seconds": 180,
                          "pause_seconds": args.pause, "multiquery_env": os.getenv("KNOWLEDGE_MULTIQUERY_ENABLED", "0"),
                          "claim_verification_env": os.getenv("KNOWLEDGE_CLAIM_VERIFICATION_ENABLED", "0")},
        "boundaries": {
            "http_e2e": "Client HTTP request through authentication, routing, agents and telemetry; login excluded",
            "request_total_ms": "Handler wall time before persistence of the agent event; authentication excluded",
            "response_ready_ms": "Handler through telemetry persistence; excludes authentication and HTTP serialization/transport",
            "stages": "Wall times; null means skipped. Nested stages overlap; parallel agent durations must not be added to infer E2E",
            "first_pass": "First pass after restart; models preloaded. Only the first relevant request is first inference, not all ten",
            "warm_pass": "Same questions and order; includes the existing query-translation cache",
            "quality": "application_ok is the server flag, not correctness; inspect saved answers and citations manually",
            "repeatability": "Repeated warm questions, not independent intents or a concurrent load test; first_pass is not necessarily cold",
        },
        "results": [], "resource_samples": [],
    }
    started = time.perf_counter()
    stop = threading.Event()
    sampler = threading.Thread(target=sample_resources, args=(stop, report["resource_samples"], started), daemon=True)
    if not args.no_resource_sampling:
        sampler.start()
    try:
        with httpx.Client(base_url=report["base_url"], timeout=180) as client:
            authenticate(client, username, password)
            for phase in phases:
                for case_id, expected_route, question in cases:
                    row = {"phase": phase, "case_id": case_id, "expected_route": expected_route, "question": question}
                    request_started = time.perf_counter()
                    try:
                        response = client.post("/api/agents/chat", json={
                            "question": question, "agent_mode": mode, "retrieval_method": report["retrieval_method"],
                            "conversation_id": str(uuid4()),
                        })
                        data = response.json()
                        metadata = data.get("metadata") or {}
                        row.update(status=response.status_code, agent=data.get("agent"),
                                   selected_route=metadata.get("selected_route"), application_ok=metadata.get("ok"),
                                   citation_count=len(data.get("evidence", [])), latency=metadata.get("latency"),
                                   answer_characters=len(data.get("answer", "")), error=data.get("detail"),
                                   answer=data.get("answer"), evidence=data.get("evidence", []),
                                   claim_verification=metadata.get("claim_verification"))
                    except (httpx.HTTPError, ValueError) as error:
                        row["error_type"] = type(error).__name__
                    row["http_elapsed_ms"] = round((time.perf_counter() - request_started) * 1000, 2)
                    report["results"].append(row)
                    save_report(args.output, report)
                    print(json.dumps({k: row.get(k) for k in ["phase", "case_id", "status", "selected_route", "http_elapsed_ms", "citation_count", "application_ok"]}), flush=True)
                    if row.get("status") in {401, 403}:
                        raise RuntimeError("Authorization failed during benchmark; stopped")
                    time.sleep(args.pause)
    finally:
        stop.set()
        if not args.no_resource_sampling:
            sampler.join(timeout=12)
        report["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        report["summary"] = {phase: summarize([r for r in report["results"] if r["phase"] == phase])
                             for phase in phases}
        report["by_case"] = {case_id: summarize([r for r in report["results"] if r["case_id"] == case_id])
                             for case_id, _, _ in cases}
        report["limitations"] = "Timing smoke, not a quality or load benchmark. No OCR/upload work occurs during chat. Provider/network variance and translation caching affect results. Resource peaks are sampled container-wide, not attributed to E5."
        save_report(args.output, report)
    print(json.dumps({"output": str(args.output), "summary": report["summary"]}), flush=True)
    return int(any(r.get("status") != 200 or r.get("latency") is None
                   or (args.cases == "vietstyle" and r.get("application_ok") is not True)
                   for r in report["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
