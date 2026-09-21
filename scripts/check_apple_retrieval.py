#!/usr/bin/env python3
# scripts/check_apple_retrieval.py
"""Run the cross-document retrieval checkpoint for the Apple corpus."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.retrieval.retrieval_service import RetrievalService  # noqa: E402
from core.retrieval.retrieval import RetrievalRequest  # noqa: E402


CASES = {
    "APL-CMP-003": (
        "What responsibilities do third parties have under "
        "Apple's Anti-Corruption Policy?"
    ),
    "APL-CMP-004": (
        "What standards must third parties working with Apple follow?"
    ),
    "APL-PRC-002": (
        "What steps must a supplier complete in Supplier Connect "
        "before receiving an SAP vendor number?"
    ),
    "APL-PRC-015": (
        "What is the most reliable way to submit invoices to Apple?"
    ),
    "APL-ENV-002": (
        "By how much did Apple reduce gross greenhouse gas emissions "
        "compared with its 2015 baseline?"
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("artifacts/retrieval/apple_retrieval_results.json"))
    args = parser.parse_args()
    retrieval = RetrievalService()
    failed = False
    results = []

    try:
        for expected_document_id, question in CASES.items():
            t0 = time.time()
            result = retrieval.retrieve(
                RetrievalRequest(query=question, top_k=args.limit)
            )
            dt = time.time() - t0
            retrieved_ids = {
                context.document_id
                for context in result.results
            }
            passed = expected_document_id in retrieved_ids
            failed |= not passed

            print(f"\nQUESTION: {question}")
            for r in result.results:
                print(f"  Rank {r.rank} | Score {r.score:.4f} | {r.source} | {result.latency_ms:.1f}ms")

            print(
                f"[{'PASS' if passed else 'FAIL'}] "
                f"{expected_document_id}: {sorted(retrieved_ids)} ({dt:.2f}s)"
            )
            
            results.append({
                "expected_document_id": expected_document_id,
                "question": question,
                "passed": passed,
                "retrieved_ids": sorted(retrieved_ids),
                "total_latency_ms": round(dt * 1000, 2),
                "chunks": [
                    {
                        "rank": r.rank,
                        "score": r.score,
                        "document_id": r.document_id,
                        "source": r.source,
                        "latency_ms": result.latency_ms,
                    }
                    for r in result.results
                ]
            })
    finally:
        retrieval.close()
        
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "top_k": args.limit,
        "summary": {
            "total": len(results),
            "passed": sum(r["passed"] for r in results),
            "failed": sum(not r["passed"] for r in results),
        },
        "results": results,
    }
    
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nEvidence written to: {args.output}")

    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
