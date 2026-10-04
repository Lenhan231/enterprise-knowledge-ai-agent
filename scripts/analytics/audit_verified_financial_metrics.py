#!/usr/bin/env python3
"""Read-only audit of published dashboard metrics against cited source PDF pages."""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

import fitz
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "artifacts/evaluation/verified-financial-metric-source-audit.json"
LABELS = {
    "cash_and_equivalents": ("cash and cash equivalents", "tiền và các khoản tương đương tiền"),
    "cost_of_goods_sold": ("cost of sales", "cost of goods sold", "giá vốn hàng bán"),
    "gross_profit": ("gross profit", "lợi nhuận gộp"),
    "inventory": ("inventories", "inventory", "hàng tồn kho"),
    "net_revenue": ("net revenue", "doanh thu thuần", "doanh thu thudn"),
    "profit_after_tax": ("profit after tax", "net profit after tax", "lợi nhuận sau thuế"),
    "profit_before_tax": ("profit before tax", "lợi nhuận trước thuế"),
    "total_assets": ("total assets", "tổng tài sản"),
    "total_consolidated_revenue": (
        "total consolidated revenue", "total revenue", "consolidated net revenue", "net revenue",
        "tổng doanh thu hợp nhất",
    ),
    "state_budget_contribution": ("contribution to the state budget", "đóng góp vào ngân sách nhà nước"),
}
_NUMBER_TOKEN = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)")
_SPACE_GROUPED_NUMBER = re.compile(r"(?<!\w)\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?!\w)")


def _unit_is_reported(unit: str, text: str) -> bool:
    unit = unit.casefold()
    if unit == "billion vnd":
        return ("billion" in text and "vnd" in text) or "tỷ đồng" in text
    if unit == "million vnd":
        return ("million" in text and "vnd" in text) or "triệu đồng" in text
    if unit == "vnd":
        return any(term in text for term in ("vnd", "vnđ", "đồng"))
    return bool(unit) and unit in text


def score_observation(observation: dict, page_text: str) -> dict:
    """Check page evidence for label, year, amount and reported unit."""
    metric = observation.get("metric_name")
    normalized_text = re.sub(r"\s+", " ", page_text).casefold()
    aliases = LABELS.get(metric, (str(observation.get("metric_label", "")).casefold(),))
    label_ok = any(alias in normalized_text for alias in aliases)
    year_ok = str(observation.get("fiscal_year", "")) in normalized_text

    value = observation.get("metric_value")
    value_ok = False
    if isinstance(value, (int, float)) and int(value) == value:
        expected_digits = str(int(value))
        source_number_tokens = [*_NUMBER_TOKEN.findall(page_text), *_SPACE_GROUPED_NUMBER.findall(page_text)]
        value_ok = any(
            re.sub(r"\D", "", token) == expected_digits
            for token in source_number_tokens
        )

    unit_ok = _unit_is_reported(str(observation.get("unit", "")), normalized_text)
    checks = {"metric_label": label_ok, "fiscal_year": year_ok, "value": value_ok, "unit": unit_ok}
    return {"checks": checks, "passed": all(checks.values())}


def _read_json(opener, url: str) -> dict:
    with opener.open(url, timeout=30) as response:
        return json.load(response)


def _is_manifest_source(document_id: str, url: str, manifest: dict) -> bool:
    documents = manifest.get("documents", [])
    approved = {
        item.get("document_id"): item.get("source_url")
        for item in documents
    }
    return bool(
        urlsplit(url).scheme == "https"
        and approved.get(document_id) == url
    )


def linked_parser_chunk_text(observation: dict, repository) -> tuple[str, str] | None:
    """Use the exact indexed source chunk only when its stored provenance hash matches."""
    document_id = observation.get("document_id")
    chunk_index = observation.get("source_chunk_index")
    expected_hash = observation.get("source_content_hash")
    if not document_id or not isinstance(chunk_index, int) or not expected_hash:
        return None
    chunks = repository.get_document_chunks(
        document_id, limit=3, offset=max(0, chunk_index - 1),
    )
    for chunk in chunks:
        content = chunk.get("content") or ""
        metadata = chunk.get("metadata") or {}
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if (chunk.get("chunk_index") == chunk_index
                and str(metadata.get("page_number")) == str(observation.get("page_number"))
                and content_hash == expected_hash):
            return content, content_hash
    return None


