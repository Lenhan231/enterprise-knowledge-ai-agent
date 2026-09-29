"""Select report pages and extract source-quoted financial metrics."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

from core.analytics.metric_ontology import METRIC_ONTOLOGY

logger = logging.getLogger(__name__)

PROMPT_VERSION = "vinamilk-financial-page-json-v2"
MAX_FINANCIAL_PAGES = 10
METRIC_NAMES = {
    "total_consolidated_revenue": "Total consolidated revenue",
    "net_revenue": "Net revenue",
    "profit_before_tax": "Profit before tax",
    "profit_after_tax": "Profit after tax",
    "total_assets": "Total assets",
}
FINANCIAL_TERMS = (
    "financial statements", "consolidated financial", "balance sheet",
    "statement of financial position", "income statement",
    "statement of comprehensive income", "results of operations",
    "báo cáo tài chính", "bảng cân đối kế toán", "kết quả hoạt động kinh doanh",
    "báo cáo kết quả", "doanh thu", "lợi nhuận", "tổng tài sản",
    "revenue", "profit", "total assets",
)
STATEMENT_TERMS = (
    "financial statements", "consolidated financial", "balance sheet",
    "statement of financial position", "income statement",
    "statement of comprehensive income", "results of operations",
    "báo cáo tài chính", "bảng cân đối kế toán", "kết quả hoạt động kinh doanh",
    "báo cáo kết quả",
)
PRIMARY_METRICS = {
    "total_consolidated_revenue", "net_revenue", "profit_before_tax",
    "profit_after_tax", "total_assets",
}


def _flat(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _ocr_label_match(labels: tuple[str, ...], quote: str) -> bool:
    """Allow a close OCR label only inside an otherwise exact source quote."""
    def words(value: str) -> list[str]:
        folded = unicodedata.normalize("NFKD", value.casefold())
        plain = "".join(char for char in folded if not unicodedata.combining(char))
        return re.findall(r"\w+", plain)

    quote_words = words(quote)
    for label in labels:
        expected = words(label)
        if not expected:
            continue
        for width in range(max(1, len(expected) - 1), len(expected) + 2):
            for start in range(max(0, len(quote_words) - width + 1)):
                observed = quote_words[start:start + width]
                if SequenceMatcher(None, " ".join(expected), " ".join(observed)).ratio() >= 0.90:
                    return True
    return False


def _table_text(table: dict) -> str:
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    parts = [" | ".join(map(str, columns))] if columns else []
    for row in rows:
        values = row.values() if isinstance(row, dict) else row
        parts.append(" | ".join(str(value or "") for value in values))
    return "\n".join(part for part in parts if part.strip())


def select_financial_pages(
    chunks: list[dict], tables: list[dict] | None = None,
    max_pages: int = MAX_FINANCIAL_PAGES,
) -> list[dict]:
    """Rank only pages with financial-section/metric signals or financial tables."""
    pages: dict[int, dict] = defaultdict(lambda: {
        "texts": [], "sections": [], "tables": [], "structured_tables": [],
        "extraction_methods": set(),
    })
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        try:
            page_number = int(metadata.get("page_number"))
        except (TypeError, ValueError):
            continue
        if page_number < 1:
            continue
        text = str(chunk.get("text", "")).strip()
        extraction_method = str(metadata.get("text_extraction_method") or "").casefold()
        if extraction_method:
            pages[page_number]["extraction_methods"].add(extraction_method)
        if text and text not in pages[page_number]["texts"]:
            pages[page_number]["texts"].append(text)
        section = str(metadata.get("section_title") or "").strip()
        if section and section not in pages[page_number]["sections"]:
            pages[page_number]["sections"].append(section)
        layout = str(metadata.get("layout_type") or metadata.get("element_type") or "").casefold()
        if layout == "table" and text:
            pages[page_number]["tables"].append(text)
    for table in tables or []:
        try:
            page_number = int(table.get("page_number"))
        except (TypeError, ValueError):
            continue
        if page_number > 0:
            text = _table_text(table)
            if text and text not in pages[page_number]["tables"]:
                pages[page_number]["tables"].append(text)
            if table not in pages[page_number]["structured_tables"]:
                pages[page_number]["structured_tables"].append(table)

    ranked = []
    for page_number, content in pages.items():
        text = "\n".join([*content["sections"], *content["texts"], *content["tables"]])
        flat = _flat(text)
        term_hits = [term for term in FINANCIAL_TERMS if term in flat]
        metric_hits = [
            name for name, definition in METRIC_ONTOLOGY.items()
            if any(_flat(alias) in flat for alias in definition["source_labels"])
        ]
        primary_hits = sorted(PRIMARY_METRICS.intersection(metric_hits))
        statement_hits = [term for term in STATEMENT_TERMS if term in flat]
        summary_signal = page_number <= 25 and bool(primary_hits)
        table_count = len(content["tables"])
        # A detected table alone is too broad; require either a financial term
        # or explicit numeric KPI labels before spending an LLM request.
        if not term_hits and not metric_hits:
            continue
        score = (
            len(primary_hits) * 5
            + len(statement_hits) * 3
            + min(table_count, 2) * 5
            + (8 if summary_signal else 0)
            + len(set(metric_hits) - PRIMARY_METRICS)
            + len(set(term_hits) - set(statement_hits))
        )
        ranked.append({
            "page_number": page_number,
            "text": text[:16000],
            "structured_tables": content["structured_tables"],
            "is_ocr_page": any(
                "tesseract" in method or "ocr" in method
                for method in content["extraction_methods"]
            ),
            "selection_signals": {
                "financial_terms": term_hits,
                "metric_labels": metric_hits,
                "primary_metric_labels": primary_hits,
                "statement_terms": statement_hits,
                "summary_area_with_metric": summary_signal,
                "table_count": table_count,
                "score": score,
            },
        })
    ranked.sort(key=lambda page: (-page["selection_signals"]["score"], page["page_number"]))
    return ranked[:max(0, max_pages)]


def _prompt(company: str, document_year: int | None, page: dict) -> str:
    parsed_tables = json.dumps(
        page.get("structured_tables", []), ensure_ascii=False, separators=(",", ":")
    )
    return f"""Extract explicitly reported financial metrics from one page of a public company report.
