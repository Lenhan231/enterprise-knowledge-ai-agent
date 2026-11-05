"""Typed quantitative evidence and deterministic display/comparison rules."""
from decimal import Decimal, InvalidOperation, localcontext
from datetime import date
from typing import Any

from pydantic import Field

from core.analytics.metric_ontology import METRIC_ONTOLOGY
from core.reports.planning import StrictModel
from core.analytics.text_to_sql import decode_query_plan
import json

FACT_VERIFICATION_SCOPE = (
    'Quantitative facts are checked against metric identity, value, unit, dimensions, filters and snapshot date. '
    'Generated interpretation is not fully semantically verified. Retained template text is user-provided and unverified.'
)


class ReportFact(StrictModel):
    id: str
    evidence_id: str
    task_id: str
    metric: str
    value: str | bool | None
    unit: str
    dimensions: dict[str, Any] = Field(default_factory=dict)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    snapshot_date: str | None = None
    formula: str | None = None
    operands: list[str] = Field(default_factory=list)
    approval_status: str | None = None
    source_row: int | None = Field(default=None, ge=0)


def display_value(fact):
    if fact.value is None:
        return 'Unavailable (missing observation or undefined value)'
    if isinstance(fact.value, bool):
        return str(fact.value).lower()
    if fact.unit == 'percent':
        with localcontext() as context:
            context.prec = max(38, len(fact.value)+2)
            text = format(Decimal(fact.value) * 100, 'f')
        return (text.rstrip('0').rstrip('.') if '.' in text else text)+'%'
    return fact.value


def validate_fact_claim(claim, facts):
    supplied = ReportFact.model_validate(claim)
    expected = facts.get(supplied.id)
    if expected is None or supplied != expected:
        raise ValueError('Fact reference or metric/value/unit/dimension/filter/date mismatch')
    return expected


def facts_from_rows(task, rows, evidence_id, start=1):
    facts = []
    mapping = task.mapping
    dimensions = list(dict.fromkeys(['snapshot_date', *mapping.dimensions])) if mapping else ([] if task.product_columns == ['product_count'] else task.product_columns)
    metrics = mapping.metrics if mapping else task.product_columns
    seen = set()
    for row in rows:
        if any(name not in row for name in {*dimensions, *metrics}):
            raise ValueError('Query omitted a requested metric or dimension')
        scope = {name: str(row[name]) if row[name] is not None else None for name in dimensions if name != 'snapshot_date'}
        snapshot = str(row['snapshot_date'])[:10] if mapping else None
        if mapping:
            date.fromisoformat(snapshot)
            if mapping.time.mode == 'snapshot' and snapshot != mapping.time.start:
                raise ValueError('Observation belongs to the wrong snapshot')
            if mapping.time.mode == 'range' and not mapping.time.start <= snapshot <= mapping.time.end:
                raise ValueError('Observation falls outside the requested range')
        key = (snapshot, tuple(scope.items()))
        if key in seen:
            raise ValueError('Duplicate observation at the requested output grain')
        seen.add(key)
        for name in metrics:
            definition = METRIC_ONTOLOGY.get(name, {}) if mapping else {}
            value = row[name]
            if mapping and value is not None:
                if definition.get('unit') == 'boolean':
                    if type(value) is not bool:
                        raise ValueError('Invalid recorded flag value')
                else:
                    number = Decimal(str(value))
                    if isinstance(value, bool) or not number.is_finite() or abs(number.adjusted()) > 1000:
                        raise ValueError('Invalid quantitative observation')
            if any(len(str(item)) > 2000 for item in [value, *scope.values()]):
                raise ValueError('Source field exceeds report cell bounds')
            facts.append(ReportFact(
                id=f'F{start+len(facts)}', evidence_id=evidence_id, task_id=task.id, metric=name,
                value=value if value is None or isinstance(value, bool) else str(value),
                unit=definition.get('unit', 'products' if name == 'product_count' else 'source_field'), dimensions=scope, snapshot_date=snapshot,
                filters=[item.model_dump() for item in (mapping.filters if mapping else task.product_filters)],
                formula=definition.get('formula', 'COUNT(products.product_id)' if name == 'product_count' else None), approval_status=definition.get('approval_status')))
    return facts