def linked_parser_chunk(observation: dict, repository) -> dict | None:
    """Resolve the exact stored chunk ID and validate its page/index/content hash."""
    chunk_id = observation.get("source_chunk_id")
    document_id = observation.get("document_id")
    if chunk_id is None or not document_id:
        return None
    chunk = repository.get_document_chunk(int(chunk_id), str(document_id))
    if chunk is None:
        return None
    content = chunk.get("content") or ""
    metadata = chunk.get("metadata") or {}
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if (
        chunk.get("chunk_index") != observation.get("source_chunk_index")
        or str(metadata.get("page_number")) != str(observation.get("page_number"))
        or content_hash != observation.get("source_content_hash")
    ):
        return None
    return {**chunk, "content_sha256": content_hash}


def linked_document_unit_pages(observation: dict, chunks: list[dict]) -> list[dict]:
    """Find same-metric unit declarations elsewhere in this document's indexed chunks."""
    document_id = observation.get("document_id")
    metric = observation.get("metric_name")
    fiscal_year = str(observation.get("fiscal_year", ""))
    if not document_id or not metric:
        return []
    aliases = LABELS.get(metric, (str(observation.get("metric_label", "")).casefold(),))
    matches = []
    for chunk in chunks:
        content = chunk.get("content") or ""
        text = re.sub(r"\s+", " ", content).casefold()
        metadata = chunk.get("metadata") or {}
        page_number = metadata.get("page_number")
        if (page_number is not None and fiscal_year in text
                and _unit_is_reported(str(observation.get("unit", "")), text)
                and any(alias in text for alias in aliases)):
            matches.append({
                "page_number": page_number,
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            })
    return matches