Company: {company}
Report year: {document_year or 'unknown'}
PDF page: {page['page_number']}

Return only a JSON object with exactly this shape:
{{"metrics":[{{"metric_name":"total_consolidated_revenue|net_revenue|profit_before_tax|profit_after_tax|total_assets","metric_value":"verbatim numeric token","unit":"reported unit","fiscal_year":2024,"source_quote":"verbatim supporting text from this page"}}]}}

Rules: extract at most one value for each of the five allowed metrics. When a report year is provided, extract only the value for that fiscal year; ignore comparison years even if the page shows them. Use an empty metrics array only when the requested year or metric is not explicitly supported on this page. Do not calculate, convert units, infer missing values, or use knowledge outside the page. For a parser table, copy the exact source_quote row from the serialized table rows below; do not rebuild or reorder cells. For narrative text, copy an exact contiguous substring from the page text. The fiscal_year must be explicitly shown on this page and must match the report year when provided. Do not return markdown or additional keys.

Parser-detected table data (preserve exact cell strings):
{parsed_tables}

Page content:
{page['text']}"""


def _validated_metrics(
    response: str, page_text: str, document_year: int | None = None,
    allow_ocr_label_recovery: bool = False,
) -> tuple[list[dict], dict[str, int]]:
    payload = json.loads(response)
    if not isinstance(payload, dict) or set(payload) != {"metrics"} or not isinstance(payload["metrics"], list):
        raise ValueError("LLM output must be an object containing only a metrics array")
    valid = []
    rejected: dict[str, int] = defaultdict(int)
    page_flat = _flat(page_text)
    allowed_keys = {"metric_name", "metric_value", "unit", "fiscal_year", "source_quote"}
    for item in payload["metrics"]:
        if not isinstance(item, dict) or set(item) != allowed_keys:
            raise ValueError("Each extracted metric must match the required JSON fields")
        name = item["metric_name"]
        value = str(item["metric_value"]).strip()
        unit = str(item["unit"]).strip()
        quote = str(item["source_quote"]).strip()
        year = item["fiscal_year"]
        if name not in METRIC_NAMES or not value or len(value) > 64 or not unit or len(unit) > 80:
            rejected["invalid_metric_value_or_unit"] += 1
            continue
        if isinstance(year, bool) or not isinstance(year, int) or year < 1900 or year > 2100:
            rejected["invalid_fiscal_year"] += 1
            continue
        if document_year is not None and str(year) != str(document_year):
            rejected["wrong_report_year"] += 1
            continue
        numeric_token = value.strip()
        if numeric_token.startswith("(") and numeric_token.endswith(")"):
            numeric_token = numeric_token[1:-1]
        if not re.fullmatch(r"[-+]?\d[\d., ]*", numeric_token):
            rejected["non_numeric_value"] += 1
            continue
        if len(quote) > 1000:
            rejected["non_finite_or_long_quote"] += 1
            continue
        quote_flat = _flat(quote)
        labels = METRIC_ONTOLOGY.get(name, {}).get("source_labels", ())
        exact_label = any(_flat(label) in quote_flat for label in labels)
        recovered_ocr_label = (
            allow_ocr_label_recovery and not exact_label
            and _ocr_label_match(labels, quote)
        )
        if (
            quote_flat not in page_flat
            or _flat(value) not in quote_flat
            or _flat(unit) not in page_flat
            or not (exact_label or recovered_ocr_label)
            or str(year) not in page_flat
        ):
            rejected["quote_not_verbatim_or_missing_label_value_year"] += 1
            continue
        valid.append({
            "metric_name": name,
            "metric_label": METRIC_NAMES[name],
            "candidate_values": [value],
            "unit": unit,
            "fiscal_year": year,
            "source_quote": quote,
            "source_label_match": "ocr_near_match" if recovered_ocr_label else "exact",
        })
    return valid, dict(rejected)


def extract_financial_candidates(
    chunks: list[dict], tables: list[dict], document: dict, llm,
    max_pages: int = MAX_FINANCIAL_PAGES,
) -> tuple[list[dict], list[dict]]:
    """Return pending review candidates and page-selection trace, with one call/page."""
    selected_pages = select_financial_pages(chunks, tables, max_pages)
    candidates = []
    provider_failed = False
    for page in selected_pages:
        if provider_failed:
            page["extraction_error"] = "Skipped after an earlier provider error"
            continue
        try:
            response = llm.generate(
                _prompt(document.get("company", "Unknown company"), document.get("fiscal_year"), page)
            )
            payload = json.loads(response)
            page["llm_metrics_returned"] = (
                len(payload.get("metrics", [])) if isinstance(payload, dict)
                and isinstance(payload.get("metrics"), list) else None
            )
            result, rejected = _validated_metrics(
                response, page["text"], document.get("fiscal_year"),
                allow_ocr_label_recovery=page["is_ocr_page"],
            )
            page["llm_metrics_accepted"] = len(result)
            page["llm_metrics_rejected"] = max(
                0, (page["llm_metrics_returned"] or 0) - len(result)
            )
            page["validation_rejections"] = rejected
            if not result:
                page["extraction_status"] = "no_valid_metrics"
        except Exception as error:
            provider_failed = True
            page["extraction_error"] = f"{type(error).__name__}: {error}"[:300]
            logger.warning(
                "Financial extraction stopped for %s after page %s: %s",
                document.get("document_id"), page["page_number"], type(error).__name__,
            )
            continue
        for metric in result:
            quote = metric["source_quote"]
            candidates.append({
                "company": document["company"],
                "metric_name": metric["metric_name"],
                "metric_label": metric["metric_label"],
                "candidate_values": metric["candidate_values"],
                "unit": metric["unit"],
                "fiscal_year": metric["fiscal_year"],
                "page_number": page["page_number"],
                "document_id": document["document_id"],
                "source_quote": quote,
                "source_quote_hash": hashlib.sha256(quote.encode()).hexdigest(),
                "source_url": document.get("official_url", ""),
                "allowed_roles": document["rbac"]["allowed_roles"],
                "status": "needs_review",
                "extraction_method": "llm_selected_financial_page",
                "extractor_model": getattr(llm, "model_name", llm.__class__.__name__),
                "prompt_version": PROMPT_VERSION,
                "selection_evidence": {
                    **page["selection_signals"],
                    **({"source_label_match": metric["source_label_match"]}
                       if metric["source_label_match"] != "exact" else {}),
                },
            })
    return candidates, selected_pages


def merge_candidate_sources(parser_candidates: list[dict], llm_candidates: list[dict]) -> list[dict]:
    """Prefer LLM values where present, while retaining parser-only metric evidence."""
    merged = {}
    for candidate in [*parser_candidates, *llm_candidates]:
        key = (
            candidate.get("document_id"), candidate.get("metric_name"),
            candidate.get("fiscal_year"), candidate.get("page_number"),
        )
        current = merged.get(key)
        if current is None or candidate.get("extraction_method") == "llm_selected_financial_page":
            merged[key] = candidate
    return list(merged.values())
