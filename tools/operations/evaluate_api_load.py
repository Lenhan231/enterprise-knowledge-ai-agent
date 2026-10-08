#!/usr/bin/env python3
"""Measure health, dashboard, and analytics endpoints through ASGI or HTTP."""

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
from urllib.parse import urlsplit

from dotenv import load_dotenv
import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.main import app  # noqa: E402


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * p)
    return round(ordered[index], 2)


def validate_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("base URL must be an http(s) origin without embedded credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("base URL must be an origin only, without path, query or fragment")
    return f"{parsed.scheme}://{parsed.netloc}"


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


def summarize_by_path(results: list[dict]) -> dict:
    summary = {}
    for path in sorted({row["path"] for row in results}):
        rows = [row for row in results if row["path"] == path]
        latencies = [row["latency_ms"] for row in rows]
        summary[path] = {
            "request_count": len(rows),
            "success_count": sum(row["status_code"] is not None and 200 <= row["status_code"] < 300 for row in rows),
            "failure_count": sum(row["status_code"] is None or not 200 <= row["status_code"] < 300 for row in rows),
            "latency_ms": {
                "mean": round(statistics.fmean(latencies), 2) if latencies else None,
                "p50": percentile(latencies, 0.5),
                "p95": percentile(latencies, 0.95),
                "max": round(max(latencies), 2) if latencies else None,
            },
        }
    return summary


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
        "by_path": summarize_by_path(results),
        "failures": [row for row in results if row["error"]],
    }


async def main_async(args) -> int:
    load_dotenv(REPO_ROOT / ".env", override=True)
    username = os.getenv("DEMO_ANALYST_USERNAME")
    password = os.getenv("DEMO_ANALYST_PASSWORD")
    if not username or not password:
        raise RuntimeError("DEMO_ANALYST_USERNAME/PASSWORD must be configured in .env")

    base_url = validate_base_url(args.base_url)
    transport = None if base_url else httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=base_url or "http://testserver", timeout=30) as client:
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
        "benchmark": "authenticated HTTP endpoints on configured server" if base_url else "local FastAPI ASGI endpoints; no external network hop",
        "base_url": base_url,
        "role": "finance_analyst",
        "paths": paths,
        "warmup": warmups,
        "configuration": {"concurrency_levels": args.concurrency, "iterations_per_worker": args.iterations, "timeout_seconds": 30},
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "database_max_connections_per_process": int(
                os.getenv("DATABASE_MAX_CONNECTIONS_PER_PROCESS", "10")
            ),
            "gpu_utilization": None,
            "gpu_note": "Not sampled; no CUDA GPU was available in the verified host environment.",
        },
        "results": levels,
        "limitations": "Measures health, dashboard and analytics only; no upload, concurrent document processing, QA generation, multi-user authorization matrix, or production-scale load. HTTP mode exercises the configured server over its network interface but does not by itself establish deployed scalability or capacity.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "results": levels}, ensure_ascii=False, indent=2))
    return 1 if failed_warmups or any(level["failure_count"] for level in levels) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 2, 4])
    parser.add_argument("--iterations", type=int, default=3, help="Requests per worker at each concurrency level")
    parser.add_argument("--base-url", help="Optional running HTTP server origin; default benchmarks the app in-process via ASGI")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "artifacts/evaluation/operations/api-load-smoke.json")
    args = parser.parse_args()
    if args.iterations < 1 or not args.concurrency or any(value < 1 or value > 16 for value in args.concurrency):
        parser.error("iterations must be positive and concurrency levels must be in [1, 16]")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
