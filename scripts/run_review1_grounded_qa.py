#!/usr/bin/env python3
"""Run and save the Review 1 grounded-QA evidence gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.rag.rag_service import RAGService  # noqa: E402


CASES = (
    {
        "id": "policy_anti_corruption",
        "domain": "compliance",
        "question": (
            "According to Apple's Anti-Corruption Policy, "
            "What responsibilities do third parties have "
            "concerning bribery and corruption?"
        ),
        "expected_document_id": "APL-CMP-003",
        "expect_insufficient": False,
    },
    {
        "id": "third_party_standards",
        "domain": "compliance",
        "question": (
            "What standards must third parties working "
            "with Apple follow?"
        ),
        "expected_document_id": "APL-CMP-004",
        "expect_insufficient": False,
    },
    {
        "id": "environment_report",
        "domain": "report",
        "question": (
            "According to Apple's Environmental Progress Report, "
            "what percentage reduction in gross greenhouse gas "
            "emissions did Apple report compared with its "
            "2015 baseline?"
        ),
        "expected_document_id": "APL-ENV-002",
        "expect_insufficient": False,
    },
    {
        "id": "unsupported_private_data",
        "domain": "negative_control",
        "question": (
            "What is Apple's private internal hiring "
            "budget for 2026?"
        ),
        "expected_document_id": None,
        "expect_insufficient": True,
    },
)


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def cited_sources(result) -> list[dict]:
    cited = set(result.source_ids)
    sources = []

    for context in result.contexts:
        if context["source_id"] not in cited:
            continue

        metadata = context.get("metadata") or {}
        sources.append(
            {
                "source_id": context["source_id"],
                "document_id": metadata.get("document_id"),
                "source_document": metadata.get(
                    "source_document",
                    context["document_name"],
                ),
                "page_number": metadata.get("page_number"),
                "section_title": metadata.get("section_title"),
                "chunk_index": context["chunk_index"],
                "similarity_score": context["similarity_score"],
                "official_url": metadata.get("official_url"),
                "content_preview": " ".join(
                    context["content"].split()
                )[:500],
            }
        )

    return sources


def case_passed(
    case: dict,
    result,
    sources: list[dict],
) -> tuple[bool, str]:
    if case["expect_insufficient"]:
        passed = (
            result.insufficient_context
            and not result.source_ids
        )
        return (
            passed,
            "Correctly refused unsupported question"
            if passed
            else "Expected insufficient-context refusal",
        )

    cited_document_ids = {
        source["document_id"]
        for source in sources
    }

    if result.insufficient_context:
        return False, "Unexpected insufficient-context refusal"

    if not result.source_ids:
        return False, "Answer contains no citations"

    expected = case["expected_document_id"]
    if expected not in cited_document_ids:
        return (
            False,
            f"Expected cited document {expected}, "
            f"got {sorted(cited_document_ids)}",
        )

    return True, "Answer cites the expected document"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Review 1 grounded-QA evidence gate."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Top-K chunks retrieved per question.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/review1/"
            "grounded_qa_results.json"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = []
    failed = False
    rag = RAGService()

    try:
        for case in CASES:
            started = perf_counter()

            try:
                result = rag.generate_answer(
                    case["question"],
                    limit=args.limit,
                )
                elapsed_ms = (
                    perf_counter() - started
                ) * 1000

                sources = cited_sources(result)
                passed, reason = case_passed(
                    case,
                    result,
                    sources,
                )
                failed = failed or not passed

                row = {
                    **case,
                    "passed": passed,
                    "reason": reason,
                    "answer": result.answer,
                    "insufficient_context": (
                        result.insufficient_context
                    ),
                    "source_ids": result.source_ids,
                    "sources": sources,
                    "retrieved_context_count": len(
                        result.contexts
                    ),
                    "total_latency_ms": round(
                        elapsed_ms,
                        2,
                    ),
                }

            except Exception as error:
                failed = True
                row = {
                    **case,
                    "passed": False,
                    "reason": "Execution error",
                    "error": (
                        f"{type(error).__name__}: {error}"
                    ),
                }

            results.append(row)

            status = "PASS" if row["passed"] else "FAIL"
            print(f"\n[{status}] {case['id']}")
            print(f"Question: {case['question']}")

            if "answer" in row:
                print(f"Answer: {row['answer']}")

                for source in row["sources"]:
                    location = (
                        f"page={source['page_number']}, "
                        f"section={source['section_title']}"
                    )
                    print(
                        f"Source: {source['source_id']} "
                        f"{source['document_id']} "
                        f"({location})"
                    )
            else:
                print(f"Error: {row['error']}")

    finally:
        rag.close()

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "git_commit": git_commit(),
        "top_k": args.limit,
        "summary": {
            "total": len(results),
            "passed": sum(
                row["passed"]
                for row in results
            ),
            "failed": sum(
                not row["passed"]
                for row in results
            ),
        },
        "baseline": [
            "Dense Top-K pgvector retrieval",
            "Evidence-only generation prompt",
            "Inline [S#] source citations",
            "Citation ID validation",
            "Document and page provenance",
            "Insufficient-context refusal",
        ],
        "planned": [
            "Clickable citation UX",
            "Exact cited-span highlighting",
            "Claim-level citation alignment",
            "Automated faithfulness evaluation",
            "Citation correctness benchmark",
            "Regression evaluation harness",
        ],
        "results": results,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"\nEvidence written to: {args.output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())