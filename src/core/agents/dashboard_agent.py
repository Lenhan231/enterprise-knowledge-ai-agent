"""Build one chart from the existing permission-checked SQL workflow."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import math
import re

from sqlglot import exp, parse_one

from core.agents.sql_analytics_agent import SQLAnalyticsAgent, payload_to_agent_result
from core.models.agents import ChartSeries, ChartSpec


def requested_chart_type(question):
    choices = {
        'line': r'\bline chart\b|biểu đồ đường',
        'bar': r'\bbar chart\b|biểu đồ cột|biểu đồ thanh',
        'donut': r'\bdonut\b|\bdoughnut\b|\bpie chart\b|biểu đồ tròn',
    }
    matches = [kind for kind, pattern in choices.items() if re.search(pattern, question, re.I)]
    if len(matches) > 1:
        raise ValueError('Choose one chart type: line, bar, or donut.')
    return next(iter(matches), None) or ('donut' if re.search(r'\bshare\b|\bcomposition\b|tỷ trọng|cơ cấu', question, re.I) else None)


class DashboardAgent:
    def __init__(self, sql_agent: SQLAnalyticsAgent) -> None:
        self.sql_agent = sql_agent

    async def run(self, request):
        SQLAnalyticsAgent._authorize(request)
        category = request.metadata.get('category')
        if category is not None:
            if not isinstance(category, str) or len(category) > 100:
                raise ValueError('category must be a string of at most 100 characters')
            if category.strip():
                request = request.model_copy(update={'question': request.question +
                    '\nInventory category filter: ' + json.dumps(category.strip(), ensure_ascii=False)})
        context = request.metadata.get('_sql_context') or {}
        chart_question = request.question
        pending = context.get('pending')
        if pending:
            chart_question = pending['question'] + '\nClarification reply: ' + request.question
        if context and not context.get('accepted'):
            # Non-inventory requests use the ordinary SQL path, including its ambiguity check.
            request = request.model_copy(update={'question': chart_question, 'metadata': {
                key: value for key, value in request.metadata.items() if key != '_sql_context'}})
        payload = await self.sql_agent.run_payload(request)
        result = payload_to_agent_result(payload, agent='dashboard')
        if not payload.get('ok') or payload.get('query_status') != 'executed' or not payload.get('rows'):
            result.metadata['chart_status'] = 'unavailable'
            return result
        try:
            chart = build_chart(payload, chart_question)
        except ValueError as error:
            reason = str(error)
            result.metadata.update(chart_status='table_only', chart_reason=reason)
            result.answer = 'The query completed. Showing the result table: ' + reason
        else:
            result.data['visualization'] = chart.model_dump(mode='json')
            result.metadata['chart_status'] = 'rendered'
            result.answer = f'{chart.type.title()} chart from {len(chart.categories)} SQL observations. '
            result.answer += 'Review the data table, source scope, and limitations below.'
        return result


def _numeric(value):
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _unit(name, projection, metadata):
    columns = {item['name']: item.get('unit') for item in metadata.get('columns', [])}
    unit = columns.get(name) or metadata.get('metrics', {}).get(name, {}).get('unit')
    if not unit and projection is not None:
        if projection.find(exp.Div):
            return None
        origins = {column.name for column in projection.find_all(exp.Column)}
        metric_units = {definition.get('unit') for key, definition in metadata.get('metrics', {}).items()
                        if key in origins and definition.get('unit')}
        if len(metric_units) == 1:
            unit = metric_units.pop()
        elif projection.find(exp.Count):
            unit = 'count'
        elif origins <= {'sessions', 'page_views', 'units_sold', 'units_received', 'stock_on_hand'} and origins:
            unit = 'sessions' if origins == {'sessions'} else 'units'
        elif origins & {'revenue', 'cogs', 'amount', 'total_amount', 'subtotal', 'tax_amount'}:
            unit = 'currency'
    if unit and unit.startswith('currency'):
        return 'currency (unconfirmed)'
    if unit == 'percent':
        return 'fraction (0.25 = 25%)'
    return unit


def build_chart(payload, question):
    rows = payload['rows']
    metadata = payload.get('metadata', {})
    try:
        tree = parse_one(payload['sql'], read='postgres')
    except Exception as error:
        raise ValueError('The SQL result has no usable chart mapping.') from error
    projections = {item.alias_or_name: item.unalias() for item in tree.expressions}
    grouped = set()
    for item in (tree.args.get('group') or exp.Group()).expressions:
        if isinstance(item, exp.Literal) and item.is_int:
            index = int(item.this) - 1
            if 0 <= index < len(tree.expressions):
                grouped.add(tree.expressions[index].alias_or_name)
        else:
            grouped.update(name for name, projection in projections.items()
                           if projection == item or isinstance(item, exp.Column) and item.name == name)
    names = list(rows[0])
    currencies = {row.get('currency') for row in rows} if 'currency' in names else set()
    if currencies:
        if len(currencies) != 1 or None in currencies:
            raise ValueError('A chart requires one verified currency; these rows have mixed or unknown currencies.')
        names.remove('currency')
    dimensions = [name for name in names if name in grouped or
                  any(value is not None and not _numeric(value) for value in (row.get(name) for row in rows))]
    constant_dates = {name: str(rows[0][name]) for name in dimensions
                      if name.endswith('date') and len({row.get(name) for row in rows}) == 1}
    if len(dimensions) > 1:
        dimensions = [name for name in dimensions if name not in constant_dates]
        names = [name for name in names if name not in constant_dates]
    if len(dimensions) != 1:
        raise ValueError('Specify one date or category dimension and numeric measures for the chart.')
    dimension = dimensions[0]
    measures = [name for name in names if name != dimension]
    if not measures or len(measures) > 4:
        raise ValueError('Choose between one and four comparable numeric measures.')
    for name in measures:
        values = [row.get(name) for row in rows]
        if not any(value is not None for value in values) or any(
                value is not None and (not _numeric(value) or not math.isfinite(float(value))) for value in values):
            raise ValueError('Chart measures must contain finite numbers; missing values remain unknown.')
    labels = [str(row[dimension]) if row.get(dimension) is not None else '(missing)' for row in rows]
    if len(set(labels)) != len(labels):
        raise ValueError('The dimension has duplicate observations; request a single grouping or narrower scope.')
    values = [row.get(dimension) for row in rows]
    temporal = all(isinstance(value, (date, datetime)) or
                   isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[ T].*)?', value)
                   for value in values)
    temporal = bool(temporal or dimension in {'year', 'fiscal_year'} and all(_numeric(value) for value in values))
    kind = requested_chart_type(question) or ('line' if temporal else 'bar')
    if kind == 'line' and (not temporal or sum(row[measures[0]] is not None for row in rows) < 2):
        raise ValueError('A line chart needs a date axis and at least two observed values.')
    units = [_unit(name, projections.get(name), metadata) for name in measures]
    if len(set(units)) > 1 or len(measures) > 1 and None in units:
        raise ValueError('Choose measures with one confirmed, comparable unit.')
    unit = units[0] or 'source units (unconfirmed)'
    if currencies:
        unit = str(next(iter(currencies)))
    if kind == 'donut':
        _validate_composition(tree, dimension, measures, rows)
    ordered = sorted(rows, key=lambda row: str(row[dimension])) if temporal else rows
    categories = [str(row[dimension]) if row.get(dimension) is not None else '(missing)' for row in ordered]
    return ChartSpec(type=kind, title=question[:200], categories=categories,
                     series=[ChartSeries(name=name.replace('_', ' ').title(),
                                         values=[float(row[name]) if row.get(name) is not None else None
                                                 for row in ordered]) for name in measures],
                     unit=unit, x_label=dimension.replace('_', ' ').title(), y_label=unit, temporal=temporal,
                     scope={'time': metadata.get('time_scope'), 'filters': metadata.get('filters', []),
                            'dates': constant_dates,
                            'snapshot_dates': metadata.get('snapshot_dates', []),
                            'sources': metadata.get('source', [])})


def _validate_composition(tree, dimension, measures, rows):
    reason = 'Donut charts require a complete, exclusive grouping of one additive, nonnegative measure.'
    if len(measures) != 1 or len(list(tree.find_all(exp.Select))) != 1 or tree.args.get('joins') or any(
            tree.args.get(key) for key in ('having', 'offset', 'distinct')):
        raise ValueError(reason)
    tables = list(tree.find_all(exp.Table))
    group = tree.args.get('group')
    if len(tables) != 1 or not group or len(group.expressions) != 1:
        raise ValueError(reason)
    projections = {item.alias_or_name: item.unalias() for item in tree.expressions}
    measure = projections.get(measures[0])
    category = projections.get(dimension)
    # shortcut: prove composition only for simple single-table groups; extend with provenance for joins/CTEs.
    additive = {'web_traffic': {'sessions', 'page_views'}, 'sales': {'revenue', 'cogs'},
                'inventory': {'stock_on_hand', 'units_received', 'units_sold'}}
    safe_sum = (isinstance(measure, exp.Sum) and isinstance(measure.this, exp.Column)
                and measure.this.name in additive.get(tables[0].name, set()))
    safe_count = isinstance(measure, exp.Count) and isinstance(measure.this, exp.Star)
    if not isinstance(category, exp.Column) or not (safe_sum or safe_count):
        raise ValueError(reason)
    limit = tree.args.get('limit')
    if limit and (not isinstance(limit.expression, exp.Literal) or len(rows) >= int(limit.expression.this)):
        raise ValueError('The result may be truncated; request the complete category distribution for a donut chart.')
    values = [row[measures[0]] for row in rows]
    if any(value is None or value < 0 for value in values) or sum(values) <= 0:
        raise ValueError(reason)
