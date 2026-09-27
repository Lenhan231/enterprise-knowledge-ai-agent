#!/usr/bin/env python3
"""Evaluate authenticated routed QA on the labeled live Vinamilk case set."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.main import app  # noqa: E402
from core.rag.rag_service import extract_source_ids  # noqa: E402

_CASES = REPO_ROOT / "data/evaluation/vinamilk_qa_cases.json"
_OUTPUT = REPO_ROOT / "artifacts/evaluation/vinamilk-app-qa-suite.json"
_ACCOUNT_BY_ROLE = {
    "employee": "viewer",
    "finance_analyst": "analyst",
    "sustainability_analyst": "sustainability_analyst",
}


def _login(client: TestClient, account: str) -> None:
    username = os.getenv(f"DEMO_{account.upper()}_USERNAME")
    password = os.getenv(f"DEMO_{account.upper()}_PASSWORD")
    if not username or not password:
        raise RuntimeError(f"DEMO_{account.upper()} credentials are required in .env")
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    if response.status_code != 200:
        raise RuntimeError(f"Demo {account} login failed with HTTP {response.status_code}")


def _fact_present(expected: str, answer: str) -> bool:
    digits = re.sub(r"[^0-9]", "", expected)
    if digits:
        return digits in re.sub(r"[^0-9]", "", answer)
    normalize = lambda text: " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))
    return normalize(expected) in normalize(answer)


def score_case(case: dict, payload: dict) -> dict:
    answer = payload.get("answer", "")
    citations = payload.get("citations", [])
    expected_insufficient = case.get("expect_insufficient", False)
    expected_facts = case.get("expected_key_facts", [])
    expected_groups = case.get("expected_key_fact_groups", [])
    missing_facts = [fact for fact in expected_facts if not _fact_present(fact, answer)]
    failed_groups = [
        group for group in expected_groups
        if not any(_fact_present(alternative, answer) for alternative in group)
    ]
    expected_document_id = case.get("expected_document_id")
    cited_documents = {item.get("document_id") for item in citations}
    citation_ids = {item.get("id") for item in citations}
    answer_citations = set(extract_source_ids(answer))
    checks = {
        "expected_agent": payload.get("agent") == case.get("expected_agent"),
        "expected_abstention": payload.get("insufficient_context") is expected_insufficient,
        "expected_facts": not missing_facts and not failed_groups,
        "expected_source_document": expected_insufficient or expected_document_id in cited_documents,
        "citation_integrity": citation_ids == answer_citations,
        "denial_has_no_sources": not expected_insufficient or not citations,
    }
    return {
        "id": case["id"],
        "role": case["role"],
        "question": case["question"],
        "passed": all(checks.values()),
        "checks": checks,
        "missing_facts": missing_facts,
        "failed_fact_groups": failed_groups,
        "cited_document_ids": sorted(doc for doc in cited_documents if doc),
        "citation_pages": sorted({item.get("page_number") for item in citations if item.get("page_number") is not None}),
        "agent": payload.get("agent"),
        "insufficient_context": payload.get("insufficient_context"),
        "answer": answer,
    }


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=True)
    cases_data = json.loads(_CASES.read_text(encoding="utf-8"))
    results = []
    current_role = None
    with TestClient(app) as client:
        for case in cases_data["cases"]:
            account = _ACCOUNT_BY_ROLE[case["role"]]
            if account != current_role:
                if current_role:
                    client.post("/api/auth/logout")
                _login(client, account)
                current_role = account
            started = time.perf_counter()
            response = client.post("/api/ask", json={"question": case["question"]})
            elapsed = time.perf_counter() - started
            if response.status_code == 200:
                result = score_case(case, response.json())
            else:
                result = {
                    "id": case["id"], "role": case["role"], "question": case["question"],
                    "passed": False, "http_status": response.status_code,
                    "error": response.json().get("detail", "Request failed"),
                }
            result["latency_seconds"] = round(elapsed, 3)
            results.append(result)
            print(f"{result['id']}: {'PASS' if result['passed'] else 'FAIL'} ({elapsed:.1f}s)", file=sys.stderr, flush=True)
        if current_role:
            client.post("/api/auth/logout")

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "route": "POST /api/ask",
        "dataset": str(_CASES.relative_to(REPO_ROOT)),
        "dataset_sha256": __import__("hashlib").sha256(_CASES.read_bytes()).hexdigest(),
        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        "case_count": len(results),
        "passed": sum(item["passed"] for item in results),
        "failed": sum(not item["passed"] for item in results),
        "mean_latency_seconds": round(sum(item["latency_seconds"] for item in results) / len(results), 3) if results else None,
        "limitations": "Live authenticated app-route evaluation for the labeled public finance, sustainability, product and denial cases only. Automated exact-fact/source/route checks do not measure semantic faithfulness or human usefulness; private HR, contracts, invoices, manufacturing and customer-service documents are not in this corpus.",
        "results": results,
    }
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(_OUTPUT), "passed": report["passed"], "failed": report["failed"]}, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
