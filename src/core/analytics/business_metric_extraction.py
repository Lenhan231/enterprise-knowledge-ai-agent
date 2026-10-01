"""Extract business metrics from parser-produced retrieval chunks using an LLM."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import defaultdict

from core.analytics.business_metric_catalog import (
    BUSINESS_DECISION_PROFILES,
    BUSINESS_METRIC_CATALOG,
)

logger = logging.getLogger(__name__)
PROMPT_VERSION = "business-metric-scoped-domain-json-v4"
EXTRACTOR_VERSION = "parser-chunk-scoped-domain-v4"
MAX_BUSINESS_METRIC_CHUNKS = 10
MAX_PRIMARY_METRICS_PER_PAGE = 5


def _flat(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _source_quote(source: str, quote: str) -> str | None:
    """Find the model quote verbatim, allowing whitespace changes only."""
    words = str(quote or "").split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(word) for word in words)
    match = re.search(pattern, source, re.IGNORECASE)
    return match.group(0) if match else None


def select_business_metric_chunks(
    chunks: list[dict], tables: list[dict] | None = None,
    max_chunks: int = MAX_BUSINESS_METRIC_CHUNKS,
    decision_domain: str | None = None,
) -> list[dict]:
    """Select metric-relevant parser chunks, then rank their numeric/layout evidence."""
    if decision_domain is not None and decision_domain not in BUSINESS_DECISION_PROFILES:
        raise ValueError("decision_domain must name a configured decision profile")
    profile_metrics = set(
        BUSINESS_DECISION_PROFILES[decision_domain]["primary_metrics"]
        if decision_domain else ()
    )
    table_context = {}
    for table in tables or []:
        metadata = table.get("metadata", {})
        key = (table.get("page_number"), table.get("table_index", metadata.get("table_index")))
        table_context[key] = table.get("context", {})

    page_contexts: dict[int, list[str]] = defaultdict(list)
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        try:
            page = int(metadata.get("page_number"))
        except (TypeError, ValueError):
            continue
        if (metadata.get("layout_type") or metadata.get("element_type")) != "table":
            text = str(chunk.get("text") or "").strip()
            if text and text not in page_contexts[page]:
                page_contexts[page].append(text)

    selected = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        is_table = (metadata.get("layout_type") or metadata.get("element_type")) == "table"
        try:
            page_number = int(metadata.get("page_number"))
        except (TypeError, ValueError):
            page_number = None
        table_index = metadata.get("table_index")
        context = table_context.get((page_number, table_index), {})
        page_context = "\n".join(page_contexts.get(page_number, []))
        domain_text = " ".join((
            text,
            str(metadata.get("section_title") or ""),
            str(context.get("table_title") or "") if isinstance(context, dict) else "",
            page_context,
        )).casefold()
        matched_metrics = []
        if decision_domain:
            for name in profile_metrics:
                definition = BUSINESS_METRIC_CATALOG[name]
                phrases = {name.replace("_", " "), definition["label"], *definition.get("aliases", ())}
                if any(" ".join(phrase.casefold().split()) in domain_text for phrase in phrases):
                    matched_metrics.append(name)
        row_text = "\n".join(re.findall(r"(?m)^Row \d+:.*$", text))
        row_text = re.sub(r"(?m)^Row \d+:\s*", "", row_text)
        numeric_tokens = re.findall(
            r"(?<!\w)[+-]?(?:\d[\d., ]*\d|\d)(?:\s*%|\s*(?:VND|tonnes?|tons?|cows|employees|stations))?",
            row_text or text, re.I,
        )
        # Tables and quantitative narrative both carry useful business evidence.
        # Financial candidates use a separate ontology, but overlapping evidence
        # is safe here because candidates are deduped/withheld by metric and year.
        if not numeric_tokens:
            continue
        score = (
            len(matched_metrics) * 100
            + min(len(numeric_tokens), 30)
            + min(len(text) // 500, 10)
            + (5 if is_table else 0)
        )
        selected.append({
            "text": text,
            "page_context_chunks": [
                item for item in page_contexts.get(page_number, []) if item != text
            ],
            "page_context": "\n".join(page_contexts.get(page_number, []))[:2500],
            "page_number": page_number,
            "chunk_index": metadata.get("chunk_index"),
            "section_title": metadata.get("section_title"),
            "layout_type": "table" if is_table else "text",
            "table_context": context if isinstance(context, dict) else {},
            "is_ocr_page": any("ocr" in str(metadata.get(key, "")).casefold()
                                for key in ("parser", "text_extraction_method", "table_extraction_method")),
            "selection_signals": {
                "domain_relevance_score": len(matched_metrics),
                "parser_layout": "table" if is_table else "text",
                "numeric_token_count": len(numeric_tokens),
                "matched_primary_metrics": sorted(matched_metrics),
                "score": score,
            },
        })
    ranked = sorted(selected, key=lambda item: (
        -item["selection_signals"]["score"],
        item["page_number"] or 0,
        item["chunk_index"] if isinstance(item["chunk_index"], int) else 0,
    ))
    # Keep selection spread across report pages; repeated narrative/table chunks
    # from a single dense page must not consume the entire LLM request budget.
    selected = []
    per_page = defaultdict(int)
    for evidence in ranked:
        page_number = evidence["page_number"]
        if per_page[page_number] >= 2:
            continue
        selected.append(evidence)
        per_page[page_number] += 1
        if len(selected) >= max(0, max_chunks):
            break
    return selected


def _prompt(company: str, document_year: int | str | None, evidence: dict,
            decision_domain: str) -> str:
    profile = BUSINESS_DECISION_PROFILES[decision_domain]
    primary_metrics = {
        name: {
            "label": BUSINESS_METRIC_CATALOG[name]["label"],
            "definition": BUSINESS_METRIC_CATALOG[name]["definition"],
            "unit_guidance": BUSINESS_METRIC_CATALOG[name]["unit_guidance"],
        }
        for name in profile["primary_metrics"]
    }
    input_chunks = []
    for chunk in evidence["chunks"]:
        context = chunk.get("table_context") or {}
        input_chunks.append(
            f"[Source chunk {chunk['chunk_index']} | {chunk['layout_type']} | "
            f"section: {chunk.get('section_title') or 'unknown'} | "
            f"table: {context.get('table_title') or 'not applicable'}]\n{chunk['text']}"
        )
    return f"""Extract explicitly reported business metrics from this parser-produced {evidence['layout_type']} chunk.
