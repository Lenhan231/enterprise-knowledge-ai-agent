"""Provenance and conservative ranking checks for v3.1 semantic audits.

The AST check covers only explicit ordering/TOP-N obligations. A PASS here is
not a full semantic audit; full-case decisions must come from an independent
reviewer and be linked with :func:`create_audit_record`.
"""

from __future__ import annotations

import argparse
import copy
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


AUDIT_FORMAT_VERSION = "sql-semantic-audit.v3.1"
AUDIT_DECISIONS = {"PASS", "FAIL", "REVIEW_REQUIRED", "INDETERMINATE"}
AUDIT_DECISIONS_FORMAT_VERSION = "sql-semantic-audit-decisions.v1"


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


def projection_signatures(sql: str) -> list[tuple[str, str | None]] | None:
    """Return narrow SQL-expression lineage signatures for SELECT projections.

    This supports column-label equivalence only when the projected expressions
    have the same parsed structure and resolve to the same fully qualified
    source columns. It is not a query-semantic proof.
    """
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception:
        return None
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return None
    select = statements[0]
    if select.args.get("with_") or any(select.find_all(exp.Subquery)):
        return None
    projections = list(select.expressions)

    tables = list(select.find_all(exp.Table))
    alias_to_relation: dict[str, str] = {}
    relation_by_bare_name: dict[str, set[str]] = {}
    relations: set[str] = set()
    for table in tables:
        name = table.name.casefold()
        schema = (table.db or "").casefold()
        catalog = (table.catalog or "").casefold()
        relation = ".".join(part for part in (catalog, schema, name) if part)
        relations.add(relation)
        relation_by_bare_name.setdefault(name, set()).add(relation)
        for label in (table.alias_or_name, table.name):
            key = str(label).casefold()
            previous = alias_to_relation.get(key)
            if previous is not None and previous != relation:
                alias_to_relation.pop(key, None)
                alias_to_relation[f"!ambiguous:{key}"] = ""
            elif f"!ambiguous:{key}" not in alias_to_relation:
                alias_to_relation[key] = relation
        if schema:
            alias_to_relation[f"{schema}.{name}"] = relation
        if catalog and schema:
            alias_to_relation[f"{catalog}.{schema}.{name}"] = relation

    if any(len(items) > 1 for items in relation_by_bare_name.values()):
        ambiguous_bare_names = {name for name, items in relation_by_bare_name.items() if len(items) > 1}
        for name in ambiguous_bare_names:
            alias_to_relation.pop(name, None)
            alias_to_relation[f"!ambiguous:{name}"] = ""

    signatures = []
    for projection in projections:
        expression = projection.this if isinstance(projection, exp.Alias) else projection
        normalized = expression.copy()
        columns = list(normalized.find_all(exp.Column))
        if not columns:
            signatures.append((str(projection.alias_or_name).casefold(), None))
            continue
        failed = False
        for column in columns:
            table_name = column.table.casefold() if column.table else ""
            schema_name = column.db.casefold() if column.db else ""
            catalog_name = column.catalog.casefold() if column.catalog else ""
            if table_name:
                qualifier = ".".join(part for part in (catalog_name, schema_name, table_name) if part)
                relation = alias_to_relation.get(qualifier) or alias_to_relation.get(table_name)
                if not relation:
                    failed = True
                    break
            elif len(relations) == 1:
                relation = next(iter(relations))
            else:
                    failed = True
                    break
            replacement = exp.Anonymous(
                this="__lineage_column__",
                expressions=[
                    exp.Literal.string(relation),
                    exp.Literal.string(column.name.casefold()),
                ],
            )
            if column is normalized:
                normalized = replacement
            else:
                column.replace(replacement)
        signature = None if failed else normalized.sql(
            dialect="postgres", normalize=True,
        )
        signatures.append((str(projection.alias_or_name).casefold(), signature))
    return signatures


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


