#!/usr/bin/env python3
# scripts/check_apple_retrieval.py
"""Run the cross-document retrieval checkpoint for the Apple corpus."""

from __future__ import annotations

import argparse
import json
import sys
import time
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
    args = parser.parse_args()
    retrieval = RetrievalService()
    failed = False

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

            print(
                f"[{'PASS' if passed else 'FAIL'}] "
                f"{expected_document_id}: {sorted(retrieved_ids)} ({dt:.2f}s)"
            )
    finally:
        retrieval.close()

    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
