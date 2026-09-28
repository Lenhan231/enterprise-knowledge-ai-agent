#!/usr/bin/env python3
"""Run the proposal's 12 business cases through the authenticated app API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.main import app  # noqa: E402
from core.rag.rag_service import extract_source_ids  # noqa: E402
from evaluate_proposal_case_coverage import evaluate_coverage  # noqa: E402

ROUTES = ROOT / "data/evaluation/proposal_business_route_cases.json"
LABELS = ROOT / "data/evaluation/proposal_business_case_corpus_labels.json"
MANIFEST = ROOT / "data/vietnam_enterprises/manifest.json"
OUTPUT = ROOT / "artifacts/evaluation/proposal-business-app-evaluation.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_output(path: Path) -> Path:
    output = path if path.is_absolute() else ROOT / path
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        with output.open("a", encoding="utf-8"):
            pass
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".business-eval-check-") as probe:
        probe.write(b"x" * 32768)
        probe.flush()
    return output


_NUMBER_TOKEN = re.compile(r"(?<!\w)\d(?:[\d.,\u00a0\u202f ]*\d)?(?!\w)")


def _has_fact(value: str, text: str) -> bool:
    digits = "".join(char for char in value if char.isdigit())
    if not digits:
        return value.casefold() in text.casefold()
    return any(
        "".join(char for char in token if char.isdigit()) == digits
        for token in _NUMBER_TOKEN.findall(text)
    )


def _has_source_location(citation: dict) -> bool:
    page = citation.get("page_number")
    has_page = isinstance(page, int) and not isinstance(page, bool) and page > 0
    url = citation.get("official_url")
    return bool(citation.get("document_id")) and (has_page or isinstance(url, str) and url.startswith("https://"))


def _has_domain_counts(rows: object) -> bool:
    if not isinstance(rows, list) or not rows:
        return False
    count_keys = {"count", "doc_count", "document_count", "documents", "total_documents", "count_documents"}
    return all(
        isinstance(row, dict)
        and "domain" in row
        and any(key.casefold() in count_keys and isinstance(value, (int, float)) and not isinstance(value, bool)
                for key, value in row.items())
        for row in rows
    )


def score_case(case: dict, payload: dict) -> dict:
    answer = payload.get("answer", "")
    citations = payload.get("citations", [])
    cited_documents = {item.get("document_id") for item in citations if item.get("document_id")}
    citation_ids = {item.get("id") for item in citations if item.get("id")}
    answer_citations = set(extract_source_ids(answer))
    coverage = case["corpus_coverage"]
    allowed_sources = set(case.get("source_document_ids", []))
    insufficient = payload.get("insufficient_context") is True

    checks = {
        "expected_route": payload.get("agent") == case["expected_route"],
        "citation_integrity": citation_ids == answer_citations,
        "no_citation_validation_failure": not payload.get("citation_validation_failed", False),
        "citations_have_source_locations": all(_has_source_location(item) for item in citations),
    }
    if coverage == "unsupported":
        checks["unsupported_case_abstains"] = insufficient and not citations
    elif coverage == "partial":
        if case["id"] == "invoice-information-retrieval":
            checks["partial_case_uses_labeled_source"] = (
                not insufficient and bool(citations) and cited_documents.issubset(allowed_sources)
            )
        elif case["id"] == "internal-document-search":
            checks["employee_access_answer_uses_code_source"] = (
                not insufficient and bool(citations) and cited_documents == {"VNM-CODE-2025-EN"}
            )
            normalized_answer = answer.casefold()
            checks["dedicated_access_policy_absence_is_disclosed"] = any(term in normalized_answer for term in (
                "information system policy is not", "information system policy was not",
                "separate information system policy", "dedicated information system policy",
                "no information system policy", "policy is not included",
                "chưa có chính sách hệ thống thông tin riêng",
                "không có chính sách hệ thống thông tin riêng",
            ))
            checks["answer_qualifies_document_type"] = "code of conduct" in normalized_answer
        else:
            checks["partial_case_abstains_or_uses_labeled_source"] = (
                (insufficient and not citations)
                or (bool(citations) and cited_documents.issubset(allowed_sources))
            )
        if case["id"] == "invoice-information-retrieval" and not insufficient:
            normalized_answer = answer.casefold()
            checks["invoice_disclosure_is_narrowly_grounded"] = (
                "VNM-AR-2020-VI" in cited_documents
                and _has_fact("60", answer)
                and any(term in normalized_answer for term in ("related", "liên quan"))
                and any(term in normalized_answer for term in (
                    "within 60 days", "within sixty days", "60 days from", "60 ngày kể từ",
                ))
            )
            checks["invoice_document_absence_is_disclosed"] = any(term in normalized_answer for term in (
                "not an invoice", "not itself an invoice", "no invoice document",
                "no invoice was found", "no invoice is present", "no invoice was provided",
                "invoice was not provided", "no invoice is included", "no invoice was supplied",
                "invoice is not included", "not present in the retrieved",
                "không phải hóa đơn", "không tìm thấy hóa đơn", "không có hóa đơn trong tài liệu",
                "chưa cung cấp hóa đơn",
            ))
    elif case["id"] == "financial-report-analysis":
        financial_sources = [item for item in citations if item.get("document_id") == "VNM-AR-2024-VI"]
        checks["source_document"] = bool(financial_sources)
        checks["revenue_and_profit_values"] = _has_fact("61824", answer) and _has_fact("9453", answer)
        financial_evidence = " ".join(str(item.get("excerpt") or "") for item in financial_sources)
        checks["financial_values_in_cited_evidence"] = (
            _has_fact("61824", financial_evidence) and _has_fact("9453", financial_evidence)
        )
        checks["reported_magnitude_unit"] = any(term in answer.casefold() for term in ("billion", "tỷ"))
    elif case["id"] == "business-intelligence-analytics":
        data = payload.get("data") or {}
        checks["dynamic_domain_count_rows"] = _has_domain_counts(data.get("results"))
        checks["result_rows_have_sources"] = bool(citations) and all(
            isinstance(row, dict) and row.get("evidence_document_ids")
            and set(row["evidence_document_ids"]).issubset(cited_documents)
            for row in (data.get("results") or [])
        )
    else:
        checks["supported_or_partial_answer_has_labeled_source"] = bool(citations) and bool(cited_documents & allowed_sources)

    return {
        "id": case["id"],
        "corpus_coverage": coverage,
        "expected_outcome": case["expected_outcome"],
        "expected_route": case["expected_route"],
        "actual_route": payload.get("agent"),
        "passed": all(checks.values()),
        "checks": checks,
        "insufficient_context": payload.get("insufficient_context"),
        "cited_document_ids": sorted(cited_documents),
        "citation_pages": sorted({item.get("page_number") for item in citations if item.get("page_number") is not None}),
        "answer": answer,
        "data_result_count": len((payload.get("data") or {}).get("results", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", action="append", help="Run selected case IDs; may be repeated")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--model", help="Override GROQ_MODEL for this run and record the selected model")
    args = parser.parse_args()
    try:
        output = prepare_output(args.output)
    except OSError as error:
        parser.error(f"cannot write evaluation output before model calls: {error}")

    routes, labels, manifest = _read(ROUTES), _read(LABELS), _read(MANIFEST)
    labeled = evaluate_coverage(routes, labels, manifest)
    cases = labeled["cases"]
    if args.case_id:
        unknown = set(args.case_id) - {case["id"] for case in cases}
        if unknown:
            parser.error(f"unknown case IDs: {sorted(unknown)}")
        selected = set(args.case_id)
        cases = [case for case in cases if case["id"] in selected]

    load_dotenv(ROOT / ".env", override=True)
    if args.model:
        os.environ["GROQ_MODEL"] = args.model
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    username, password = os.getenv("DEMO_ADMIN_USERNAME"), os.getenv("DEMO_ADMIN_PASSWORD")
    if not username or not password:
        parser.error("DEMO_ADMIN_USERNAME and DEMO_ADMIN_PASSWORD are required in .env")

    results = []
    stop_reason = None
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": username, "password": password})
        if login.status_code != 200:
            parser.error(f"Admin demo login failed with HTTP {login.status_code}")
        for case in cases:
            started = time.perf_counter()
            response = client.post("/api/ask", json={"question": case["question"]})
            elapsed = time.perf_counter() - started
            if response.status_code == 200:
                result = score_case(case, response.json())
            else:
                result = {
                    "id": case["id"], "corpus_coverage": case["corpus_coverage"],
                    "expected_route": case["expected_route"], "passed": False,
                    "http_status": response.status_code,
                    "error": response.json().get("detail", "Request failed"),
                    "checks": {},
                }
            result["latency_seconds"] = round(elapsed, 3)
            results.append(result)
            print(f"{case['id']}: {'PASS' if result['passed'] else 'FAIL'} ({elapsed:.1f}s)", file=sys.stderr, flush=True)
            if response.status_code == 429:
                stop_reason = "provider_rate_limit"
                break
            if response.status_code >= 500:
                stop_reason = "server_error"
                break
        client.post("/api/auth/logout")

    attempted_ids = {result["id"] for result in results}
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "route": "POST /api/ask",
        "corpus_id": labeled["corpus_id"],
        "corpus_manifest_sha256": labeled["corpus_manifest_sha256"],
        "route_dataset_sha256": labeled["route_cases_sha256"],
        "coverage_dataset_sha256": hashlib.sha256(LABELS.read_bytes()).hexdigest(),
        "model": model,
        "actor_role": "admin",
        "case_count": len(cases),
        "attempted_count": len(results),
        "unrun_case_ids": [case["id"] for case in cases if case["id"] not in attempted_ids],
        "stop_reason": stop_reason,
        "passed": sum(result["passed"] for result in results),
        "failed": sum(not result["passed"] for result in results),
        "mean_latency_seconds": round(sum(row["latency_seconds"] for row in results) / len(results), 3) if results else None,
        "results": results,
        "limitations": [
            "This is a single authenticated admin run over the public Vinamilk corpus; it is not a role-matrix test.",
            "Supported and unsupported outcomes have deterministic route, source, value, abstention and result-shape checks.",
            "Partial HR, compliance and executive cases still need blinded semantic review; these labels do not prove private-domain capability.",
        ],
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "attempted": report["attempted_count"], "passed": report["passed"], "failed": report["failed"], "stop_reason": stop_reason}, ensure_ascii=False))
    return 0 if not report["failed"] and not report["unrun_case_ids"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
