#!/usr/bin/env python3
"""Measure local ASGI health, dashboard, and analytics endpoints under light load."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import resource
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.main import app  # noqa: E402


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * p)
    return round(ordered[index], 2)


async def request_once(client: httpx.AsyncClient, path: str) -> dict:
    started = time.perf_counter()
    try:
        response = await client.get(path)
        return {
            "path": path,
            "status_code": response.status_code,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "response_bytes": len(response.content),
            "error": None if response.is_success else response.text[:250],
        }
    except Exception as error:
        return {
            "path": path,
            "status_code": None,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "response_bytes": 0,
            "error": f"{type(error).__name__}: {error}",
        }


async def run_level(client: httpx.AsyncClient, paths: list[str], concurrency: int, iterations: int) -> dict:
    requests = [paths[index % len(paths)] for index in range(concurrency * iterations)]
    started = time.perf_counter()
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(path):
        async with semaphore:
            return await request_once(client, path)

    results = await asyncio.gather(*(bounded(path) for path in requests))
    elapsed = time.perf_counter() - started
    latencies = [row["latency_ms"] for row in results]
    return {
        "concurrency": concurrency,
        "request_count": len(results),
        "elapsed_seconds": round(elapsed, 3),
        "throughput_requests_per_second": round(len(results) / elapsed, 3) if elapsed else None,
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 2) if latencies else None,
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies), 2) if latencies else None,
        },
        "success_count": sum(row["status_code"] is not None and 200 <= row["status_code"] < 300 for row in results),
        "failure_count": sum(row["status_code"] is None or not 200 <= row["status_code"] < 300 for row in results),
        "status_counts": {str(code): sum(row["status_code"] == code for row in results) for code in sorted({row["status_code"] for row in results}, key=str)},
        "failures": [row for row in results if row["error"]],
    }


async def main_async(args) -> int:
    load_dotenv(REPO_ROOT / ".env", override=True)
    username = os.getenv("DEMO_ANALYST_USERNAME")
    password = os.getenv("DEMO_ANALYST_PASSWORD")
    if not username or not password:
        raise RuntimeError("DEMO_ANALYST_USERNAME/PASSWORD must be configured in .env")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=30) as client:
        login = await client.post("/api/auth/login", json={"username": username, "password": password})
        if login.status_code != 200:
            raise RuntimeError(f"Analyst login failed with HTTP {login.status_code}")
        user = await client.get("/api/auth/me")
        if user.status_code != 200 or user.json().get("role") != "finance_analyst":
            raise RuntimeError("Authenticated benchmark identity is not a finance_analyst")

        paths = ["/health", "/api/dashboard", "/api/analytics"]
        warmups = [await request_once(client, path) for path in paths]
        failed_warmups = [row for row in warmups if row["error"]]
        levels = []
        for concurrency in args.concurrency:
            levels.append(await run_level(client, paths, concurrency, args.iterations))

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark": "local FastAPI ASGI endpoints; no external network hop",
        "role": "finance_analyst",
        "paths": paths,
        "warmup": warmups,
        "configuration": {"concurrency_levels": args.concurrency, "iterations_per_worker": args.iterations, "timeout_seconds": 30},
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "gpu_utilization": None,
            "gpu_note": "Not sampled; no CUDA GPU was available in the verified host environment.",
        },
        "results": levels,
        "limitations": "In-process ASGI benchmark against the configured database, not a deployed server/network benchmark. It measures health, dashboard and analytics only; no upload, concurrent document processing, QA generation, multi-user authorization matrix, or production-scale load. Use a dedicated load-test environment before capacity claims.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "results": levels}, ensure_ascii=False, indent=2))
    return 1 if failed_warmups or any(level["failure_count"] for level in levels) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 2, 4])
    parser.add_argument("--iterations", type=int, default=3, help="Requests per worker at each concurrency level")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "artifacts/evaluation/vinamilk-api-load-smoke.json")
    args = parser.parse_args()
    if args.iterations < 1 or not args.concurrency or any(value < 1 or value > 16 for value in args.concurrency):
        parser.error("iterations must be positive and concurrency levels must be in [1, 16]")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
