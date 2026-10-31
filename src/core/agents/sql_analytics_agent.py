"""Permission-checked, model-assisted read-only commerce queries."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Mapping
from typing import Any

from core.agents.base import BaseAgent
from core.analytics.metric_ontology import resolve_metric_names, get_metric_definition
from core.analytics.metric_mapping import build_metric_mapping_prompt, decode_metric_mapping, validate_mapped_sql
from core.analytics.metric_validation import MetricDefinitionError, validate_metric_definitions, validate_metric_request
from core.analytics.text_to_sql import (
    APPROVED_COLUMNS,
    SQLValidationError,
    build_sql_prompt,
    decode_query_plan,
    parse_json_response,
    validate_commerce_sql,
)
from core.database.commerce_repository import CommerceRepository
from core.llm.llm_interface import LLMInterface
from core.models.agents import AgentResult, Evidence, VerifiedIdentity
from core.latency import measure
from core.agents.runtime import generate


class AnalyticsPermissionDenied(PermissionError):
    """The request has no server-verified permission to query commerce data."""


def payload_to_agent_result(payload: Mapping[str, Any], *, agent: str = "analytics") -> AgentResult:
    if not isinstance(payload, Mapping):
        raise TypeError("analytics payload must be a mapping")
    evidence = []
    for index, item in enumerate(payload.get("evidence") or [], start=1):
        if not isinstance(item, Mapping) or not isinstance(item.get("source"), str) or not item["source"].strip():
            raise ValueError("analytics evidence requires a non-empty source")
        metadata = dict(item.get("metadata") or {})
        if item.get("period") is not None:
            metadata.setdefault("period", item["period"])
        evidence.append(Evidence(
            citation_id=str(item.get("citation_id") or f"S{index}"),
            source_type=str(item.get("source_type") or "database"),
            source=item["source"],
            content=item.get("content"),
            metadata=metadata,
        ))
    metadata = dict(payload.get("metadata") or {})
    metadata.setdefault("ok", bool(payload.get("ok", False)))
    if payload.get("limitations"):
        metadata["limitations"] = list(payload["limitations"])
    data = {key: value for key, value in payload.items()
            if key not in {"answer", "evidence", "metadata"}}
    answer = payload.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        answer = "Query completed." if payload.get("ok") else "The analytics request could not be completed."
    return AgentResult(answer=answer, agent=agent, evidence=evidence, data=data, metadata=metadata)


class SQLAnalyticsAgent(BaseAgent):
    def __init__(self, repository: CommerceRepository, *, llm: LLMInterface | None = None) -> None:
        self.repository = repository
        self.llm = llm

    async def run(self, request: Any) -> AgentResult:
        return payload_to_agent_result(await self.run_payload(request), agent="sql_analytics")

    async def run_payload(self, request: Any) -> dict[str, Any]:
        self._authorize(request)
        question = self._query_text(request)
        metric_names = resolve_metric_names(question)
        definitions = {}
        raw = None
        interpretation = None
        try:
            try:
                validate_metric_request(question, metric_names)
            except MetricDefinitionError as error:
                if error.code != 'snapshot_required':
                    raise
            if not metric_names or any(get_metric_definition(name).get('domain') == 'inventory_management' for name in metric_names):
                with measure('metric_interpretation'):
                    mapped = await generate(self._provider(),build_metric_mapping_prompt(question),timeout=30)
                interpretation = decode_metric_mapping(mapped,question)
                if interpretation.domain == 'inventory':
                    metric_names = set(interpretation.metrics)
            prompt = build_sql_prompt(question,metric_names=metric_names,
                                      interpretation=interpretation.model_dump() if interpretation and interpretation.domain == 'inventory' else None)
        except MetricDefinitionError as error:
            return self._generation_error(error)
        except Exception as error:
            return self._generation_error(error)
        for attempt in range(2):
            try:
                with measure("sql_planning"):
                    raw = await generate(self._provider(), prompt, timeout=60)
                plan = decode_query_plan(raw)
                if plan.sql:
                    definitions = validate_metric_definitions(plan.sql, metric_names, plan.parameters, APPROVED_COLUMNS,
                                                              question=interpretation.date_question() if interpretation and interpretation.domain == 'inventory' else question)
                    if interpretation:
                        validate_mapped_sql(plan,interpretation,question=question)
                break
            except (SQLValidationError, MetricDefinitionError) as error:
                if attempt == 0:
                    prompt = build_sql_prompt(
                        question, validation_error=str(error), previous_response=str(raw),
                        metric_names=metric_names,
                        interpretation=interpretation.model_dump() if interpretation and interpretation.domain == 'inventory' else None,
                    )
                    continue
                return self._generation_error(
                    error, self._attempted_sql(raw), self._attempted_parameters(raw),
                )
            except Exception as error:
                return self._generation_error(
                    error, self._attempted_sql(raw), self._attempted_parameters(raw),
                )
        if plan.clarification:
            return {
                "ok": False, "operation": "text_to_sql", "rows": [], "answer": plan.clarification,
                "limitations": ["The question needs clarification before a safe query can be generated."],
                "metadata": {"clarification_required": True},
            }

        try:
            validated = validate_commerce_sql(plan.sql or "")
        except Exception as error:
            return self._generation_error(error, plan.sql, plan.parameters)
        try:
            with measure("sql_execution"):
                rows = await self.repository.execute_approved_query(plan.sql or "", *plan.parameters)
        except Exception as error:
            return self._database_error(error, plan.sql, plan.parameters)
        limitations = list(dict.fromkeys(
            note for definition in definitions.values() for note in definition.get("limitations", ())
        ))
        if any(definition["unit"].startswith("currency") for definition in definitions.values()):
            limitations.append("Dataset currency is not confirmed; do not assume USD, VND or another currency.")
        if any(definition["aggregation"] == "ratio" and definition["unit"] == "percent"
               for definition in definitions.values()):
            limitations.append("Ratio results are fractions: 0.25 means 25%; raw result rows are not rescaled.")
        metadata = {"source": list(validated.sources), "explanation": plan.explanation, "metrics": definitions}
        if interpretation and interpretation.domain == 'inventory':
            metadata['semantic_interpretation'] = interpretation.model_dump()
        if any(definition.get('domain') == 'inventory_management' for definition in definitions.values()):
            dates = sorted({str(row['snapshot_date']) for row in rows if row.get('snapshot_date') is not None})
            metadata.update(metric_catalog_version='1.0.0', historical_inventory=True, snapshot_dates=dates)
            limitations.append('Inventory observations are historical; selected snapshot dates: ' + ', '.join(dates))
        if not rows:
            return {
                "ok": False, "operation": "text_to_sql", "rows": [],
                "answer": "No matching rows were found in the approved data sources.",
                "sql": plan.sql, "parameters": list(plan.parameters), "query_status": "executed",
                "limitations": limitations, "metadata": metadata,
            }
        return {
            "ok": True, "operation": "text_to_sql", "rows": rows,
            "answer": "Query completed.",
            "sql": plan.sql, "parameters": list(plan.parameters), "query_status": "executed",
            "evidence": [{"source": source, "metadata": {"metrics": definitions}} for source in validated.sources],
            "limitations": limitations,
            "metadata": metadata,
        }

    async def close(self) -> None:
        await self.repository.close()
        if self.llm is not None and hasattr(self.llm, "close"):
            self.llm.close()

    def _provider(self) -> LLMInterface:
        if self.llm is None:
            from core.llm.groq_provider import GroqProvider
            self.llm = GroqProvider()
        return self.llm

    @staticmethod
    def _authorize(request: Any) -> None:
        identity = request.get("identity") if isinstance(request, dict) else getattr(request, "identity", None)
        if not isinstance(identity, VerifiedIdentity) or "analytics:read" not in identity.permissions:
            raise AnalyticsPermissionDenied("Verified analytics:read permission is required")

    @staticmethod
    def _query_text(request: Any) -> str:
        if isinstance(request, str) and request.strip():
            return request.strip()
        for field in ("question", "query", "message", "prompt", "text"):
            value = request.get(field) if isinstance(request, dict) else getattr(request, field, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise ValueError("AgentRequest must contain query text")

    @staticmethod
    def _generation_error(error: Exception, sql: str | None = None,
                          parameters: tuple[Any, ...] = ()) -> dict[str, Any]:
        result = {
            "ok": False, "operation": "text_to_sql", "rows": [],
            "answer": f"I couldn't safely run the generated query: {error}",
            "limitations": ["The generated query did not pass planning or SQL validation."],
            "metadata": {"error_type": type(error).__name__},
        }
        if isinstance(error, MetricDefinitionError):
            result['metadata']['metric_error_code'] = error.code
            if error.clarification:
                result['answer'] = str(error)
                result['metadata'].update(clarification_required=True, status='clarification_required')
        if sql:
            result.update(attempted_sql=sql, parameters=list(parameters), query_status="rejected")
        return result

    @staticmethod
    def _database_error(error: Exception, sql: str, parameters: tuple[Any, ...]) -> dict[str, Any]:
        result = {
            "ok": False, "operation": "text_to_sql", "rows": [],
            "answer": "The approved data query could not be completed. Please try again later.",
            "limitations": ["Database query did not complete."],
            "metadata": {"error_type": type(error).__name__},
        }
        result.update(attempted_sql=sql, parameters=list(parameters), query_status="error")
        return result

    @staticmethod
    def _attempted_sql(raw: Any) -> str | None:
        try:
            plan = parse_json_response(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        sql = plan.get("sql") if isinstance(plan, dict) else None
        return sql if isinstance(sql, str) and sql.strip() else None

    @staticmethod
    def _attempted_parameters(raw: Any) -> tuple[Any, ...]:
        try:
            plan = parse_json_response(raw)
        except (TypeError, json.JSONDecodeError):
            return ()
        parameters = plan.get("parameters") if isinstance(plan, dict) else None
        if not isinstance(parameters, list):
            return ()
        return tuple(value for value in parameters if isinstance(value, (str, int, float, bool, type(None))))
