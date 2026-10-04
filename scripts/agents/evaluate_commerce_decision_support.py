#!/usr/bin/env python3
"""Replay the Commerce decision benchmark through the authenticated app API."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from app.main import app  # noqa: E402
from core.rag.rag_service import extract_source_ids  # noqa: E402

BENCHMARK = ROOT / "data/evaluation/commerce_decision_benchmark.json"
MANIFEST = ROOT / "data/commerce_knowledge/manifest.json"
DEFAULT_OUTPUT = ROOT / "artifacts/evaluation/commerce-decision-support-live.json"
_NUMBER_TOKEN = re.compile(r"(?<!\d)\d+(?:[.,\u00a0\u202f]\d+)*(?!\d)")
_GOLD_FIELD_ALIASES = {
    "snapshots": ("sku_snapshots",),
    "overstock_products": ("overstock_count",),
    "stockout_products": ("stockout_count",),
    "tagged": ("used_promotion",),
    "campaign": ("promo_name",),
    "net_item_sales": ("net_sales",),
    "avg_days": ("avg_transit_days", "avg_transit_time_days"),
    "avg_transit_days": ("avg_transit_time_days", "avg_days"),
    "avg_fee": ("avg_shipping_fee",),
}
_YEAR_METRIC = re.compile(r"^(?P<year>20\d{2})_(?P<metric>avg_days|avg_fee)$")
_TIME_DIMENSIONS = ("year", "fiscal_year", "snapshot_date")
_PRIMARY_DIMENSIONS = ("category", "region", "campaign", "used_promotion", "tagged")


def _decimal_interpretations(token: str) -> set[Decimal]:
    """Handle decimal and thousands separators used in English and Vietnamese answers."""
    value = re.sub(r"[\s\u00a0\u202f]", "", token)
    interpretations = {value}
    if "," in value and "." in value:
        decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
        grouping_separator = "." if decimal_separator == "," else ","
        interpretations = {value.replace(grouping_separator, "").replace(decimal_separator, ".")}
    elif "," in value:
        interpretations = {value.replace(",", "."), value.replace(",", "")}
    elif "." in value:
        interpretations = {value, value.replace(".", "")}
    parsed = set()
    for candidate in interpretations:
        try:
            parsed.add(Decimal(candidate))
        except InvalidOperation:
            continue
    return parsed


def missing_gold_numeric_facts(case: dict, answer: str) -> list[str]:
    expected = case.get("required_numeric_facts", [])
    answer_numbers = {
        number
        for token in _NUMBER_TOKEN.findall(answer)
        for number in _decimal_interpretations(token)
    }
    missing = []
    for value in expected:
        number = Decimal(str(value))
        precision = max(0, -number.as_tuple().exponent)
        quantum = Decimal(1).scaleb(-precision)
        rounded_answers = {
            candidate.quantize(quantum, rounding=ROUND_HALF_UP)
            for candidate in answer_numbers
        }
        if number.quantize(quantum, rounding=ROUND_HALF_UP) not in rounded_answers:
            missing.append(str(value))
    return missing


def _expand_gold_observations(case: dict) -> list[dict]:
    """Convert wide year/measure gold rows into the grouped rows returned by SQL."""
    expected_rows = []
    for observation in case.get("gold_observations", []):
        if not isinstance(observation, dict):
            continue
        if "available" in observation or "missing" in observation:
            continue
        static = {key: value for key, value in observation.items() if not _YEAR_METRIC.match(key)}
        yearly = {}
        for key, value in observation.items():
            match = _YEAR_METRIC.match(key)
            if not match:
                continue
            year = int(match.group("year"))
            metric = match.group("metric")
            yearly.setdefault(year, dict(static))["year"] = year
            yearly[year][metric] = value
        if yearly:
            expected_rows.extend(yearly.values())
        elif all(isinstance(value, (str, int, float, bool)) or value is None for value in observation.values()):
            expected_rows.append(observation)
    return expected_rows


def _evidence_observation_rows(citations: list[dict]) -> list[dict]:
    rows = []
    decoder = json.JSONDecoder()
    for citation in citations:
        if citation.get("source_type") != "commerce_sql":
            continue
        observations = citation.get("commerce_observations")
        if not isinstance(observations, list):
            excerpt = str(citation.get("excerpt") or "")
            start = excerpt.find("[")
            try:
                observations, _ = decoder.raw_decode(excerpt, start) if start >= 0 else (None, 0)
            except json.JSONDecodeError:
                observations = None
        if isinstance(observations, list):
            scoped_year = _single_scoped_year(citation.get("sql_query"))
            for row in observations:
                if not isinstance(row, dict):
                    continue
                # A constant year filter is valid period evidence even when the
                # query does not redundantly project that same year in every row.
                if scoped_year is not None and not any(key in row for key in _TIME_DIMENSIONS):
                    row = {**row, "year": scoped_year}
                rows.append(row)
    return rows


def _single_scoped_year(sql: str | None) -> int | None:
    if not sql:
        return None
    where = re.search(r"\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|$)", sql, re.I | re.S)
    if not where or re.search(r"\bOR\b", where.group(1), re.I):
        return None
    years = set(re.findall(
        r"EXTRACT\s*\(\s*YEAR\s+FROM\s+[\w.]+\s*\)\s*=\s*'?((?:19|20)\d{2})'?",
        where.group(1),
        re.I,
    ))
    return int(next(iter(years))) if len(years) == 1 else None


def _matches_observation_value(actual, expected) -> bool:
    if isinstance(expected, bool):
        return actual is expected
    if expected is None:
        return actual is None
    if isinstance(expected, (str, int, float)):
        try:
            expected_number = Decimal(str(expected))
            actual_number = Decimal(str(actual))
        except InvalidOperation:
            return str(actual).casefold() == str(expected).casefold()
        precision = max(0, -expected_number.as_tuple().exponent)
        quantum = Decimal(1).scaleb(-precision)
        return actual_number.quantize(quantum, rounding=ROUND_HALF_UP) == expected_number.quantize(
            quantum, rounding=ROUND_HALF_UP,
        )
    return False


def _gold_observation_requirements(case: dict) -> list[dict]:
    """Keep requested numeric facts and enough dimensions to verify their grouping."""
    rows = _expand_gold_observations(case)
    if not rows:
        return []
    facts = case.get("required_numeric_facts", [])
    dimensions = [key for key in _TIME_DIMENSIONS if any(key in row for row in rows)]
    dimensions.extend(
        key for key in _PRIMARY_DIMENSIONS
        if key not in dimensions and any(key in row for row in rows)
    )
    candidates = list(dict.fromkeys(
        key for row in rows for key, value in row.items()
        if key not in dimensions and (isinstance(value, bool) or isinstance(value, str))
    ))
    while candidates:
        signatures = [tuple(str(row.get(key)) for key in dimensions) for row in rows]
        if len(set(signatures)) == len(rows):
            break
        best = max(candidates, key=lambda key: len({
            tuple(str(row.get(name)) for name in (*dimensions, key)) for row in rows
        }))
        dimensions.append(best)
        candidates.remove(best)

    requirements = []
    for row in rows:
        required = {key: row[key] for key in dimensions if key in row}
        for key, value in row.items():
            if isinstance(value, bool) or value is None or isinstance(value, (dict, list)):
                continue
            if any(_matches_observation_value(value, fact) for fact in facts):
                required[key] = value
        if required:
            requirements.append(required)
    return requirements


def missing_gold_observations(case: dict, citations: list[dict]) -> list[dict]:
    """Return expected dimension/value groups absent from structured cited SQL evidence."""
    actual_rows = _evidence_observation_rows(citations)
    missing = []
    for expected_row in _gold_observation_requirements(case):
        matched = False
        for actual_row in actual_rows:
            if all(
                (any(
                    field in actual_row and _matches_observation_value(actual_row[field], expected_value)
                    for field in (key, *_GOLD_FIELD_ALIASES.get(key, ()))
                ) or (
                    key in _TIME_DIMENSIONS
                    and isinstance(expected_value, int)
                    and any(
                        re.search(rf"(?<!\d){expected_value}(?!\d)", str(actual_row.get(field, "")))
                        for field in ("campaign", "promo_name")
                    )
                ))
                for key, expected_value in expected_row.items()
            ):
                matched = True
                break
        if not matched:
            missing.append(expected_row)
    return missing


def load_cases(benchmark: dict) -> list[dict]:
    return [
        {**case, "domain": domain}
        for domain, profile in benchmark["domains"].items()
        for case in profile["cases"]
    ]


def score_case(case: dict, response_payload: dict, expected_tables: set[str]) -> dict:
    citations = response_payload.get("citations") or []
    answer = str(response_payload.get("answer") or "")
    citation_ids = {str(item.get("id")) for item in citations if item.get("id")}
    answer_ids = set(extract_source_ids(answer))
    sql_citations = [item for item in citations if item.get("source_type") == "commerce_sql"]
    document_citations = [item for item in citations if item.get("source_type") == "document"]
    question_specific_sql = next((item for item in sql_citations if item.get("sql_query")), None)
    sql_expected = case.get("question_specific_sql_expected", True)
    schema_gap_cited = any(
        item.get("source_type") == "commerce_schema"
        and item.get("commerce_domain") == case["domain"]
        for item in citations
    )
    checks = {
        "citation_integrity": citation_ids == answer_ids,
        "citation_validation": not response_payload.get("citation_validation_failed", False),
        "domain_sql_evidence": (
            any(item.get("commerce_domain") == case["domain"]
                and expected_tables.intersection(item.get("source_tables") or [])
                for item in sql_citations)
            if sql_expected else (
                response_payload.get("question_sql_fallback") == "requested_dimension_unavailable"
                and schema_gap_cited
            )
        ),
        "question_specific_sql_available": question_specific_sql is not None,
        "question_specific_sql_requirement_met": (
            (question_specific_sql is not None) == sql_expected
        ),
        "sql_dataset_provenance": all(
            "Synthetic Kaggle" in str(item.get("dataset_note") or "")
            for item in sql_citations
        ),
        "document_source_locations": all(
            bool(item.get("document_id"))
            and (isinstance(item.get("page_number"), int)
                 or str(item.get("source_url") or "").startswith("https://"))
            for item in document_citations
        ),
        "document_scope_attribution": all(
            bool(item.get("evidence_class")) and bool(item.get("reference_applicability"))
            for item in document_citations
        ),
    }
    if case.get("requires_operating_reference"):
        checks["operating_reference_present"] = bool(document_citations)
    missing_gold_values = missing_gold_numeric_facts(case, answer)
    gold_numeric_coverage_passed = not missing_gold_values
    checks["required_gold_numeric_facts_present"] = gold_numeric_coverage_passed
    missing_gold_rows = missing_gold_observations(case, citations)
    gold_observation_coverage_applicable = bool(_expand_gold_observations(case))
    gold_observation_coverage_passed = not missing_gold_rows if gold_observation_coverage_applicable else None
    if gold_observation_coverage_applicable:
        checks["gold_observation_rows_present_in_cited_sql"] = gold_observation_coverage_passed
    citation_domain_passed = all(
        passed for name, passed in checks.items()
        if name not in {"question_specific_sql_available", "required_gold_numeric_facts_present"}
    )
    return {
        "case_id": case["id"],
        "domain": case["domain"],
        "question": case["question"],
        "decision_analysis": response_payload.get("decision_analysis"),
        "citation_validation_failed": response_payload.get("citation_validation_failed", False),
        "passed": all(
            passed for name, passed in checks.items()
            if name != "question_specific_sql_available"
        ),
        "checks": checks,
        "citation_domain_checks_passed": citation_domain_passed,
        "question_specific_sql_passed": checks["question_specific_sql_available"],
        "gold_numeric_coverage_passed": gold_numeric_coverage_passed,
        "gold_numeric_coverage_applicable": bool(case.get("required_numeric_facts")),
        "missing_gold_numeric_facts": missing_gold_values,
        "gold_observation_coverage_passed": gold_observation_coverage_passed,
        "gold_observation_coverage_applicable": gold_observation_coverage_applicable,
        "missing_gold_observation_rows": missing_gold_rows,
        "citations": citations,
        "question_specific_sql_used": question_specific_sql is not None,
        "sql_generation_provider": question_specific_sql.get("sql_generation_provider") if question_specific_sql else None,
        "question_sql_fallback": response_payload.get("question_sql_fallback"),
        "answer_generation_provider": response_payload.get("generation_provider"),
        "token_usage": response_payload.get("token_usage"),
        "answer": answer,
        "semantic_review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", action="append", help="Run only these benchmark case IDs; repeatable")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    benchmark_bytes = BENCHMARK.read_bytes()
    manifest_bytes = MANIFEST.read_bytes()
    benchmark = json.loads(benchmark_bytes)
    manifest = json.loads(manifest_bytes)
    cases = load_cases(benchmark)
    known_ids = {case["id"] for case in cases}
    unknown = set(args.case_id or []) - known_ids
    if unknown:
        parser.error(f"unknown case IDs: {sorted(unknown)}")
    if args.case_id:
        selected = set(args.case_id)
        cases = [case for case in cases if case["id"] in selected]

    load_dotenv(ROOT / ".env", override=True)
    username, password = os.getenv("DEMO_ADMIN_USERNAME"), os.getenv("DEMO_ADMIN_PASSWORD")
    if not username or not password:
        parser.error("DEMO_ADMIN_USERNAME and DEMO_ADMIN_PASSWORD are required in .env")

    source_tables = {
        domain: set(profile["source_tables"])
        for domain, profile in benchmark["domains"].items()
    }
    results = []
    stop_reason = None
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": username, "password": password})
        if login.status_code != 200:
            parser.error(f"Demo admin login failed with HTTP {login.status_code}")
        for case in cases:
            started = time.perf_counter()
            response = client.post("/api/ask", json={
                "question": case["question"],
                "business_decision_domain": case["domain"],
            })
            elapsed = time.perf_counter() - started
            if response.status_code == 200:
                result = score_case(case, response.json(), source_tables[case["domain"]])
            else:
                result = {
                    "case_id": case["id"], "domain": case["domain"],
                    "question": case["question"], "passed": False,
                    "checks": {}, "error": response.json().get("detail", "Request failed"),
                }
            result.update({"http_status": response.status_code, "latency_seconds": round(elapsed, 3)})
            results.append(result)
            print(f"{case['id']}: {'PASS' if result['passed'] else 'FAIL'} ({elapsed:.1f}s)",
                  file=sys.stderr, flush=True)
            if response.status_code == 429:
                stop_reason = "provider_rate_limit"
                break
            if response.status_code >= 500:
                stop_reason = "server_error"
                break
        client.post("/api/auth/logout")

    attempted = {result["case_id"] for result in results}
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "benchmark_id": benchmark["benchmark_id"],
        "dataset": benchmark["dataset"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "route": "POST /api/ask",
        "principal_role": "admin",
        "benchmark_sha256": hashlib.sha256(benchmark_bytes).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_corpus_id": manifest["corpus_id"],
        "case_count": len(cases),
        "attempted_count": len(results),
        "unrun_case_ids": [case["id"] for case in cases if case["id"] not in attempted],
        "stop_reason": stop_reason,
        "mechanically_passed": sum(result["passed"] for result in results),
        "failed": sum(not result["passed"] for result in results),
        "citation_domain_checks_passed": sum(result.get("citation_domain_checks_passed", False) for result in results),
        "question_specific_sql_passed": sum(result.get("question_specific_sql_passed", False) for result in results),
        "question_sql_fallback_reasons": dict(Counter(
            result.get("question_sql_fallback") or "none" for result in results
        )),
        "gold_numeric_coverage_passed": sum(result.get("gold_numeric_coverage_passed", False) for result in results),
        "gold_numeric_coverage_applicable": sum(result.get("gold_numeric_coverage_applicable", False) for result in results),
        "gold_observation_coverage_passed": sum(result.get("gold_observation_coverage_passed") is True for result in results),
        "gold_observation_coverage_applicable": sum(result.get("gold_observation_coverage_applicable", False) for result in results),
        "semantic_review_required": True,
        "limitations": [
            "Structured gold-observation checks verify that expected dimension/value groups occur together in cited SQL rows. This does not verify that the final answer associates each row correctly, causal interpretation, qualitative claims, or recommendation quality.",
            "Review each answer against gold_observations and expected_behavior before reporting semantic benchmark scores.",
            "Commerce observations and synthetic policy rules are demo-only, not facts or policies of a real retailer.",
        ],
        "results": results,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "attempted": len(results),
                      "passed": report["mechanically_passed"], "failed": report["failed"],
                      "citation_domain_checks_passed": report["citation_domain_checks_passed"],
                      "question_specific_sql_passed": report["question_specific_sql_passed"],
                      "gold_numeric_coverage_passed": report["gold_numeric_coverage_passed"],
                      "stop_reason": stop_reason}, ensure_ascii=False))
    return 0 if results and report["failed"] == 0 and not stop_reason else 1


if __name__ == "__main__":
    raise SystemExit(main())
