#!/usr/bin/env python3
# scripts/check_apple_retrieval.py
"""Run the cross-document retrieval checkpoint for the Apple corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.retrieval import RetrievalService  # noqa: E402
from core.models.retrieval import RetrievalRequest  # noqa: E402


QUESTIONS = (
    "What standards must third parties working with Apple follow?",
    "What obligations does a supplier have regarding subcontractors?",
    "What requirements apply to supplier personnel?",
    "How does Apple's anti-corruption policy relate to third parties?",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    retrieval = RetrievalService()
    try:
        for question in QUESTIONS:
            result = retrieval.retrieve(RetrievalRequest(query=question, top_k=args.limit))
            print(f"\nQUESTION: {question}")
            for context in result.results:
                compact = " ".join(context.text.split())[:240]
                print(
                    json.dumps(
                        {
                            "rank": context.rank,
                            "document_name": context.source,
                            "chunk_index": context.location.chunk_index,
                            "score": round(context.score, 4),
                            "preview": compact,
                        },
                        ensure_ascii=False,
                    )
                )
    finally:
        retrieval.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