Company: {company}
Report fiscal year: {document_year or 'unknown'}
PDF page: {evidence['page_number'] or 'unknown'}

Return only JSON with this shape:
{{"metrics":[{{"metric_name":"primary metric key","metric_value":"numeric value as printed","unit":"unit as printed","fiscal_year":2025,"source_quote":"exact contiguous evidence from one source chunk"}}]}}

Decision domain: {decision_domain} — {profile['label']}
Management question: {profile['management_question']}
Choose metric_name only from this domain's primary metrics: {json.dumps(primary_metrics, ensure_ascii=False, separators=(',', ':'))}
Extract only directly supported primary metrics for this decision question, up to {MAX_PRIMARY_METRICS_PER_PAGE} metrics. Ignore every other catalog metric, supporting indicator, and unrelated number even when present. Explicitly labeled comparison periods are allowed when they belong to a primary metric.
The metric label, value, unit, and year must be supported by this chunk. Use an empty metrics array when no catalog metric is supported.
Never calculate, normalize units, infer a missing value/year, invent a quote, or use outside knowledge.
Each source_quote must be copied verbatim from exactly one source chunk below. For a table, include the full row and period/header; for narrative, quote the exact supporting passage. Do not return markdown or additional keys.

Other parsed text on this page (context only; do not quote values from it):
{evidence.get('page_context') or 'none'}

