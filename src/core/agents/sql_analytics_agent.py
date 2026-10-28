"""Permission-checked, model-assisted read-only commerce queries."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Mapping
from typing import Any

from core.agents.base import BaseAgent
from core.analytics.text_to_sql import (
    SQLValidationError,
    build_sql_prompt,
    decode_query_plan,
    validate_commerce_sql,
)
from core.database.commerce_repository import CommerceRepository
from core.llm.llm_interface import LLMInterface
from core.models.agents import AgentResult, Evidence, VerifiedIdentity
from core.latency import measure


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
            if key not in {"answer", "evidence", "metadata", "sql", "attempted_sql", "parameters"}}
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
        raw = None
        prompt = build_sql_prompt(question)
        for attempt in range(2):
            try:
                with measure("sql_planning"):
                    raw = await asyncio.to_thread(self._provider().generate, prompt)
                    if inspect.isawaitable(raw):
                        raw = await raw
                plan = decode_query_plan(raw)
                break
            except SQLValidationError as error:
                if attempt == 0:
                    prompt = build_sql_prompt(
                        question, validation_error=str(error), previous_response=str(raw),
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
        if not rows:
            return {
                "ok": False, "operation": "text_to_sql", "rows": [],
                "answer": "No matching rows were found in the approved data sources.",
                "sql": plan.sql, "parameters": list(plan.parameters), "query_status": "executed",
                "limitations": [], "metadata": {"source": list(validated.sources), "explanation": plan.explanation},
            }
        return {
            "ok": True, "operation": "text_to_sql", "rows": rows,
            "answer": "Query completed.",
            "sql": plan.sql, "parameters": list(plan.parameters), "query_status": "executed",
            "evidence": [{"source": source} for source in validated.sources],
            "limitations": [],
            "metadata": {"source": list(validated.sources), "explanation": plan.explanation},
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
            plan = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        sql = plan.get("sql") if isinstance(plan, dict) else None
        return sql if isinstance(sql, str) and sql.strip() else None

    @staticmethod
    def _attempted_parameters(raw: Any) -> tuple[Any, ...]:
        try:
            plan = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return ()
        parameters = plan.get("parameters") if isinstance(plan, dict) else None
        if not isinstance(parameters, list):
            return ()
        return tuple(value for value in parameters if isinstance(value, (str, int, float, bool, type(None))))
