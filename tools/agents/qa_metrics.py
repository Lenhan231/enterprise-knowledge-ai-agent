"""Source and citation metrics for saved grounded-QA evaluations."""

from __future__ import annotations

import re
import unicodedata

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
            "source_document": metadata.get(
                "source_document",
                context["document_name"],
            ),
            "page_number": metadata.get("page_number"),
            "section_title": metadata.get("section_title"),
            "chunk_index": context["chunk_index"],
            "retrieval_score": context["retrieval_score"],
            "retrieval_method": context["retrieval_method"],
            "source_url": metadata.get("source_url"),
            "content_preview": " ".join(
                context["content"].split()
            )[:500],
        }
        if include_full_evidence:
            source["evidence"] = context["content"]
        sources.append(source)

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
    normalized_answer = normalize_fact(answer)
    checks = [(fact, [fact]) for fact in case.get("expected_key_facts", [])]
    checks.extend(
        (" or ".join(group), group)
        for group in case.get("expected_key_fact_groups", [])
    )
    return [
        label for label, alternatives in checks
        if not any(normalize_fact(fact) in normalized_answer for fact in alternatives)
    ]


def normalize_fact(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"(?<=\d)[\s.,]+(?=\d)", "", value)
    value = re.sub(r"(?<=\d)\s+(?=%)", "", value)
    return " ".join(value.split())


def fact_present_in_evidence(fact: str, evidence: str) -> bool:
    normalized_fact = normalize_fact(fact)
    normalized_evidence = normalize_fact(evidence)
    if normalized_fact in normalized_evidence:
        return True

    # PDF table extraction may place a shared unit label apart from its numeric
    # cells; accept both literals anywhere in the same cited chunk.
    unit = next((unit for unit in ("billion vnd", "tỷ đồng", "tỷ vnd", "million vnd", "kcal", "mg", "g") if normalized_fact.endswith(unit)), None)
    if unit is None:
        return False
    amount = normalized_fact[:-len(unit)].strip()
    return bool(amount) and amount in normalized_evidence and unit in normalized_evidence


def citation_metrics(case: dict, answer: str, sources: list[dict], insufficient_context: bool = False) -> dict:
    """Compute labeled-context precision, citation coverage and literal fact support."""
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
    source_evidence = {}
    truncated_preview_ids = set()
    for source in sources:
        source_id = source.get("source_id")
        full_evidence = source.get("evidence")
        preview = source.get("content_preview") or ""
        source_evidence[source_id] = normalize_fact(full_evidence if isinstance(full_evidence, str) else preview)
        if not isinstance(full_evidence, str) and len(preview) >= 500:
            truncated_preview_ids.add(source_id)
    expected_groups = [[fact] for fact in case.get("expected_key_facts", [])]
    expected_groups.extend(case.get("expected_key_fact_groups", []))
    supported_fact_count = 0
    unsupported_fact_count = 0
    unverifiable_fact_count = 0
    for alternatives in expected_groups:
        answer_has_fact = any(normalize_fact(fact) in normalize_fact(answer) for fact in alternatives)
        cited_source_ids = answer_source_ids.intersection(source_evidence)
        cited_evidence = " ".join(source_evidence[source_id] for source_id in cited_source_ids)
        evidence_has_fact = any(fact_present_in_evidence(fact, cited_evidence) for fact in alternatives)
        if answer_has_fact and evidence_has_fact:
            supported_fact_count += 1
        elif answer_has_fact and cited_source_ids.intersection(truncated_preview_ids):
            unverifiable_fact_count += 1
        else:
            unsupported_fact_count += 1
    assessable_fact_count = supported_fact_count + unsupported_fact_count
    fact_support_rate = supported_fact_count / assessable_fact_count if assessable_fact_count else None
    return {
        "context_precision_at_cited_sources": round(context_precision, 4) if context_precision is not None else None,
        "citation_covered_line_fraction": round(cited_claims / len(claims), 4) if claims else None,
        "answer_has_valid_citation": bool(cited_ids & answer_source_ids),
        "expected_fact_count": len(expected_groups),
        "expected_facts_literal_in_cited_evidence": supported_fact_count,
        "expected_facts_not_supported_by_cited_evidence": unsupported_fact_count,
        "expected_facts_unverifiable_due_to_truncated_preview": unverifiable_fact_count,
        "expected_fact_evidence_assessed_count": assessable_fact_count,
        "expected_fact_cited_evidence_rate": round(fact_support_rate, 4) if fact_support_rate is not None else None,
        "claim_count": len(claims),
        "claims_with_valid_citations": cited_claims,
        "context_precision_definition": "fraction of cited source documents matching manually labeled relevant_document_ids; not RAGAS context precision",
        "citation_coverage_definition": "fraction of non-empty answer lines or paragraphs containing a valid [S#] citation; bullets are not independently claim-aligned",
        "expected_fact_cited_evidence_definition": "fraction of assessable labeled expected facts present in both the answer and its cited source text by normalized literal matching; missing literals in a 500-character preview are marked unverifiable, not unsupported; this is not semantic entailment or a hallucination score",
    }