def audit(base_url: str, username: str, password: str) -> dict:
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    login = Request(
        f"{base_url.rstrip('/')}/api/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with opener.open(login, timeout=15) as response:
        identity = json.load(response)
    if identity.get("role") != "admin":
        raise RuntimeError("The configured account is not an admin")

    analytics = _read_json(opener, f"{base_url.rstrip('/')}/api/analytics")
    manifest = json.loads((ROOT / "data/vietnam_enterprises/manifest.json").read_text(encoding="utf-8"))
    pdfs: dict[str, tuple[bytes, fitz.Document, str]] = {}
    results = []
    chunk_repository = None
    indexed_chunks_by_document: dict[str, list[dict]] = {}
    for item in analytics.get("financial", []):
        url = item.get("source_url")
        document_id = str(item.get("document_id") or "")
        if not item.get("page_number"):
            results.append({"metric_name": item.get("metric_name"), "passed": False, "error": "missing source page"})
            continue
        if url:
            if not _is_manifest_source(document_id, url, manifest):
                results.append({"metric_name": item.get("metric_name"), "passed": False,
                                "error": "source URL is not the document's manifest URL"})
                continue
            source_key, source_kind = url, "manifest_pdf"
            if source_key not in pdfs:
                request = Request(url, headers={"User-Agent": "EnterpriseKnowledgeMetricAudit/1.0"})
                with build_opener().open(request, timeout=60) as response:
                    content = response.read()
                pdfs[source_key] = (content, fitz.open(stream=content, filetype="pdf"), source_kind)
        elif document_id.startswith("UPLOAD-"):
            source_key, source_kind = f"uploaded:{document_id}", "private_uploaded_pdf"
            if source_key not in pdfs:
                request = Request(f"{base_url.rstrip('/')}/api/admin/processing/{document_id}/source")
                with opener.open(request, timeout=60) as response:
                    content = response.read()
                pdfs[source_key] = (content, fitz.open(stream=content, filetype="pdf"), source_kind)
        else:
            results.append({"metric_name": item.get("metric_name"), "passed": False,
                            "error": "source is neither manifest PDF nor an uploaded PDF"})
            continue
        content, pdf, source_kind = pdfs[source_key]
        page_number = int(item["page_number"])
        if page_number < 1 or page_number > len(pdf):
            results.append({"metric_name": item.get("metric_name"), "page_number": page_number, "passed": False, "error": "page is outside source PDF"})
            continue
        page_text = pdf[page_number - 1].get_text()
        evidence_kind = "pdf_text_layer"
        if chunk_repository is None:
            from core.database.document_chunks_repository import DocumentChunkRepository
            chunk_repository = DocumentChunkRepository()
        linked_chunk = linked_parser_chunk(item, chunk_repository)
        parser_chunk_sha256 = linked_chunk.get("content_sha256") if linked_chunk else None
        if not page_text.strip():
            if linked_chunk is None:
                results.append({"metric_name": item.get("metric_name"), "page_number": page_number,
                                "passed": False,
                                "error": "PDF page is image-only and no hash-matching linked parser chunk was found"})
                continue
            page_text = linked_chunk["content"]
            evidence_kind = "linked_indexed_parser_chunk"
        score = score_observation(item, page_text)
        score["checks"]["linked_source_chunk_matches_database"] = linked_chunk is not None
        score["passed"] = all(score["checks"].values())
        unit_context_pages = []
        if not score["checks"]["unit"] and source_kind == "private_uploaded_pdf":
            if chunk_repository is None:
                from core.database.document_chunks_repository import DocumentChunkRepository
                chunk_repository = DocumentChunkRepository()
            indexed_chunks_by_document.setdefault(document_id, [])
            if not indexed_chunks_by_document[document_id]:
                indexed_chunks_by_document[document_id] = chunk_repository.get_document_chunks(
                    document_id, limit=100, offset=0,
                )
            unit_context_pages = linked_document_unit_pages(
                item, indexed_chunks_by_document[document_id],
            )
            if unit_context_pages:
                score["checks"]["unit"] = True
                score["passed"] = all(score["checks"].values())
        results.append({
            "metric_name": item.get("metric_name"), "metric_label": item.get("metric_label"),
            "fiscal_year": item.get("fiscal_year"), "metric_value": item.get("metric_value"),
            "unit": item.get("unit"), "document_id": item.get("document_id"),
            "page_number": page_number, "source_url": url, "source_kind": source_kind,
            "entry_method": item.get("entry_method"),
            "source_chunk_id": item.get("source_chunk_id"),
            "source_chunk_index": item.get("source_chunk_index"),
            "source_content_hash": item.get("source_content_hash"),
            "evidence_kind": evidence_kind,
            "parser_chunk_sha256": parser_chunk_sha256,
            "unit_context_pages": unit_context_pages,
            "source_pdf_sha256": hashlib.sha256(content).hexdigest(),
            "page_text_sha256": hashlib.sha256(page_text.encode()).hexdigest(),
            **score,
        })
    for _, pdf, _ in pdfs.values():
        pdf.close()
    if chunk_repository is not None:
        chunk_repository.close()
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "authenticated admin analytics API plus cited official PDF pages",
        "verified_observation_count": len(analytics.get("financial", [])),
        "pending_candidate_count": len(analytics.get("candidates", [])),
        "audited": len(results), "passed": sum(row["passed"] for row in results),
        "failed": sum(not row["passed"] for row in results), "observations": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("APP_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=True)
    username = os.getenv("DEMO_ADMIN_USERNAME")
    password = os.getenv("DEMO_ADMIN_PASSWORD")
    if not username or not password:
        raise SystemExit("DEMO_ADMIN_USERNAME and DEMO_ADMIN_PASSWORD are required in .env")
    try:
        result = audit(args.base_url, username, password)
    except Exception as error:
        raise SystemExit(f"Metric source audit failed: {type(error).__name__}: {error}") from error
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: result[key] for key in ("verified_observation_count", "pending_candidate_count", "audited", "passed", "failed")}
    summary["output"] = str(output.relative_to(ROOT) if output.is_relative_to(ROOT) else output)
    print(json.dumps(summary, indent=2))
    return 0 if result["failed"] == 0 and result["audited"] == result["verified_observation_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
