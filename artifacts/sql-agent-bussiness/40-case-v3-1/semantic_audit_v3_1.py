"""Provenance and conservative ranking checks for v3.1 semantic audits.

The AST check covers only explicit ordering/TOP-N obligations. A PASS here is
not a full semantic audit; full-case decisions must come from an independent
reviewer and be linked with :func:`create_audit_record`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from typing import Any

import sqlglot
from sqlglot import exp


AUDIT_FORMAT_VERSION = "sql-semantic-audit.v3.1"
AUDIT_DECISIONS = {"PASS", "FAIL", "REVIEW_REQUIRED", "INDETERMINATE"}


def _json_default(value: Any):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported audit value: {type(value).__name__}")


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_audit_record(
    *, case: dict, case_set_sha256: str, observation: dict,
    auditor_id: str, auditor_version: str, decision: str, evidence: list[str],
) -> dict:
    """Build a reproducibly linked review record; this does not decide it."""
    sql = observation.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("An audit record requires the observed SQL text.")
    if decision not in AUDIT_DECISIONS:
        raise ValueError(f"Unsupported semantic audit decision: {decision}")
    if not isinstance(evidence, list) or not evidence or any(
        not isinstance(item, str) or not item.strip() for item in evidence
    ):
        raise ValueError("Audit evidence must contain non-empty strings.")
    parameters = observation.get("parameters", [])
    if not isinstance(parameters, (list, tuple)):
        raise ValueError("Observed SQL parameters must be a list or tuple.")
    return {
        "format_version": AUDIT_FORMAT_VERSION,
        "case_id": case["id"],
        "sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        "parameters": list(parameters),
        "parameters_sha256": canonical_sha256(list(parameters)),
        "case_contract_sha256": canonical_sha256(case),
        "case_set_sha256": case_set_sha256,
        "auditor_id": auditor_id,
        "auditor_version": auditor_version,
        "decision": decision,
        "evidence": evidence,
    }


def validate_audit_record(
    record: dict | None, *, case: dict, case_set_sha256: str, observation: dict,
) -> tuple[str, list[str]]:
    """Return a usable decision only when all frozen inputs match exactly."""
    reasons = []
    if not isinstance(record, dict):
        return "INDETERMINATE", ["audit_record_missing_or_not_an_object"]
    sql = observation.get("sql")
    parameters = observation.get("parameters", [])
    if not isinstance(sql, str) or not sql.strip():
        reasons.append("observed_sql_missing")
    elif record.get("sql_sha256") != hashlib.sha256(sql.encode("utf-8")).hexdigest():
        reasons.append("sql_hash_mismatch")
    if not isinstance(parameters, (list, tuple)):
        reasons.append("observed_parameters_invalid")
    else:
        normalized_parameters = list(parameters)
        if record.get("parameters") != normalized_parameters:
            reasons.append("parameters_mismatch")
        if record.get("parameters_sha256") != canonical_sha256(normalized_parameters):
            reasons.append("parameters_hash_mismatch")
    if record.get("format_version") != AUDIT_FORMAT_VERSION:
        reasons.append("audit_format_version_mismatch")
    if record.get("case_id") != case.get("id"):
        reasons.append("case_id_mismatch")
    if record.get("case_contract_sha256") != canonical_sha256(case):
        reasons.append("case_contract_hash_mismatch")
    if record.get("case_set_sha256") != case_set_sha256:
        reasons.append("case_set_hash_mismatch")
    if not isinstance(record.get("auditor_id"), str) or not record["auditor_id"].strip():
        reasons.append("auditor_id_missing")
    if not isinstance(record.get("auditor_version"), str) or not record["auditor_version"].strip():
        reasons.append("auditor_version_missing")
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(
        not isinstance(item, str) or not item.strip() for item in evidence
    ):
        reasons.append("audit_evidence_invalid")
    decision = record.get("decision")
    if decision not in AUDIT_DECISIONS:
        reasons.append("audit_decision_invalid")
    if reasons:
        return "INDETERMINATE", reasons
    return decision, []


def audit_ranking_contract(case: dict, sql: str) -> dict:
    """Check explicit ORDER BY/TOP-N only; leave other semantics to review."""
    top_n = case.get("top_n")
    requires_order = bool(case.get("output_contract", {}).get("ordered")) or (
        isinstance(top_n, int) and not isinstance(top_n, bool) and top_n > 0
    )
    ranking = case.get("ranking") or []
    if not requires_order:
        return {"decision": "NOT_REQUIRED", "evidence": ["row_order_is_not_semantic"]}
    if not ranking:
        return {"decision": "REVIEW_REQUIRED", "evidence": ["ranking_contract_has_no_keys"]}
    try:
        parsed = sqlglot.parse(sql, read="postgres")
    except Exception as error:
        return {"decision": "INDETERMINATE", "evidence": [f"sql_parse_error:{type(error).__name__}"]}
    if len(parsed) != 1 or not isinstance(parsed[0], exp.Query):
        return {"decision": "INDETERMINATE", "evidence": ["expected_exactly_one_query"]}
    query = parsed[0]
    order = query.args.get("order")
    actual_order = order.expressions if order is not None else []
    if len(actual_order) < len(ranking):
        return {"decision": "FAIL", "evidence": ["required_ordering_or_tie_break_missing"]}
    aliases = case.get("column_aliases", {})
    for index, required in enumerate(ranking):
        ordered = actual_order[index]
        expression = ordered.this
        if not isinstance(expression, exp.Column):
            return {"decision": "REVIEW_REQUIRED", "evidence": [f"ranking_expression_{index}_needs_semantic_review"]}
        expected = str(required.get("field", "")).casefold()
        accepted = {expected, *(str(alias).casefold() for alias in aliases.get(required.get("field"), []))}
        if expression.name.casefold() not in accepted:
            return {"decision": "FAIL", "evidence": [f"ranking_key_{index}_mismatch"]}
        actual_direction = "desc" if ordered.args.get("desc") else "asc"
        if actual_direction != str(required.get("direction", "")).casefold():
            return {"decision": "FAIL", "evidence": [f"ranking_direction_{index}_mismatch"]}
    if isinstance(top_n, int) and not isinstance(top_n, bool) and top_n > 0:
        limit = query.args.get("limit")
        fetch = query.args.get("fetch")
        count = None
        if limit is not None:
            value = limit.expression
            if isinstance(value, exp.Literal) and not value.is_string:
                try:
                    count = int(value.this)
                except (TypeError, ValueError):
                    pass
        elif fetch is not None:
            value = fetch.args.get("count")
            if isinstance(value, exp.Literal) and not value.is_string:
                try:
                    count = int(value.this)
                except (TypeError, ValueError):
                    pass
        if count != top_n:
            return {"decision": "FAIL", "evidence": ["top_n_limit_missing_or_mismatched"]}
    return {"decision": "PASS", "evidence": ["explicit_ordering_and_top_n_structure_verified"]}
