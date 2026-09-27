#!/usr/bin/env python3
"""Recompute deterministic QA/citation metrics from a saved run without model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_review1_grounded_qa import (  # noqa: E402
    case_passed,
    citation_metrics,
    missing_expected_facts,
)


def summarize_human_reviews(results: list[dict]) -> dict:
    reviewed = []
    reviewed_cases = 0
    for row in results:
        entries = row.get("human_reviews")
        if not isinstance(entries, list):
            legacy = row.get("human_review")
            entries = [legacy] if isinstance(legacy, dict) else []
        valid_entries = [entry for entry in entries if isinstance(entry, dict) and entry.get("reviewer")]
        reviewed.extend(valid_entries)
        reviewed_cases += bool(valid_entries)
    score_fields = ("faithfulness", "answer_relevancy", "context_precision")
    means = {}
    for field in score_fields:
        values = [
            review[field] for review in reviewed
            if isinstance(review.get(field), int)
            and not isinstance(review[field], bool)
            and 1 <= review[field] <= 5
        ]
        means[f"mean_{field}"] = round(sum(values) / len(values), 3) if values else None

    claim_reviews = [
        review for review in reviewed
        if isinstance(review.get("factual_claim_count"), int)
        and not isinstance(review.get("factual_claim_count"), bool)
        and review["factual_claim_count"] >= 0
        and isinstance(review.get("hallucinated_claim_count"), int)
        and not isinstance(review.get("hallucinated_claim_count"), bool)
        and 0 <= review["hallucinated_claim_count"] <= review["factual_claim_count"]
    ]
    factual_claims = sum(review["factual_claim_count"] for review in claim_reviews)
    hallucinated_claims = sum(review["hallucinated_claim_count"] for review in claim_reviews)
    return {
        "reviewed_case_count": reviewed_cases,
        "reviewer_count": len({review["reviewer"] for review in reviewed}),
        **means,
        "claim_review_case_count": len(claim_reviews),
        "factual_claim_count": factual_claims,
        "hallucinated_claim_count": hallucinated_claims,
        "hallucination_rate": round(hallucinated_claims / factual_claims, 4) if factual_claims else None,
        "note": "Human metrics include only rows with a reviewer ID and valid values; score each model's answer against source evidence.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--cases", type=Path, default=REPO_ROOT / "data/evaluation/vinamilk_qa_cases.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.artifact.read_text(encoding="utf-8"))
    case_bytes = args.cases.read_bytes()
    cases_file = json.loads(case_bytes)
    cases = {case["id"]: case for case in cases_file["cases"]}
    for result in report.get("results", []):
        case = cases.get(result.get("id"))
        if case is None or "answer" not in result:
            continue
        result["expected_key_facts"] = case.get("expected_key_facts", [])
        if "expected_key_fact_groups" in case:
            result["expected_key_fact_groups"] = case["expected_key_fact_groups"]
        else:
            result.pop("expected_key_fact_groups", None)
        result["generation_metrics"] = citation_metrics(case, result["answer"], result.get("sources", []), result.get("insufficient_context", False))
        passed, reason = case_passed(
            case,
            SimpleNamespace(
                answer=result["answer"],
                insufficient_context=result.get("insufficient_context", False),
                source_ids=result.get("source_ids", []),
            ),
            result.get("sources", []),
        )
        result["passed"] = passed
        result["reason"] = reason
        checks = result.setdefault("quality_checks", {})
        expected_document = case.get("expected_document_id")
        checks["expected_source_correct"] = (
            result.get("insufficient_context", False) and not result.get("source_ids")
            if case.get("expect_insufficient")
            else expected_document in {
                source.get("document_id") for source in result.get("sources", [])
            }
        )
        checks["expected_key_facts_present"] = not missing_expected_facts(case, result["answer"])

    report["scoring_protocol"] = {
        "case_file": args.cases.name,
        "case_file_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "source_run": str(args.artifact),
    }
    completed = [row for row in report.get("results", []) if "answer" in row]
    fact_cases = [
        row for row in completed
        if row.get("expected_key_facts") or row.get("expected_key_fact_groups")
    ]
    report.setdefault("summary", {}).update({
        "completed": len(completed),
        "passed": sum(bool(row.get("passed")) for row in report.get("results", [])),
        "failed": sum(not bool(row.get("passed")) for row in report.get("results", [])),
        "expected_source_accuracy": round(
            sum(bool(row.get("quality_checks", {}).get("expected_source_correct")) for row in completed) / len(completed), 4
        ) if completed else None,
        "expected_key_fact_case_accuracy": round(
            sum(bool(row.get("quality_checks", {}).get("expected_key_facts_present")) for row in fact_cases) / len(fact_cases), 4
        ) if fact_cases else None,
    })
    valid = [row for row in report.get("results", []) if row.get("generation_metrics") and not row.get("insufficient_context")]
    report["generation_metric_summary"] = {
        "scored_answer_cases": len(valid),
        "mean_labeled_context_precision": round(sum(row["generation_metrics"]["context_precision_at_cited_sources"] for row in valid if row["generation_metrics"]["context_precision_at_cited_sources"] is not None) / max(1, sum(row["generation_metrics"]["context_precision_at_cited_sources"] is not None for row in valid)), 4),
        "mean_line_citation_coverage": round(sum(row["generation_metrics"]["citation_covered_line_fraction"] for row in valid if row["generation_metrics"]["citation_covered_line_fraction"] is not None) / max(1, sum(row["generation_metrics"]["citation_covered_line_fraction"] is not None for row in valid)), 4),
        "valid_citation_answer_rate": round(sum(row["generation_metrics"]["answer_has_valid_citation"] for row in valid) / max(1, len(valid)), 4),
        "human_review": summarize_human_reviews(report.get("results", [])),
        "note": "Correct abstentions are excluded from answer citation averages; deterministic proxies are not semantic quality scores.",
        "source_run": str(args.artifact),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["generation_metric_summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