def export_audit_records(
    cases_doc: dict, experiment_doc: dict, decisions_doc: dict, *,
    recorded_at_utc: str | None = None,
) -> dict:
    """Link reviewer-supplied decisions to the exact run inputs without inventing review."""
    expected_case_set_sha256 = canonical_sha256(cases_doc)
    if not isinstance(decisions_doc, dict):
        raise ValueError("Reviewer decisions must be a JSON object.")
    if decisions_doc.get("format_version") != AUDIT_DECISIONS_FORMAT_VERSION:
        raise ValueError("Unsupported reviewer-decision format version.")
    if decisions_doc.get("case_set_sha256") != expected_case_set_sha256:
        raise ValueError("Reviewer decisions do not match the current case-set hash.")
    auditor_id = decisions_doc.get("auditor_id")
    auditor_version = decisions_doc.get("auditor_version")
    if not isinstance(auditor_id, str) or not auditor_id.strip():
        raise ValueError("A non-empty auditor_id is required.")
    if not isinstance(auditor_version, str) or not auditor_version.strip():
        raise ValueError("A non-empty auditor_version is required.")

    if not isinstance(cases_doc, dict) or not isinstance(experiment_doc, dict):
        raise ValueError("Cases and experiment inputs must be JSON objects.")
    case_items = cases_doc.get("cases")
    observation_items = experiment_doc.get("cases")
    if not isinstance(case_items, list) or not isinstance(observation_items, list):
        raise ValueError("Cases and experiment observations must be lists.")
    if any(not isinstance(item, dict) for item in [*case_items, *observation_items]):
        raise ValueError("Case and observation entries must be objects.")
    if any(not isinstance(item.get("id"), str) or not item["id"].strip()
           for item in [*case_items, *observation_items]):
        raise ValueError("Case and observation IDs must be non-empty strings.")
    cases = {item["id"]: item for item in case_items}
    observations = {item["id"]: item for item in observation_items}
    if len(cases) != len(case_items) or len(observations) != len(observation_items):
        raise ValueError("Case and observation IDs must be present and unique.")
    existing = experiment_doc.get("independent_semantic_audits", [])
    if existing:
        raise ValueError("Refusing to replace existing independent semantic audits.")

    decisions = decisions_doc.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("Reviewer decisions must be a list.")
    records = []
    reviewed = set()
    for item in decisions:
        if not isinstance(item, dict):
            raise ValueError("Each reviewer decision must be an object.")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or case_id in reviewed:
            raise ValueError("Reviewer decisions require unique case IDs.")
        reviewed.add(case_id)
        case = cases.get(case_id)
        observation = observations.get(case_id)
        if case is None or case.get("expected_behavior") != "execute":
            raise ValueError(f"{case_id}: semantic SQL audits apply only to known execute cases.")
        if observation is None:
            raise ValueError(f"{case_id}: no observed SQL exists in this experiment.")
        records.append(create_audit_record(
            case=case,
            case_set_sha256=expected_case_set_sha256,
            observation=observation,
            auditor_id=auditor_id,
            auditor_version=auditor_version,
            decision=item.get("decision"),
            evidence=item.get("evidence"),
        ))

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    recorded_at_utc = recorded_at_utc or now
    if not isinstance(recorded_at_utc, str) or not recorded_at_utc.strip():
        raise ValueError("recorded_at_utc must be a non-empty timestamp string.")
    try:
        timestamp = datetime.fromisoformat(recorded_at_utc.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("recorded_at_utc must be an ISO 8601 timestamp.") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise ValueError("recorded_at_utc must use a UTC timezone.")
    result = copy.deepcopy(experiment_doc)
    result["independent_semantic_audits"] = records
    result["semantic_audit_export"] = {
        "format_version": "sql-semantic-audit-export.v1",
        "source": "reviewer_decisions_json",
        "authenticated": False,
        "recorded_at_utc": recorded_at_utc,
        "auditor_id": auditor_id,
        "auditor_version": auditor_version,
        "case_set_sha256": expected_case_set_sha256,
        "reviewed_case_ids": sorted(reviewed),
        "unreviewed_observed_sql_case_ids": sorted(
            case_id for case_id, observation in observations.items()
            if cases.get(case_id, {}).get("expected_behavior") == "execute"
            and isinstance(observation.get("sql"), str)
            and observation["sql"].strip()
            and case_id not in reviewed
        ),
    }
    return result


def _export_cli() -> int:
    parser = argparse.ArgumentParser(description="Export linked independent SQL semantic audit records.")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        cases_doc = json.loads(args.cases.read_text(encoding="utf-8"))
        experiment_doc = json.loads(args.experiment.read_text(encoding="utf-8"))
        decisions_doc = json.loads(args.decisions.read_text(encoding="utf-8"))
        exported = export_audit_records(cases_doc, experiment_doc, decisions_doc)
        # Exclusive create protects prior run and review evidence from accidental replacement.
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(exported, handle, ensure_ascii=False, indent=2, default=_json_default)
            handle.write("\n")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


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


if __name__ == "__main__":
    raise SystemExit(_export_cli())
