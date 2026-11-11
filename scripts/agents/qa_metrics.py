"""Deterministic citation and expected-fact metrics for saved QA results."""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from core.rag.rag_service import extract_source_ids


def cited_sources(result, include_full_evidence: bool = False) -> list[dict]:
    cited = set(result.source_ids)
    sources = []
    for context in result.contexts:
        if context["source_id"] not in cited:
            continue
        metadata = context.get("metadata") or {}
        source = {
            "source_id": context["source_id"],
            "document_id": metadata.get("document_id"),
            "source_document": metadata.get("source_document", context["document_name"]),
            "page_number": metadata.get("page_number"),
            "section_title": metadata.get("section_title"),
            "chunk_index": context["chunk_index"],
            "retrieval_score": context["retrieval_score"],
            "retrieval_method": context["retrieval_method"],
            "source_url": metadata.get("source_url"),
            "content_preview": " ".join(context["content"].split())[:500],
        }
        if include_full_evidence:
            source["evidence"] = context["content"]
        sources.append(source)
    return sources


def case_passed(case: dict, result, sources: list[dict]) -> tuple[bool, str]:
    if case.get("expect_insufficient"):
        passed = result.insufficient_context and not result.source_ids
        return passed, "Correctly refused unsupported question" if passed else "Expected insufficient-context refusal"
    cited_document_ids = {source["document_id"] for source in sources}
    if result.insufficient_context:
        return False, "Unexpected insufficient-context refusal"
    if not result.source_ids:
        return False, "Answer contains no citations"
    expected = case.get("expected_document_id")
    if expected and expected not in cited_document_ids:
        return False, f"Expected cited document {expected}, got {sorted(cited_document_ids)}"
    missing = missing_expected_facts(case, result.answer)
    if missing:
        return False, f"Answer omitted expected facts: {missing}"
    return True, "Answer cites the expected document"


def missing_expected_facts(case: dict, answer: str) -> list[str]:
    normalized = normalize_fact(answer)
    checks = [(fact, [fact]) for fact in case.get("expected_key_facts", [])]
    checks.extend((" or ".join(group), group) for group in case.get("expected_key_fact_groups", []))
    return [label for label, alternatives in checks
            if not any(normalize_fact(fact) in normalized for fact in alternatives)]


def normalize_fact(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"(?<=\d)[\s.,]+(?=\d)", "", value)
    value = re.sub(r"(?<=\d)\s+(?=%)", "", value)
    return " ".join(value.split())


def fact_present_in_evidence(fact: str, evidence: str) -> bool:
    normalized_fact, normalized_evidence = normalize_fact(fact), normalize_fact(evidence)
    if normalized_fact in normalized_evidence:
        return True
    unit = next((unit for unit in ("billion vnd", "tỷ đồng", "tỷ vnd", "million vnd", "kcal", "mg", "g")
                 if normalized_fact.endswith(unit)), None)
    amount = normalized_fact[:-len(unit)].strip() if unit else ""
    return bool(amount and amount in normalized_evidence and unit in normalized_evidence)


def citation_metrics(case: dict, answer: str, sources: list[dict], insufficient_context: bool = False) -> dict:
    relevant_ids = set(case.get("relevant_document_ids", []))
    retrieved_ids = [source.get("document_id") for source in sources]
    precision = sum(item in relevant_ids for item in retrieved_ids) / max(1, len(retrieved_ids)) if relevant_ids else None
    claims = [] if insufficient_context else [part.strip(" -*\t") for part in re.split(r"\n+", answer)
                                               if part.strip(" -*\t") and re.search(r"\w", part.strip(" -*\t"))]
    cited_ids = {source.get("source_id") for source in sources}
    cited_claims = sum(bool(set(extract_source_ids(claim)) & cited_ids) for claim in claims)
    answer_ids = set(extract_source_ids(answer))
    evidence = {}
    truncated = set()
    for source in sources:
        source_id = source.get("source_id")
        full, preview = source.get("evidence"), source.get("content_preview") or ""
        evidence[source_id] = normalize_fact(full if isinstance(full, str) else preview)
        if not isinstance(full, str) and len(preview) >= 500:
            truncated.add(source_id)
    groups = [[fact] for fact in case.get("expected_key_facts", [])] + case.get("expected_key_fact_groups", [])
    supported = unsupported = unverifiable = 0
    for alternatives in groups:
        answer_has = any(normalize_fact(fact) in normalize_fact(answer) for fact in alternatives)
        used = answer_ids.intersection(evidence)
        cited_text = " ".join(evidence[source_id] for source_id in used)
        evidence_has = any(fact_present_in_evidence(fact, cited_text) for fact in alternatives)
        if answer_has and evidence_has:
            supported += 1
        elif answer_has and used.intersection(truncated):
            unverifiable += 1
        else:
            unsupported += 1
    assessed = supported + unsupported
    return {
        "context_precision_at_cited_sources": round(precision, 4) if precision is not None else None,
        "citation_covered_line_fraction": round(cited_claims / len(claims), 4) if claims else None,
        "answer_has_valid_citation": bool(cited_ids & answer_ids),
        "expected_fact_count": len(groups),
        "expected_facts_literal_in_cited_evidence": supported,
        "expected_facts_not_supported_by_cited_evidence": unsupported,
        "expected_facts_unverifiable_due_to_truncated_preview": unverifiable,
        "expected_fact_evidence_assessed_count": assessed,
        "expected_fact_cited_evidence_rate": round(supported / assessed, 4) if assessed else None,
        "claim_count": len(claims), "claims_with_valid_citations": cited_claims,
        "context_precision_definition": "fraction of cited source documents matching manually labeled relevant_document_ids; not RAGAS context precision",
        "citation_coverage_definition": "fraction of non-empty answer lines or paragraphs containing a valid [S#] citation; bullets are not independently claim-aligned",
        "expected_fact_cited_evidence_definition": "literal match of expected facts in both answer and cited source text; not semantic entailment",
    }