Parser-produced source chunks:
{chr(10).join(input_chunks)}"""


def _validated_metrics(
    response: str, evidence: dict, document_year: int | str | None,
) -> tuple[list[dict], dict[str, int], str | None]:
    payload = json.loads(response)
    if (not isinstance(payload, dict) or set(payload) != {"metrics"}
            or not isinstance(payload["metrics"], list)):
        raise ValueError("LLM output must contain only metrics")
    decision_domain = evidence["decision_domain"]
    if decision_domain not in BUSINESS_DECISION_PROFILES:
        raise ValueError("A valid business decision domain is required")
    allowed_metrics = set(BUSINESS_DECISION_PROFILES[decision_domain]["primary_metrics"])
    source = "\n".join(chunk["text"] for chunk in evidence["chunks"])
    valid, rejected = [], defaultdict(int)
    if len(payload["metrics"]) > MAX_PRIMARY_METRICS_PER_PAGE:
        rejected["domain_metric_limit"] += len(payload["metrics"]) - MAX_PRIMARY_METRICS_PER_PAGE
        payload["metrics"] = payload["metrics"][:MAX_PRIMARY_METRICS_PER_PAGE]
    required = {"metric_name", "metric_value", "unit", "fiscal_year", "source_quote"}
    for item in payload["metrics"]:
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("Each metric must contain the required JSON fields")
        name = item["metric_name"]
        value = str(item["metric_value"]).strip()
        unit = str(item["unit"]).strip()
        quote = str(item["source_quote"]).strip()
        year = item["fiscal_year"]
        if (name not in allowed_metrics or not value or len(value) > 64
                or not unit or len(unit) > 80 or not quote or len(quote) > 1200):
            rejected["metric_outside_decision_profile_or_empty_field"] += 1
            continue
        if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100:
            rejected["invalid_fiscal_year"] += 1
            continue
        if document_year and year > int(document_year):
            rejected["year_after_report"] += 1
            continue
        matched_chunk = next((
            (chunk, _source_quote(chunk["text"], quote))
            for chunk in evidence["chunks"]
            if _source_quote(chunk["text"], quote) is not None
        ), None)
        source_chunk, source_quote = matched_chunk if matched_chunk else (None, None)
        quote_normalized = " ".join(quote.split())
        if (source_chunk is None or value not in quote_normalized
                or _flat(unit) not in _flat("\n".join((source, evidence.get("page_context", ""))))
                or (str(year) not in quote_normalized
                    and (not document_year or year != int(document_year)))):
            rejected["quote_not_grounded"] += 1
            continue
        negative = value.startswith("(") and value.endswith(")")
        numeric = value.strip().strip("()")
        if not re.fullmatch(r"[-+]?\d[\d., ]*", numeric):
            rejected["non_numeric_value"] += 1
            continue
        numeric = numeric.replace(" ", "")
        if "," in numeric and "." not in numeric:
            groups = numeric.split(",")
            numeric = "".join(groups) if all(len(group) == 3 for group in groups[1:]) else ".".join(groups)
        elif "," in numeric and "." in numeric:
            numeric = numeric.replace(",", "") if numeric.rfind(",") < numeric.rfind(".") else numeric.replace(".", "").replace(",", ".")
        try:
            metric_value = float(numeric)
        except ValueError:
            rejected["invalid_numeric_value"] += 1
            continue
        if negative:
            metric_value = -abs(metric_value)
        if not math.isfinite(metric_value):
            rejected["non_finite_value"] += 1
            continue
        definition = BUSINESS_METRIC_CATALOG[name]
        valid.append({
            "metric_name": name,
            "metric_label": definition["label"],
            "domain": definition["domain"],
            "metric_value": metric_value,
            "unit": unit,
            "scope": definition["definition"],
            "fiscal_year": year,
            "source_quote": source_quote,
            "source_chunk_index": source_chunk["chunk_index"],
            "source_content_hash": hashlib.sha256(source_chunk["text"].encode()).hexdigest(),
            "source_table_context": source_chunk["table_context"],
            "source_layout_type": source_chunk["layout_type"],
        })
    return valid, dict(rejected), decision_domain


def extract_business_metric_candidates(
    chunks: list[dict], tables: list[dict], document: dict, llm,
    max_chunks: int = MAX_BUSINESS_METRIC_CHUNKS,
) -> tuple[list[dict], list[dict]]:
    """Extract only the primary KPIs for the explicitly selected decision domain."""
    decision_domain = document.get("business_decision_domain")
    if decision_domain not in BUSINESS_DECISION_PROFILES:
        raise ValueError("business_decision_domain must name a configured decision profile")
    selected = select_business_metric_chunks(
        chunks, tables, max_chunks, decision_domain=decision_domain,
    )
    chunks_by_page = defaultdict(list)
    for source_chunk in selected:
        chunks_by_page[source_chunk["page_number"]].append(source_chunk)
    page_evidence = []
    for page_number, source_chunks in chunks_by_page.items():
        selected_texts = {chunk["text"] for chunk in source_chunks}
        page_context_chunks = list(dict.fromkeys(
            text
            for chunk in source_chunks
            for text in chunk["page_context_chunks"]
            if text not in selected_texts
        ))
        page_evidence.append({
            "page_number": page_number,
            "decision_domain": decision_domain,
            "chunks": source_chunks,
            "page_context": "\n".join(page_context_chunks)[:2500],
            "layout_type": "mixed" if len({chunk["layout_type"] for chunk in source_chunks}) > 1
            else source_chunks[0]["layout_type"],
            "selection_signals": {
                "source_chunks": len(source_chunks),
                "numeric_token_count": sum(chunk["selection_signals"]["numeric_token_count"]
                                            for chunk in source_chunks),
            },
        })

    observations = []
    for evidence in page_evidence:
        try:
            response = llm.generate(_prompt(document.get("company", "Unknown company"),
                                            document.get("fiscal_year"), evidence, decision_domain))
            evidence["llm_usage"] = getattr(llm, "last_usage", None)
            found, rejected, decision_domain = _validated_metrics(
                response, evidence, document.get("fiscal_year"),
            )
            evidence["decision_domain"] = decision_domain
            evidence["llm_metrics_returned"] = len(json.loads(response).get("metrics", []))
            evidence["llm_metrics_accepted"] = len(found)
            evidence["validation_rejections"] = rejected
        except Exception as error:
            evidence["extraction_error"] = f"{type(error).__name__}: {error}"[:300]
            logger.warning("Business metric extraction failed for %s page %s chunk %s: %s",
                           document.get("document_id"), evidence["page_number"],
                           [chunk["chunk_index"] for chunk in evidence["chunks"]], evidence["extraction_error"])
            continue
        for metric in found:
            observations.append((metric, evidence))

    candidates = []
    by_metric_period = defaultdict(list)
    for metric, evidence in observations:
        by_metric_period[(metric["metric_name"], metric["fiscal_year"])].append((metric, evidence))
    for same_metric in by_metric_period.values():
        signatures = {(row[0]["metric_value"], row[0]["unit"]) for row in same_metric}
        if len(signatures) != 1:
            marked = set()
            for _, evidence in same_metric:
                if id(evidence) not in marked:
                    evidence["ambiguous_metric_periods"] = evidence.get("ambiguous_metric_periods", 0) + 1
                    marked.add(id(evidence))
            continue
        metric, evidence = same_metric[0]
        quote = metric["source_quote"]
        candidates.append({
            **metric,
            "company": document["company"],
            "source_document_id": document["document_id"],
            "page_number": evidence["page_number"],
            "source_quote_hash": hashlib.sha256(quote.encode()).hexdigest(),
            "source_url": document.get("source_url"),
            "allowed_roles": document.get("rbac", {}).get("allowed_roles", ["executive", "admin"]),
            "extraction_method": "llm_parser",
            "extractor_version": EXTRACTOR_VERSION,
            "extraction_config": {
                "prompt_version": PROMPT_VERSION,
                "decision_domain": evidence.get("decision_domain"),
                "model": getattr(llm, "model_name", llm.__class__.__name__),
                "selection_signals": evidence["selection_signals"],
                "layout_type": evidence["layout_type"],
                "source_layout_type": metric["source_layout_type"],
                "table_context": metric["source_table_context"],
                "selected_chunk_indices": [chunk["chunk_index"] for chunk in evidence["chunks"]],
                "llm_usage": evidence.get("llm_usage"),
            },
            "source_content_hash": metric["source_content_hash"],
        })
    return candidates, page_evidence


def build_business_metric_extraction_run(
    chunks: list[dict], page_results: list[dict], candidates: list[dict],
    document: dict, llm, execution_error: str | None = None,
) -> dict:
    """Create a compact, source-text-free audit of every chunk considered."""
    selected_by_index = {}
    page_by_number = {}
    for page in page_results:
        page_by_number[page["page_number"]] = page
        for selected in page.get("chunks", []):
            selected_by_index[selected.get("chunk_index")] = selected
    candidate_indices = {candidate.get("source_chunk_index") for candidate in candidates}
    decisions = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        index = metadata.get("chunk_index")
        try:
            page_number = int(metadata.get("page_number"))
        except (TypeError, ValueError):
            page_number = None
        selected = selected_by_index.get(index)
        page = page_by_number.get(page_number, {})
        row_text = "\n".join(re.findall(r"(?m)^Row \d+:.*$", str(chunk.get("text") or "")))
        row_text = re.sub(r"(?m)^Row \d+:\s*", "", row_text)
        has_numeric_evidence = bool(re.search(
            r"(?<!\w)[+-]?(?:\d[\d., ]*\d|\d)(?:\s*%|\s*(?:VND|tonnes?|tons?|cows|employees|stations))?",
            row_text or str(chunk.get("text") or ""), re.I,
        ))
        if execution_error:
            status = "not_evaluated"
        elif selected is None:
            status = "not_selected"
        elif page.get("extraction_error"):
            status = "llm_error"
        elif index in candidate_indices:
            status = "candidate_found"
        else:
            status = "checked_no_candidate"
        decisions.append({
            "chunk_index": index,
            "page_number": page_number,
            "content_hash": hashlib.sha256(str(chunk.get("text") or "").encode()).hexdigest(),
            "section_title": metadata.get("section_title"),
            "layout_type": metadata.get("layout_type") or metadata.get("element_type"),
            "status": status,
            "selection_reason": (
                None if selected else "no_numeric_evidence" if not has_numeric_evidence
                else "ranked_out_or_per_page_limit"
            ),
            "selection_signals": selected.get("selection_signals") if selected else None,
        })

    selected_count = len(selected_by_index)
    errors = sum(bool(page.get("extraction_error")) for page in page_results)
    if execution_error in {"provider_unavailable", "unsupported_format"}:
        status = execution_error
    elif execution_error:
        status = "failed"
    elif not selected_count:
        status = "no_chunks_selected"
    else:
        status = "partial" if errors else "completed"
    return {
        "document_id": document["document_id"],
        "company": document.get("company", "Unknown company"),
        "decision_domain": document["business_decision_domain"],
        "extractor_version": EXTRACTOR_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model_name": getattr(llm, "model_name", llm.__class__.__name__) if llm else "unavailable",
        "status": status,
        "input_chunk_count": len(chunks),
        "selected_chunk_count": selected_count,
        "candidate_count": len(candidates),
        "audit": {
            "chunk_decisions": decisions,
            "page_results": [{
                "page_number": page["page_number"],
                "selected_chunk_indices": [chunk.get("chunk_index") for chunk in page.get("chunks", [])],
                "metrics_returned": page.get("llm_metrics_returned", 0),
                "metrics_accepted": page.get("llm_metrics_accepted", 0),
                "validation_rejections": page.get("validation_rejections", {}),
                "ambiguous_metric_periods": page.get("ambiguous_metric_periods", 0),
                "error": page.get("extraction_error"),
                "llm_usage": page.get("llm_usage"),
            } for page in page_results],
            "execution_error": execution_error,
        },
    }
