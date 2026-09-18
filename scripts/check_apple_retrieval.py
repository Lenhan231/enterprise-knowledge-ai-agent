#!/usr/bin/env python3
"""Run the cross-document retrieval checkpoint for the Apple corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.rag.rag_service import RAGService  # noqa: E402


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
    rag = RAGService()
    try:
        for question in QUESTIONS:
            result = rag.retrieve(question, args.limit)
            print(f"\nQUESTION: {question}")
            for rank, context in enumerate(result["contexts"], start=1):
                compact = " ".join(context["content"].split())[:240]
                print(
                    json.dumps(
                        {
                            "rank": rank,
                            "document_name": context["document_name"],
                            "chunk_index": context["chunk_index"],
                            "score": round(context["similarity_score"], 4),
                            "preview": compact,
                        },
                        ensure_ascii=False,
                    )
                )
    finally:
        rag.repository.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
