#!/usr/bin/env python3
"""Run and save the Review 1 grounded-QA evidence gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, sleep


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.rag.rag_service import RAGService  # noqa: E402
from core.rag.rag_service import extract_source_ids  # noqa: E402


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
                "retrieval_score": context["retrieval_score"],
                "retrieval_method": context["retrieval_method"],
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

    missing_facts = missing_expected_facts(case, result.answer)
    if missing_facts:
        return False, f"Answer omitted expected facts: {missing_facts}"

    return True, "Answer cites the expected document"


def missing_expected_facts(case: dict, answer: str) -> list[str]:
    def normalize(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).casefold()
        value = re.sub(r"(?<=\d)[\s.,]+(?=\d)", "", value)
        value = re.sub(r"(?<=\d)\s+(?=%)", "", value)
        return " ".join(value.split())

    normalized_answer = normalize(answer)
    checks = [(fact, [fact]) for fact in case.get("expected_key_facts", [])]
    checks.extend(
        (" or ".join(group), group)
        for group in case.get("expected_key_fact_groups", [])
    )
    return [
        label for label, alternatives in checks
        if not any(normalize(fact) in normalized_answer for fact in alternatives)
    ]


def citation_metrics(case: dict, answer: str, sources: list[dict], insufficient_context: bool = False) -> dict:
    """Compute labeled-context precision and sentence citation coverage."""
    relevant_ids = set(case.get("relevant_document_ids", []))
    retrieved_ids = [source.get("document_id") for source in sources]
    context_precision = None
    if relevant_ids:
        context_precision = sum(document_id in relevant_ids for document_id in retrieved_ids) / max(1, len(retrieved_ids))

    claims = [] if insufficient_context else [part.strip(" -*\t") for part in re.split(r"\n+", answer) if part.strip(" -*\t") and re.search(r"\w", part.strip(" -*\t"))]
    cited_ids = {source.get("source_id") for source in sources}
    cited_claims = 0
    for claim in claims:
        ids = set(extract_source_ids(claim))
        cited_claims += bool(ids & cited_ids)
    answer_source_ids = set(extract_source_ids(answer))
    return {
        "context_precision_at_cited_sources": round(context_precision, 4) if context_precision is not None else None,
        "citation_covered_line_fraction": round(cited_claims / len(claims), 4) if claims else None,
        "answer_has_valid_citation": bool(cited_ids & answer_source_ids),
        "claim_count": len(claims),
        "claims_with_valid_citations": cited_claims,
        "context_precision_definition": "fraction of cited source documents matching manually labeled relevant_document_ids; not RAGAS context precision",
        "citation_coverage_definition": "fraction of non-empty answer lines or paragraphs containing a valid [S#] citation; bullets are not independently claim-aligned",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Review 1 grounded-QA evidence gate."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        help="Optional JSON file with the same case fields as the built-in Review 1 set.",
    )
    parser.add_argument(
        "--company",
        help="Optional company filter applied to every case.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Top-K chunks retrieved per question.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0,
        help="Pause between model calls to stay within provider rate limits.",
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
    if args.delay_seconds < 0:
        raise ValueError("--delay-seconds must be non-negative")
    cases = CASES
    cases_sha256 = None
    if args.cases:
        case_bytes = args.cases.read_bytes()
        cases_sha256 = hashlib.sha256(case_bytes).hexdigest()
        loaded = json.loads(case_bytes)
        cases = loaded.get("cases", loaded)
        if not isinstance(cases, list) or not cases:
            raise ValueError("--cases must contain a non-empty cases array")
    results = []
    failed = False
    rag = RAGService()

    try:
        for index, case in enumerate(cases):
            started = perf_counter()

            try:
                result = rag.generate_answer(
                    case["question"],
                    limit=args.limit,
                    company=args.company,
                    roles=[case["role"]] if case.get("role") else None,
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
                if case["expect_insufficient"]:
                    source_correct = result.insufficient_context and not sources
                else:
                    source_correct = case["expected_document_id"] in {
                        source["document_id"] for source in sources
                    }
                fact_misses = missing_expected_facts(case, result.answer)

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
                    "quality_checks": {
                        "expected_source_correct": source_correct,
                        "expected_key_facts_present": not fact_misses,
                        "missing_key_facts": fact_misses,
                    },
                    "generation_metrics": citation_metrics(case, result.answer, sources, result.insufficient_context),
                    "retrieved_context_count": len(
                        result.contexts
                    ),
                    "context_sha256": hashlib.sha256(
                        json.dumps(result.contexts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    ).hexdigest(),
                    "prompt_sha256": result.prompt_sha256,
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

            row["human_reviews"] = []
            row["llm_usage"] = (
                getattr(rag.llm, "last_usage", None)
                if "answer" in row and not row.get("insufficient_context")
                else None
            )

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
            if args.delay_seconds and index < len(cases) - 1:
                sleep(args.delay_seconds)

    finally:
        rag.close()

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "git_commit": git_commit(),
        "case_file": args.cases.name if args.cases else "built-in Review 1 cases",
        "case_file_sha256": cases_sha256,
        "company": args.company,
        "top_k": args.limit,
        "retrieval_method": "hybrid",
        "prompt_template_sha256": hashlib.sha256(
            (REPO_ROOT / "src/core/prompts/Knowledge.py").read_bytes()
        ).hexdigest(),
        "delay_seconds_between_cases": args.delay_seconds,
        "llm_model": getattr(rag.llm, "model_name", type(rag.llm).__name__),
        "human_review_required": [
            "faithfulness and answer relevancy on a 1-5 scale",
            "context precision on a 1-5 scale",
            "hallucinated_claim_count and factual_claim_count",
        ],
        "human_review_rubric": {
            "scale": "1-5; 1=poor, 3=partly meets, 5=fully meets",
            "faithfulness": "Rate whether each factual claim is supported by the cited source content.",
            "answer_relevancy": "Rate whether the answer directly and completely addresses the question.",
            "context_precision": "Rate whether the cited/retrieved evidence is relevant to the question and answer.",
            "hallucinated_claim_count": "Count factual claims unsupported or contradicted by the cited evidence.",
            "factual_claim_count": "Count all verifiable factual claims in the answer; exclude correct abstentions.",
            "reviewer": "Use an anonymous reviewer ID. Reviewers should score answers against source pages, not model identity.",
        },
        "summary": {
            "total": len(results),
            "completed": sum("answer" in row for row in results),
            "execution_errors": sum(row.get("reason") == "Execution error" for row in results),
            "passed": sum(
                row["passed"]
                for row in results
            ),
            "failed": sum(
                not row["passed"]
                for row in results
            ),
            "input_tokens": sum(
                row["llm_usage"]["input_tokens"]
                for row in results
                if row.get("llm_usage") and row["llm_usage"].get("input_tokens") is not None
            ),
            "output_tokens": sum(
                row["llm_usage"]["output_tokens"]
                for row in results
                if row.get("llm_usage") and row["llm_usage"].get("output_tokens") is not None
            ),
            "expected_source_accuracy": round(
                sum(row["quality_checks"]["expected_source_correct"] for row in results if "answer" in row)
                / sum("answer" in row for row in results), 4
            ) if any("answer" in row for row in results) else None,
            "expected_key_fact_case_accuracy": round(
                sum(row["quality_checks"]["expected_key_facts_present"] for row in results if row.get("expected_key_facts") and "answer" in row)
                / sum(bool(row.get("expected_key_facts") or row.get("expected_key_fact_groups")) for row in results if "answer" in row), 4
            ) if any((row.get("expected_key_facts") or row.get("expected_key_fact_groups")) and "answer" in row for row in results) else None,
        },
        "baseline": [
            "Default retrieval mode selected by RetrievalService",
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
