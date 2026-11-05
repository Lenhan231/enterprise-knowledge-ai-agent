"""Permission-checked, model-assisted read-only commerce queries."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from core.agents.base import BaseAgent
from core.analytics.field_retrieval import field_contract, compile_field_query
from core.analytics.commerce_decision_support import resolve_commerce_decision_domain, unavailable_commerce_dimensions
from core.analytics.metric_ontology import resolve_metric_names, get_metric_definition
from core.analytics.metric_mapping import build_metric_mapping_prompt, compile_inventory_query, decode_metric_mapping, decode_sql_turn, MetricTime, validate_mapped_sql
from core.analytics.metric_validation import MetricDefinitionError, inventory_time_scope, validate_metric_definitions, validate_metric_request
from core.analytics.text_to_sql import (
    APPROVED_COLUMNS, INVENTORY_SOURCES, inventory_scope_enabled,
    approved_join_path,
    QueryPlan,
    relevant_schema_tables,
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
    def __init__(self, repository: CommerceRepository, *, llm: LLMInterface | None = None, inventory_only: bool | None = None) -> None:
        if inventory_only is None:
            inventory_only = inventory_scope_enabled()
        self.inventory_only = inventory_only
        self.table_columns = {name:columns for name,columns in APPROVED_COLUMNS.items()
                              if not inventory_only or name in INVENTORY_SOURCES}
        self.repository = repository
        self.llm = llm

    async def run(self, request: Any) -> AgentResult:
        return payload_to_agent_result(await self.run_payload(request), agent="sql_analytics")

    async def run_payload(self, request: Any) -> dict[str, Any]:
        self._authorize(request)
        context_info = {}
        result = await self._run_payload(request,context_info)
        metadata = result.setdefault('metadata',{})
        metadata['sql_scope'] = 'inventory' if self.inventory_only else 'approved_commerce'
        metadata.update(context_info)
        metadata['execution_status'] = (('executed' if result.get('rows') else 'executed_empty')
            if result.get('query_status') == 'executed' else
            ('clarification_required' if metadata.get('clarification_required') else
             'source_failed' if result.get('query_status') == 'error' else
             'validation_failed' if metadata.get('error_type') in {'SQLValidationError','MetricDefinitionError'} else 'planning_failed'))
        return result

    async def _run_payload(self, request: Any, context_info: dict) -> dict[str, Any]:
        question = self._query_text(request)
        options = request.get('metadata',{}) if isinstance(request,Mapping) else getattr(request,'metadata',{})
        context = options.get('_sql_context')
        if context is not None:
            context_info.update(context_used=False,_sql_context_action='new')
        unavailable = unavailable_commerce_dimensions(question, resolve_commerce_decision_domain(question) or '',
                                                      set().union(*self.table_columns.values()))
        if unavailable:
            return self._generation_error(MetricDefinitionError(
                'The full approved schema does not support these requested dimensions: '+', '.join(unavailable)+'. '
                'A supported alternative is inventory observations by product/category at an available historical snapshot.',
                code='unsupported_dimension', clarification=True))
        try:
            direct = field_contract(question) if context is None else None
        except MetricDefinitionError as error:
            return self._generation_error(error)
        metric_names = set() if direct is not None else resolve_metric_names(question)
        named_sources = set(re.findall(r'\bcommerce\.\w+', re.sub(r"'(?:[^']|'')*'", '', question).casefold()))
        if self.inventory_only and direct is None and (named_sources - INVENTORY_SOURCES or any(
                get_metric_definition(name).get('domain') != 'inventory_management' for name in metric_names)):
            return self._generation_error(MetricDefinitionError(
                'This deployment supports Inventory Management using commerce.inventory and commerce.products. '
                'The requested business metric is outside that scope. Try stock_on_hand by category at a historical snapshot.',
                code='outside_inventory_scope', clarification=True))
        if direct is not None:
            context_info['field_retrieval'] = {'source': direct.args['from_'].this.sql(),
                'columns': [p.name for p in direct.selects], 'assurance': 'literal field contract'}
        definitions = {}
        raw = None
        interpretation = None
        try:
            try:
                validate_metric_request(question, {name for name in metric_names
                    if get_metric_definition(name).get('definition_status') in {'unresolved', 'draft'}
                    or get_metric_definition(name).get('approval_status') == 'unreviewed'})
            except MetricDefinitionError as error:
                if error.code != 'snapshot_required':
                    raise
            tables = relevant_schema_tables(question, {name:get_metric_definition(name) for name in metric_names})
            if (direct is None and 'commerce.inventory' in tables and all(
                    get_metric_definition(name).get('domain') == 'inventory_management' for name in metric_names)
                    and re.search(r'\bcurrent\b|\btoday\b|hiện tại|hôm nay', re.sub(r"'(?:[^']|'')*'", '', question), re.I)
                    and not re.search(r'latest available|mới nhất hiện có', question, re.I)):
                period = inventory_time_scope(question) or ('snapshot', date.today().isoformat(), None)
                if period:
                    snapshot_sql = 'SELECT MAX(i.snapshot_date) AS snapshot_date FROM commerce.inventory AS i LIMIT 1'
                    try:
                        snapshots = await self.repository.execute_approved_query(snapshot_sql)
                    except Exception as error:
                        return self._database_error(error,snapshot_sql,())
                    latest = snapshots[0].get('snapshot_date') if snapshots else None
                    if latest is None or date.fromisoformat(str(latest)) < date.fromisoformat(period[1]):
                        reason = ('No inventory observations are available in the requested current period. '
                            + ('The latest available snapshot is '+str(latest)+'. ' if latest else 'No inventory snapshots are available. ')
                            + 'Historical observations cannot establish current stock. Request an available historical snapshot instead.')
                        result = self._generation_error(MetricDefinitionError(reason,code='requested_period_unavailable'))
                        result['answer'] = reason
                        result['metadata'].update(status='unsupported',latest_available_snapshot=str(latest) if latest else None,
                            availability_source='MAX(commerce.inventory.snapshot_date)')
                        return result
            cross_domain = (not self.inventory_only and direct is None and 'commerce.inventory' in tables and bool(tables & {'commerce.orders','commerce.order_items'})
                            and bool(re.search(r'\borders\b|\bordered\b|\border(?!\s+by)\b|đơn hàng',question,re.I)))
            if (direct is None and not cross_domain and (context is not None
                    or any(get_metric_definition(name).get('domain') == 'inventory_management' for name in metric_names)
                    or (not metric_names and 'commerce.inventory' in tables))):
                with measure('metric_interpretation'):
                    mapped = await generate(self._provider(),build_metric_mapping_prompt(question,context=context),timeout=30)
                if context is None:
                    interpretation = decode_metric_mapping(mapped,question)
                else:
                    interpretation, used = decode_sql_turn(mapped,question,context)
                    context_info.update(context_used=used,_sql_context_action='followup' if used else 'new')
                if interpretation.domain == 'inventory':
                    metric_names = set(interpretation.metrics)
            resolved_latest = False
            if context is not None and interpretation and interpretation.domain == 'inventory' and interpretation.time.mode == 'latest':
                snapshot_sql = 'SELECT MAX(i.snapshot_date) AS snapshot_date FROM commerce.inventory AS i LIMIT 1'
                try:
                    snapshots = await self.repository.execute_approved_query(snapshot_sql)
                except Exception as error:
                    return self._database_error(error,snapshot_sql,())
                snapshot = snapshots[0].get('snapshot_date') if snapshots else None
                if snapshot is None:
                    raise MetricDefinitionError('No inventory snapshots are available.',code='snapshot_unavailable',clarification=True)
                context_info['requested_time'] = interpretation.time.model_dump()
                interpretation = interpretation.model_copy(update={'time':MetricTime(mode='snapshot',start=str(snapshot))})
                interpretation = decode_metric_mapping(interpretation.model_dump_json(),interpretation.date_question())
                resolved_latest = True
            prompt = build_sql_prompt(question,metric_names=metric_names,
                                      allowed_sources=self.table_columns, interpretation=interpretation.model_dump() if interpretation and interpretation.domain == 'inventory' else None)
        except MetricDefinitionError as error:
            if context is not None and hasattr(error,'context_action'):
                context_info['_sql_context_action'] = error.context_action
            return self._generation_error(error)
        except Exception as error:
            return self._generation_error(error)
        for attempt in range(2):
            try:
                if direct is not None:
                    plan = compile_field_query(direct)
                elif interpretation and interpretation.domain == 'inventory':
                    sql, parameters = compile_inventory_query(interpretation)
                    plan = QueryPlan(sql=sql, parameters=parameters,
                                     explanation='Compiled from the validated inventory interpretation.')
                else:
                    with measure("sql_planning"):
                        raw = await generate(self._provider(), prompt, timeout=60)
                    plan = decode_query_plan(raw)
                    if plan.clarification and attempt == 0 and approved_join_path(tables) and re.search(
                            r'join|relationship', plan.clarification, re.I):
                        raise SQLValidationError('An approved bridge path exists in the supplied schema. '
                            'Use that path with independent aggregates or correlated EXISTS as appropriate; '
                            'do not introduce direct fact joins or ask the user to approve an existing relationship.')
                if plan.sql:
                    validate_commerce_sql(plan.sql, allowed_sources=self.table_columns)
                    if cross_domain and not {'commerce.inventory','commerce.orders','commerce.order_items'} <= set(validate_commerce_sql(plan.sql).sources):
                        raise SQLValidationError('The requested cross-domain contract must retain inventory, orders and order_items.')
                    definitions = validate_metric_definitions(plan.sql, metric_names, plan.parameters, APPROVED_COLUMNS,
                                                              question=interpretation.date_question() if interpretation and interpretation.domain == 'inventory' else question)
                    if interpretation:
                        validate_mapped_sql(plan,interpretation,question=interpretation.date_question() if resolved_latest else question)
                break
            except (SQLValidationError, MetricDefinitionError) as error:
                if attempt == 0 and direct is None and not (interpretation and interpretation.domain == 'inventory'):
                    prompt = build_sql_prompt(
                        question, validation_error=str(error), previous_response=str(raw),
                        metric_names=metric_names, allowed_sources=self.table_columns,
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
            validated = validate_commerce_sql(plan.sql or "", allowed_sources=self.table_columns)
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
        metadata['columns'] = [{'name': name, 'unit': definitions.get(name, {}).get('unit')}
                               for name in (rows[0] if rows else ())]
        if interpretation and interpretation.domain == 'inventory':
            metadata['semantic_interpretation'] = interpretation.model_dump()
            metadata['filters'] = [item.model_dump() for item in interpretation.filters]
            metadata['time_scope'] = interpretation.time.model_dump()
        if interpretation and interpretation.time and interpretation.time.mode == 'comparison':
            metadata['columns'] = [dict(name=name, unit='units' if name in {'stock_before','stock_after','stock_delta'} else None) for name in (rows[0] if rows else ())]
            metadata['comparison'] = dict(before=interpretation.time.start, after=interpretation.time.end,
                population='products observed on both dates', calculation='stock_after - stock_before', unit='units', null_policy='preserve')
            limitations.append('Only products observed on both selected dates are included. NULL stock operands produce NULL deltas; missing observations are not zero stock.')
        if any(definition.get('domain') == 'inventory_management' for definition in definitions.values()):
            dates = sorted({str(row[name]) for row in rows for name in ('snapshot_date','before_date','after_date') if row.get(name) is not None})
            metadata.update(metric_catalog_version='1.0.0', historical_inventory=True, snapshot_dates=dates)
            if interpretation and interpretation.time.mode == 'range':
                limitations.append('Results retain separate exact snapshot observations. No combined period movement or balance total is established by the catalog.')
            periods = [definition['calculation_scope'] for definition in definitions.values() if definition.get('calculation_scope')]
            if periods:
                metadata['inventory_period_scope'] = periods[0]
                limitations.append('Recorded inventory movement observations are summed over the requested period: ' + str(periods[0]))
            elif dates:
                limitations.append('Inventory observations are historical; selected snapshot dates: ' + ', '.join(dates))
            else:
                limitations.append('No matching inventory observations were found for the requested scope; missing observations are not zero stock.')
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
