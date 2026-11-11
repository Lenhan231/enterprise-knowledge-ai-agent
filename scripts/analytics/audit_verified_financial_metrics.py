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
    "cost_of_goods_sold": ("cost of sales", "cost of goods sold"),
    "gross_profit": ("gross profit",),
    "profit_after_tax": ("profit after tax", "net profit after tax"),
    "profit_before_tax": ("profit before tax",),
    "total_assets": ("total assets",),
    "total_consolidated_revenue": ("total revenue", "consolidated net revenue", "net revenue"),
    "net_revenue": ("net revenue",),
}


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
        grouped = f"{int(value):,}"
        value_ok = grouped in page_text or str(int(value)) in page_text

    unit = str(observation.get("unit", "")).casefold()
    if unit == "billion vnd":
        unit_ok = ("billion" in normalized_text and "vnd" in normalized_text) or "tỷ đồng" in normalized_text
    elif unit == "million vnd":
        unit_ok = ("million" in normalized_text and "vnd" in normalized_text) or "triệu đồng" in normalized_text
    elif unit == "vnd":
        unit_ok = "vnd" in normalized_text or "đồng" in normalized_text
    else:
        unit_ok = bool(unit) and unit in normalized_text
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
    pdfs: dict[str, tuple[bytes, fitz.Document]] = {}
    results = []
    for item in analytics.get("financial", []):
        url = item.get("source_url")
        if not url or not item.get("page_number"):
            results.append({"metric_name": item.get("metric_name"), "passed": False, "error": "missing source URL or page"})
            continue
        if not _is_manifest_source(item.get("document_id", ""), url, manifest):
            results.append({"metric_name": item.get("metric_name"), "passed": False, "error": "source URL is not the document's manifest URL"})
            continue
        if url not in pdfs:
            request = Request(url, headers={"User-Agent": "EnterpriseKnowledgeMetricAudit/1.0"})
            with build_opener().open(request, timeout=60) as response:
                content = response.read()
            pdfs[url] = (content, fitz.open(stream=content, filetype="pdf"))
        content, pdf = pdfs[url]
        page_number = int(item["page_number"])
        if page_number < 1 or page_number > len(pdf):
            results.append({"metric_name": item.get("metric_name"), "page_number": page_number, "passed": False, "error": "page is outside source PDF"})
            continue
        page_text = pdf[page_number - 1].get_text()
        score = score_observation(item, page_text)
        results.append({
            "metric_name": item.get("metric_name"), "metric_label": item.get("metric_label"),
            "fiscal_year": item.get("fiscal_year"), "metric_value": item.get("metric_value"),
            "unit": item.get("unit"), "document_id": item.get("document_id"),
            "page_number": page_number, "source_url": url,
            "source_pdf_sha256": hashlib.sha256(content).hexdigest(),
            "page_text_sha256": hashlib.sha256(page_text.encode()).hexdigest(),
            **score,
        })
    for _, pdf in pdfs.values():
        pdf.close()
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