def facts_from_analytics(task, result, evidence_id, start=1):
    """Keep raw SQL output fields and validated metric units tied to query scope."""
    query = decode_query_plan(json.dumps({'sql': result.data.get('sql'),
                                         'parameters': result.data.get('parameters', [])}, default=str))
    # The shared SQL agent validates metric definitions and resolved time scope before execution.
    definitions = result.metadata.get('metrics', {})
    comparison = result.metadata.get('comparison')
    if comparison:
        source = definitions.get('stock_on_hand', {})
        definitions = {**definitions, **{name: {'unit':'units', 'approval_status':source.get('approval_status'),
            'formula':'stock_after - stock_before' if name == 'stock_delta' else 'stock_on_hand'}
            for name in ('stock_before','stock_after','stock_delta')}}
    rows = result.data.get('rows', [])
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError('Shared SQL result exceeds the report row bound')
    fields = set(rows[0]) if rows else set()
    if len(fields) > 20:
        raise ValueError('Narrow the shared SQL task to at most 20 output fields')
    facts = []
    scope = json.loads(json.dumps({'sql': query.sql, 'parameters': query.parameters}, default=str))
    for row_index, row in enumerate(rows):
        row_facts = []
        if not isinstance(row, dict):
            raise ValueError('SQL rows must be field dictionaries')
        if set(row) != fields:
            raise ValueError('SQL rows have inconsistent output fields')
        dimensions = {name: str(value) if value is not None else None for name, value in row.items() if name not in definitions}
        if any(len(str(value)) > 2000 for value in dimensions.values()):
            raise ValueError('Source field exceeds report cell bounds')
        for name, value in row.items():
            definition = definitions.get(name, {})
            if definition and value is not None:
                number = Decimal(str(value))
                if not number.is_finite() or abs(number.adjusted()) > 1000:
                    raise ValueError('Invalid quantitative observation')
            snapshot = (comparison['before'] if name == 'stock_before' else comparison['after'] if name == 'stock_after'
                        else comparison['before']+' through '+comparison['after'] if name == 'stock_delta' else None) if comparison else None
            facts.append(ReportFact(id=f'F{start+len(facts)}', evidence_id=evidence_id, task_id=task.id,
                metric=name, value=value if value is None or isinstance(value, bool) else str(value),
                unit=definition.get('unit', 'source_field'), dimensions=dimensions, filters=[scope], snapshot_date=snapshot,
                formula=definition.get('formula'), approval_status=definition.get('approval_status'), source_row=row_index))
            row_facts.append(facts[-1])
        if comparison:
            operands = {fact.metric:fact.id for fact in row_facts}
            for fact in row_facts:
                if fact.metric == 'stock_delta':
                    fact.operands = [operands['stock_before'], operands['stock_after']]
    return facts


def compare_facts(before, after, identifier):
    if (before.metric, before.unit, before.dimensions, before.filters) != (after.metric, after.unit, after.dimensions, after.filters):
        raise ValueError('Comparison requires matching metric, units, dimensions and filters')
    if not before.snapshot_date or not after.snapshot_date or before.snapshot_date >= after.snapshot_date:
        raise ValueError('Comparison requires ordered, distinct snapshots')
    difference = percent = None
    if before.value is not None and after.value is not None:
        if isinstance(before.value, bool) or isinstance(after.value, bool):
            raise ValueError('Recorded flags cannot be subtracted')
        try:
            with localcontext() as context:
                context.prec = 38
                left, right = Decimal(before.value), Decimal(after.value)
                if not left.is_finite() or not right.is_finite():
                    raise ValueError('Nonfinite comparison operand')
                difference = str((right-left)*100 if before.unit == 'percent' else right-left)
                percent = str((right-left)/left) if left else None
        except InvalidOperation as error:
            raise ValueError('Comparison requires numerical operands') from error
    base = after.model_dump()
    base.update(operands=[before.id, after.id], snapshot_date=before.snapshot_date+' through '+after.snapshot_date)
    delta = ReportFact(**{**base, 'id': identifier, 'metric': before.metric+'_difference',
                          'value': difference, 'unit': 'percentage_points' if before.unit == 'percent' else before.unit,
                          'formula': '(after - before) * 100' if before.unit == 'percent' else 'after - before'})
    ratio = ReportFact(**{**base, 'id': identifier+'p', 'metric': before.metric+'_percent_change',
                          'value': percent, 'unit': 'percent', 'formula': '(after - before) / before'})
    return delta, ratio


def fact_statement(fact):
    scope = ', '.join(f'{name}={value}' for name, value in fact.dimensions.items())
    date = f'; snapshot={fact.snapshot_date}' if fact.snapshot_date else ''
    return f'{fact.metric}: {display_value(fact)} ({fact.unit}; {scope}{date}) [{fact.id}] [{fact.evidence_id}]'
