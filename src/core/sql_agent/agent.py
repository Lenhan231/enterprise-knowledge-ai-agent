"""Permission-checked, model-assisted read-only commerce queries."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
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
from core.analytics.join_validation import PRIMARY_KEYS
from core.analytics.text_to_sql import (
    APPROVED_COLUMNS, APPROVED_JOINS, INVENTORY_SOURCES, inventory_scope_enabled,
    approved_join_path,
    QueryPlan,
    relevant_schema_tables,
    SQLValidationError,
    SQLSchemaMismatchError,
    build_sql_prompt,
    decode_query_plan,
    parse_json_response,
    validate_commerce_sql,
    validate_current_year_month_range,
    validate_latest_month_query,
    resolve_current_year_month_parameters,
    validate_current_month_total_query,
)
from core.database.commerce_repository import CommerceRepository
from core.llm.llm_interface import LLMInterface
from core.models.agents import AgentResult, Evidence, VerifiedIdentity
from core.latency import measure
from core.agents.runtime import generate


class AnalyticsPermissionDenied(PermissionError):
    """The request has no server-verified permission to query commerce data."""


def _month_over_month_revenue_plan(question: str, metric_names: set[str], today: date | None = None):
    """Compile the common current-vs-previous calendar month revenue comparison."""
    text = question.casefold()
    compares_months = bool(re.search(r"\b(?:compare|comparison|versus|vs\.?|month.over.month|mom)\b|so sánh|đối chiếu", text))
    mentions_previous_month = bool(re.search(r"previous month|last month|tháng trước", text))
    explicit_period = bool(re.search(r"\b(?:19|20)\d{2}\b|\btháng\s+(?:0?[1-9]|1[0-2])\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b", text))
    if metric_names != {"revenue"} or not compares_months or not mentions_previous_month or explicit_period:
        return None

    today = today or date.today()
    current_start = date(today.year, today.month, 1)
    if today.month == 1:
        previous_start = date(today.year - 1, 12, 1)
    else:
        previous_start = date(today.year, today.month - 1, 1)
    next_start = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    sql = (
        "SELECT CAST($2 AS DATE) AS month, CAST($1 AS DATE) AS previous_month, "
        "SUM(s.revenue) FILTER (WHERE s.date >= $2 AND s.date < $3) AS revenue, "
        "SUM(s.revenue) FILTER (WHERE s.date >= $1 AND s.date < $2) AS previous_month_revenue, "
        "SUM(s.revenue) FILTER (WHERE s.date >= $2 AND s.date < $3) - "
        "SUM(s.revenue) FILTER (WHERE s.date >= $1 AND s.date < $2) AS revenue_change, "
        "(SUM(s.revenue) FILTER (WHERE s.date >= $2 AND s.date < $3) - "
        "SUM(s.revenue) FILTER (WHERE s.date >= $1 AND s.date < $2)) / "
        "NULLIF(SUM(s.revenue) FILTER (WHERE s.date >= $1 AND s.date < $2), 0) AS revenue_change_fraction "
        "FROM commerce.sales AS s LIMIT 1"
    )
    return QueryPlan(sql=sql, parameters=(previous_start, current_start, next_start),
                     explanation="Compare current and previous calendar month revenue using code-resolved date bounds.")


def _explicit_month_revenue_plan(question: str, metric_names: set[str], today: date | None = None):
    if metric_names != {"revenue"}:
        return None
    match = re.search(r"\btháng\s+(0?[1-9]|1[0-2])(?:\s+năm\s+((?:19|20)\d{2}))?\b", question, re.I)
    if not match:
        return None
    year, month = int(match.group(2) or (today or date.today()).year), int(match.group(1))
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    sql = (
        "SELECT CAST($1 AS DATE) AS month, SUM(s.revenue) AS revenue "
        "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 LIMIT 1"
    )
    return QueryPlan(sql=sql, parameters=(start, end),
                     explanation="Compile a calendar-month revenue total from commerce.sales.")


def _promotion_query_plan(question: str, today: date | None = None):
    """Compile the two unambiguous promotion questions using their source grain."""
    text = question.casefold()
    mentions_promo = bool(re.search(r"promo(?:tion)?s?|promotion code|discount code|coupon|voucher|khuyến mãi|mã giảm giá|mã khuyến mãi", text))
    if not mentions_promo:
        return None, None

    asks_active_count = bool(re.search(
        r"\bhow many\b|\bcount\b|bao nhiêu|số lượng", text
    )) and bool(re.search(r"\bactive\b|\bcurrent\b|currently|hiện tại|đang hoạt động", text))
    if asks_active_count:
        today = today or date.today()
        return QueryPlan(
            sql=("SELECT COUNT(*) AS active_promotion_count "
                 "FROM commerce.promotions AS p "
                 "WHERE p.start_date <= $1 AND p.end_date >= $1 LIMIT 1"),
            parameters=(today,),
            explanation="Count promotions whose recorded start and end dates include the server's current date.",
        ), "active_promotion_count"

    asks_top_revenue = bool(re.search(r"\b(?:top|highest|most|rank|best)\b|cao nhất|nhiều nhất|đứng đầu", text)) \
        and bool(re.search(r"revenue|sales|doanh thu", text))
    if asks_top_revenue:
        limit_match = re.search(r"\btop\s+(\d{1,2})\b|(\d{1,2})\s+(?:mã|promo|promotion|discount)", text)
        limit = min(int(next(group for group in limit_match.groups() if group)), 50) if limit_match else 10
        return QueryPlan(
            sql=("SELECT p.promo_id, p.promo_name, "
                 "SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue "
                 "FROM commerce.order_items AS oi "
                 "JOIN commerce.promotions AS p ON p.promo_id = oi.promo_id "
                 "WHERE oi.promo_id IS NOT NULL AND oi.promo_id_2 IS NULL "
                 "AND oi.quantity IS NOT NULL AND oi.unit_price IS NOT NULL "
                 "AND oi.discount_amount IS NOT NULL "
                 "GROUP BY p.promo_id, p.promo_name "
                 "ORDER BY revenue DESC, p.promo_id LIMIT " + str(limit)),
            parameters=(),
            explanation="Rank promotions by recorded net item revenue, without double-attributing lines with a second promotion.",
        ), "promotion_revenue"
    return None, None


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
    def __init__(self, repository: CommerceRepository, llm: LLMInterface | None = None, *,
                 inventory_only: bool | None = None, metric_retriever=None) -> None:
        if inventory_only is None:
            inventory_only = inventory_scope_enabled()
        self.inventory_only = inventory_only
        self.table_columns = {name:columns for name,columns in APPROVED_COLUMNS.items()
                              if not inventory_only or name in INVENTORY_SOURCES}
        self.repository = repository
        self.llm = llm
        self.metric_retriever = metric_retriever

    async def _run_async(self, request: Any) -> AgentResult:
        return payload_to_agent_result(await self.run_payload(request), agent="sql_analytics")

    def run(self, request: Any) -> AgentResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._run_async(request))
        return self._run_async(request)

    async def run_payload(self, request: Any) -> dict[str, Any]:
        self._authorize(request)
        context_info = {}
        schema = {}
        discover = getattr(self.repository, 'get_schema', None)
        if discover is not None:
            try:
                with measure('schema_discovery'):
                    discovered = await discover()
            except Exception as error:
                discovered = None
                discovery_error = error
            else:
                discovery_error = None
            if isinstance(discovered, dict) and isinstance(discovered.get('tables'), dict):
                schema = discovered
            elif discovery_error is not None:
                result = self._database_error(discovery_error, None, ())
                result.setdefault('metadata', {})['schema_discovery'] = 'failed'
                result['metadata']['sql_scope'] = 'inventory' if self.inventory_only else 'configured_schemas'
                result['metadata']['execution_status'] = 'source_failed'
                return result
        table_columns = schema.get('tables') or self.table_columns
        if self.inventory_only:
            table_columns = {name: columns for name, columns in table_columns.items()
                             if name in INVENTORY_SOURCES}
        joins = set(schema.get('joins') or ()) | set(APPROVED_JOINS)
        primary_keys = {**PRIMARY_KEYS, **schema.get('primary_keys', {})}
        date_columns = schema.get('date_columns')
        if schema:
            context_info['discovered_schema'] = {
                'tables': sorted(table_columns),
                'schemas': sorted({table.split('.', 1)[0] for table in table_columns}),
            }
        result = await self._run_payload(request, context_info, table_columns, joins, primary_keys, date_columns)
        metadata = result.setdefault('metadata',{})
        schemas = context_info.get('discovered_schema', {}).get('schemas')
        metadata['sql_scope'] = ('inventory' if self.inventory_only else
                                 ','.join(schemas) if schemas else 'approved_commerce')
        metadata.update(context_info)
        metadata['execution_status'] = (('executed' if result.get('rows') else 'executed_empty')
            if result.get('query_status') == 'executed' else
            ('clarification_required' if metadata.get('clarification_required') else
             'source_failed' if result.get('query_status') == 'error' else
             'validation_failed' if metadata.get('error_type') in {
                 'SQLValidationError', 'SQLSecurityError', 'SQLSchemaMismatchError', 'MetricDefinitionError'
             } else 'planning_failed'))
        return result

    async def _run_payload(self, request: Any, context_info: dict, table_columns, approved_joins,
                           primary_keys, date_columns) -> dict[str, Any]:
        question = self._query_text(request)
        options = request.get('metadata',{}) if isinstance(request,Mapping) else getattr(request,'metadata',{})
        original_question = options.get('_original_question')
        if not isinstance(original_question, str) or not original_question.strip():
            original_question = question
        context = options.get('_sql_context')
        if context is not None:
            known_metrics = resolve_metric_names(question)
            if known_metrics and not any(
                    get_metric_definition(name).get('domain') == 'inventory_management'
                    for name in known_metrics):
                context = None
        if context is not None:
            context_info.update(context_used=False,_sql_context_action='new')
        unavailable = unavailable_commerce_dimensions(question, resolve_commerce_decision_domain(question) or '',
                                                      set().union(*table_columns.values()))
        if unavailable:
            return self._generation_error(MetricDefinitionError(
                'The full approved schema does not support these requested dimensions: '+', '.join(unavailable)+'. '
                'A supported alternative is inventory observations by product/category at an available historical snapshot.',
                code='unsupported_dimension', clarification=True))
        try:
            direct = field_contract(question) if context is None else None
        except MetricDefinitionError as error:
            return self._generation_error(error)
        promotion_plan, promotion_metric = _promotion_query_plan(question) if direct is None else (None, None)
        explicit_order_item_formula = bool(
            re.search(r'\border[_ ]items?\b', question, re.I)
            and re.search(r'\b(?:discount_amount|refund_amount|unit_price|quantity)\b', question, re.I)
        )
        metric_names = (set() if direct is not None or promotion_plan is not None or explicit_order_item_formula
                        else resolve_metric_names(question))
        relative_month_followup = bool(re.fullmatch(
            r'\s*(?:(?:vậy|còn)\s+)?(?:tháng trước(?: thì sao)?|last month|previous month)\s*[?!.]*\s*',
            original_question, re.I))
        explicit_month_plan = (_explicit_month_revenue_plan(question, metric_names)
                               if relative_month_followup else None)
        month_comparison_plan = _month_over_month_revenue_plan(question, metric_names)
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
            if promotion_metric == "promotion_revenue":
                tables = {"commerce.order_items", "commerce.promotions"}
            elif promotion_metric == "active_promotion_count":
                tables = {"commerce.promotions"}
            else:
                tables = relevant_schema_tables(question, {name:get_metric_definition(name) for name in metric_names}, table_columns)
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
            cross_domain = ('commerce.inventory' in tables and bool(tables & {'commerce.orders', 'commerce.order_items'})
                            and bool(re.search(r'\borders\b|\bordered\b|\border(?!\s+by)\b|đơn hàng', question, re.I)))
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
            metric_evidence = {}
            metric_lookup = {}
            if (not metric_names and direct is None and promotion_plan is None
                    and not explicit_order_item_formula and self.metric_retriever is not None):
                with measure('metric_retrieval'):
                    try:
                        items = await self.metric_retriever(request, question)
                    except Exception as error:
                        items = []
                        metric_lookup['rag_fallback'] = 'unavailable:' + type(error).__name__
                    else:
                        metric_lookup['rag_fallback'] = 'found' if items else 'not_found'
                    if items:
                        metric_evidence['rag_fallback'] = items
            if metric_names:
                context_info['metric_definition_source'] = {
                    name: 'metric_ontology' for name in sorted(metric_names)
                }
            elif metric_lookup:
                context_info['metric_definition_source'] = {
                    'rag_fallback': 'rag' if metric_evidence else 'not_found_or_unavailable'
                }
                context_info['metric_lookup_status'] = metric_lookup
            prompt = build_sql_prompt(question, metric_names=metric_names,
                allowed_sources=set(table_columns), schema_columns=table_columns, approved_joins=approved_joins,
                primary_keys=primary_keys,
                interpretation=interpretation.model_dump() if interpretation and interpretation.domain == 'inventory' else None,
                metric_evidence=metric_evidence, relative_time_question=original_question)
        except MetricDefinitionError as error:
            if context is not None and hasattr(error,'context_action'):
                context_info['_sql_context_action'] = error.context_action
            return self._generation_error(error)
        except Exception as error:
            return self._generation_error(error)
        for attempt in range(2):
            try:
                if promotion_plan is not None:
                    plan = promotion_plan
                elif explicit_month_plan is not None:
                    plan = explicit_month_plan
                elif month_comparison_plan is not None:
                    plan = month_comparison_plan
                elif direct is not None:
                    plan = compile_field_query(direct)
                elif interpretation and interpretation.domain == 'inventory':
                    sql, parameters = compile_inventory_query(interpretation)
                    plan = QueryPlan(sql=sql, parameters=parameters,
                                     explanation='Compiled from the validated inventory interpretation.')
                else:
                    with measure("sql_planning"):
                        raw = await self._generate_sql(prompt)
                    plan = decode_query_plan(raw, table_columns, allowed_sources=set(table_columns),
                        approved_joins=approved_joins, primary_keys=primary_keys, date_columns=date_columns)
                    resolved_parameters = resolve_current_year_month_parameters(
                        plan.sql or '', plan.parameters, original_question, date_columns=date_columns)
                    if resolved_parameters != plan.parameters:
                        plan = QueryPlan(sql=plan.sql, parameters=resolved_parameters,
                                         explanation=plan.explanation, clarification=plan.clarification)
                    validate_current_year_month_range(plan.sql or '', plan.parameters, original_question,
                                                      date_columns=date_columns)
                    if plan.sql:
                        validate_current_month_total_query(plan.sql, original_question,
                                                           date_columns=date_columns)
                        validate_latest_month_query(plan.sql, question)
                    if plan.clarification and attempt == 0 and approved_join_path(tables, approved_joins) and re.search(
                            r'join|relationship', plan.clarification, re.I):
                        raise SQLValidationError('An approved bridge path exists in the supplied schema. '
                            'Use that path with independent aggregates or correlated EXISTS as appropriate; '
                            'do not introduce direct fact joins or ask the user to approve an existing relationship.')
                if plan.sql:
                    validate_commerce_sql(plan.sql, allowed_sources=set(table_columns), schema_columns=table_columns,
                        approved_joins=approved_joins, primary_keys=primary_keys, date_columns=date_columns)
                    if cross_domain and not {'commerce.inventory','commerce.orders','commerce.order_items'} <= set(validate_commerce_sql(
                            plan.sql, schema_columns=table_columns, approved_joins=approved_joins,
                            primary_keys=primary_keys, date_columns=date_columns).sources):
                        raise SQLValidationError('The requested cross-domain contract must retain inventory, orders and order_items.')
                    definitions = ({"revenue": get_metric_definition("revenue")}
                                   if month_comparison_plan is not None or explicit_month_plan is not None else
                                   validate_metric_definitions(plan.sql, metric_names, plan.parameters, table_columns,
                                       question=interpretation.date_question() if interpretation and interpretation.domain == 'inventory' else question))
                    if promotion_metric == "promotion_revenue":
                        definitions = {"promotion_revenue": {
                            "unit": "currency", "aggregation": "sum",
                            "limitations": (
                                "Revenue is net item revenue attributed through order_items.promo_id; lines with promo_id_2 are excluded because the allocation rule is undefined.",
                            ),
                        }}
                    elif promotion_metric == "active_promotion_count":
                        definitions = {"active_promotion_count": {
                            "unit": "promotions", "aggregation": "count",
                            "limitations": (
                                "A promotion is counted as active when the current server date falls within its recorded start_date and end_date.",
                            ),
                        }}
                    if interpretation:
                        validate_mapped_sql(plan,interpretation,question=interpretation.date_question() if resolved_latest else question)
                break
            except (SQLValidationError, MetricDefinitionError) as error:
                if attempt == 0 and direct is None and not (interpretation and interpretation.domain == 'inventory'):
                    prompt = build_sql_prompt(
                        question, validation_error=str(error), previous_response=str(raw),
                        metric_names=metric_names, allowed_sources=set(table_columns), schema_columns=table_columns,
                        approved_joins=approved_joins, primary_keys=primary_keys,
                        interpretation=interpretation.model_dump() if interpretation and interpretation.domain == 'inventory' else None,
                        metric_evidence=metric_evidence, relative_time_question=original_question,
                    )
                    continue
                return self._generation_error(
                    error, self._attempted_sql(raw), self._attempted_parameters(raw), question=question,
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
            validated = validate_commerce_sql(plan.sql or "", allowed_sources=set(table_columns),
                schema_columns=table_columns, approved_joins=approved_joins,
                primary_keys=primary_keys, date_columns=date_columns)
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
        invoice_query = any(source in {'commerce.invoices', 'commerce.invoice_items'} for source in validated.sources)
        if invoice_query:
            limitations.extend([
                'Only explicitly approved invoice extractions are included; missing fields remain unknown.',
                'Invoice access is temporarily shared across all analytics:read users until RBAC is established.',
                'Currency may be unknown; a NULL currency group does not establish a shared currency.',
            ])
        if any(definition["unit"].startswith("currency") for definition in definitions.values()):
            limitations.append("Dataset currency is not confirmed; do not assume USD, VND or another currency.")
        if any(definition["aggregation"] == "ratio" and definition["unit"] == "percent"
               for definition in definitions.values()):
            limitations.append("Ratio results are fractions: 0.25 means 25%; raw result rows are not rescaled.")
        metadata = {"source": list(validated.sources), "explanation": plan.explanation, "metrics": definitions}
        if invoice_query:
            metadata['invoice_access_control'] = 'temporary_all_analytics_readers'
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
        for provider in (self.llm, getattr(self, "_fallback_llm", None)):
            if provider is not None and hasattr(provider, "close"):
                provider.close()

    def _provider(self) -> LLMInterface:
        if self.llm is None:
            provider_name = os.getenv("SQL_LLM_PROVIDER", "auto").strip().casefold()
            if provider_name == "groq":
                from core.llm.groq_provider import GroqProvider
                self.llm = GroqProvider(model=os.getenv("SQL_GROQ_MODEL") or None)
                return self.llm
            from core.llm.Cloudflare_provider import CloudflareProvider
            if os.getenv("CLOUDFLARE_API_TOKEN") or os.getenv("CLOUDFLARE_WORKERS_API"):
                self.llm = CloudflareProvider(model=os.getenv('SQL_CLOUDFLARE_MODEL') or None)
            else:
                from core.llm.groq_provider import GroqProvider
                self.llm = GroqProvider()
        return self.llm

    async def _generate_sql(self, prompt: str) -> str:
        primary = self._provider()
        try:
            return await generate(primary, prompt, timeout=60)
        except Exception as primary_error:
            from core.llm.Cloudflare_provider import CloudflareProvider
            from core.llm.groq_provider import GroqProvider
            if isinstance(primary, CloudflareProvider):
                fallback_type = GroqProvider
                fallback_kwargs = {}
            elif (isinstance(primary, GroqProvider)
                  and os.getenv("CLOUDFLARE_ACCOUNT_ID")
                  and (os.getenv("CLOUDFLARE_API_TOKEN") or os.getenv("CLOUDFLARE_WORKERS_API"))):
                fallback_type = CloudflareProvider
                fallback_kwargs = {"model": os.getenv("SQL_CLOUDFLARE_MODEL") or None}
            else:
                raise
            try:
                fallback = getattr(self, "_fallback_llm", None)
                if fallback is None:
                    fallback = fallback_type(**fallback_kwargs)
                    self._fallback_llm = fallback
            except Exception:
                raise primary_error
            return await generate(fallback, prompt, timeout=60)

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
                          parameters: tuple[Any, ...] = (), *, question: str = "") -> dict[str, Any]:
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
        if isinstance(error, SQLSchemaMismatchError):
            if re.search(r'[ăâđêôơưáàảãạấầẩẫậắằẳẵặếềểễệốồổỗộớờởỡợứừửữựýỳỷỹỵ]', question, re.I):
                result['answer'] = (
                    f"Schema hiện tại không có cột {error.table}.{error.column}. "
                    f"Các cột khả dụng: {', '.join(error.available_columns)}. "
                    "Bạn muốn mình thử tạo lại truy vấn theo schema này không? Trả lời ‘có’ hoặc cho biết trường cần dùng."
                )
            else:
                result['answer'] = (
                    f"The query used {error.table}.{error.column}, which is missing from the live schema. "
                    f"Available columns are: {', '.join(error.available_columns)}. "
                    "Would you like me to retry using the discovered schema? Reply yes or specify the field you mean."
                )
            result['limitations'] = ["No query was executed; the generated SQL did not match the live schema."]
            result['metadata'].update(
                status='clarification_required', clarification_required=True,
                schema_confirmation_required=True,
                schema_mismatch={'table': error.table, 'column': error.column,
                                 'available_columns': list(error.available_columns)},
            )
        if sql:
            result.update(attempted_sql=sql, parameters=list(parameters), query_status="rejected")
        return result

    @staticmethod
    def _database_error(error: Exception, sql: str | None, parameters: tuple[Any, ...]) -> dict[str, Any]:
        result = {
            "ok": False, "operation": "text_to_sql", "rows": [],
            "answer": "The approved data query could not be completed. Please try again later.",
            "limitations": ["Database query did not complete."],
            "metadata": {"error_type": type(error).__name__},
        }
        result['query_status'] = "error"
        if sql:
            result.update(attempted_sql=sql, parameters=list(parameters))
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
