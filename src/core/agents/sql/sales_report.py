"""Fixed sales SQL plans executed through the SQL Agent's existing security boundary."""
import asyncio
from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import math

from core.agents.sql.text_to_sql import validate_commerce_sql
from core.agents.runtime import remaining
from core.agents.report.sales_performance import load_contract, month_start, monthly_scopes


async def query(agent, request, sql, parameters=()):
    agent._authorize(request)
    validated = validate_commerce_sql(sql, allowed_sources=set(agent.table_columns), schema_columns=agent.table_columns)
    rows = await asyncio.wait_for(agent.repository.execute_approved_query(validated.sql, *parameters), remaining(15))
    return rows, validated.sources


async def latest(agent, request):
    rows, _ = await query(agent, request, 'SELECT MAX(s.date) AS latest FROM commerce.sales AS s LIMIT 1')
    return rows[0]['latest'] if rows else None


def plans(scope):
    supported = load_contract()['supported_request']
    if scope['granularity'] not in supported['granularities'] or scope['dimension'] not in supported['dimensions']:
        raise ValueError('Unsupported sales report scope')
    start, end = (date.fromisoformat(scope['period'][k]) for k in ('start', 'end_exclusive'))
    if start >= end or start.day != 1 or end.day != 1:
        raise ValueError('Sales reports require calendar period boundaries')
    months = (end.year - start.year) * 12 + end.month - start.month
    if months > 200:
        raise ValueError('Sales reports support up to 200 calendar months per request')
    prior = month_start(start.year, start.month - months)
    args = (start, end, prior)
    # Full daily company coverage is required for calendar comparisons, including internal gaps.
    company_totals = """WITH totals AS (
        SELECT SUM(s.revenue) FILTER (WHERE s.date >= $1) AS revenue,
        SUM(s.cogs) FILTER (WHERE s.date >= $1) AS cogs,
        SUM(s.revenue) FILTER (WHERE s.date < $1) AS prior_revenue,
        SUM(s.cogs) FILTER (WHERE s.date < $1) AS prior_cogs,
        COUNT(DISTINCT s.date) FILTER (WHERE s.date >= $1) AS days,
        COUNT(DISTINCT s.date) FILTER (WHERE s.date < $1) AS prior_days,
        MIN(s.date) FILTER (WHERE s.date >= $1) AS coverage_start,
        MAX(s.date) FILTER (WHERE s.date >= $1) AS coverage_end,
        ($2::date - $1::date) AS expected_current_days, ($1::date - $3::date) AS expected_prior_days
        FROM commerce.sales AS s WHERE s.date >= $3 AND s.date < $2)"""
    company_values = """t.revenue AS company_revenue, t.cogs AS company_cogs,
        t.revenue-t.cogs AS company_gross_profit,
        100*(t.revenue-t.cogs)/NULLIF(t.revenue,0) AS company_gross_margin_pct,
        CASE WHEN t.days = t.expected_current_days AND t.prior_days = t.expected_prior_days
        THEN 100*(t.revenue-t.prior_revenue)/NULLIF(t.prior_revenue,0) END AS company_revenue_change_pct,
        t.prior_revenue-t.prior_cogs AS prior_gross_profit,
        t.days = t.expected_current_days AND t.prior_days = t.expected_prior_days AS comparable,
        t.days <> t.expected_current_days AS partial_period,
        t.coverage_start, t.coverage_end, t.expected_current_days-t.days AS missing_or_unmatched_count,
        t.days AS current_days, t.prior_days AS prior_days,
        t.prior_revenue AS prior_revenue,
        t.expected_current_days, t.expected_prior_days, t.days AS source_count"""
    company = company_totals + ' SELECT ' + company_values + ' FROM totals AS t LIMIT 1'
    monthly_totals = """WITH monthly AS (
        SELECT DATE_TRUNC('month', s.date)::date AS period, SUM(s.revenue) AS revenue,
        SUM(s.cogs) AS cogs, COUNT(DISTINCT s.date) AS days, MIN(s.date) AS coverage_start, MAX(s.date) AS coverage_end
        FROM commerce.sales AS s WHERE s.date >= $3 AND s.date < $2 GROUP BY 1),
        totals AS (SELECT c.period, c.revenue, c.cogs, p.revenue AS prior_revenue, p.cogs AS prior_cogs,
        c.days, COALESCE(p.days,0) AS prior_days, c.coverage_start, c.coverage_end,
        (c.period + INTERVAL '1 month')::date-c.period AS expected_current_days,
        c.period-(c.period - INTERVAL '1 month')::date AS expected_prior_days
        FROM monthly AS c LEFT JOIN monthly AS p ON p.period = (c.period - INTERVAL '1 month')::date
        WHERE c.period >= $1)"""
    dimension = scope['dimension']
    expressions = {'all': "'all'", 'category': 'p.category', 'product': 'p.product_id', 'region': 'g.region', 'order_source': 'o.order_source'}
    expression = expressions[dimension]
    joins = ' FROM commerce.orders AS o'
    if dimension == 'region':
        joins += ' LEFT JOIN commerce.geography AS g ON o.zip = g.zip'
    line_joins = ' FROM commerce.orders AS o LEFT JOIN commerce.order_items AS oi ON oi.order_id = o.order_id'
    if dimension in {'category', 'product'}:
        line_joins += ' JOIN commerce.products AS p ON oi.product_id = p.product_id'
    if dimension == 'region':
        line_joins += ' LEFT JOIN commerce.geography AS g ON o.zip = g.zip'
    where = ' WHERE o.order_date >= $1 AND o.order_date < $2'
    line_args = (start, end)
    if scope['dimension_value'] is not None:
        where += ' AND ' + expression + ' = $3'
        value = scope['dimension_value']
        if dimension == 'product':
            if not isinstance(value, str) or not value.isascii() or not value.isdigit() or not 0 < int(value) <= 2147483647:
                raise ValueError('Product filters require a quoted numeric product ID.')
            value = int(value)
        line_args += (value,)
    delivered = "o.order_status = 'delivered'"
    revenue = 'SUM(oi.quantity*oi.unit_price-oi.discount_amount)'
    line_values = (f'{revenue} FILTER (WHERE {delivered}) AS delivered_line_revenue, '
                   f'{revenue} FILTER (WHERE {delivered}) / NULLIF(COUNT(DISTINCT o.order_id) FILTER (WHERE {delivered}),0) AS delivered_average_order_value, '
                   'SUM(oi.discount_amount) AS promotion_discount, COUNT(oi.order_item_id) AS source_count')
    grain = scope['granularity']  # Already restricted to the three contract literals.
    bucket = f"DATE_TRUNC('{grain}', o.order_date)::date"
    return {
        'company': (company, args),
        'coverage_dates': ('SELECT ARRAY_AGG(DISTINCT s.date ORDER BY s.date) AS dates FROM commerce.sales AS s '
                           'WHERE s.date >= $1 AND s.date < $2 AND s.revenue IS NOT NULL AND s.cogs IS NOT NULL LIMIT 1',
                           (month_start(start.year, start.month-1), end)) if dimension == 'all' else None,
        'monthly_company': (monthly_totals + ' SELECT t.period, ' + company_values + ' FROM totals AS t ORDER BY t.period LIMIT 200',
                            (start, end, month_start(start.year, start.month-1))) if dimension == 'all' and months > 1 else None,
        'sales_trend': (f"SELECT DATE_TRUNC('{grain}', s.date)::date AS period, SUM(s.revenue) AS company_revenue, SUM(s.revenue)-SUM(s.cogs) AS company_gross_profit FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 GROUP BY 1 ORDER BY 1 LIMIT 200", (start, end)),
        'orders': ('SELECT COUNT(DISTINCT o.order_id) AS order_count, COUNT(*) AS source_count' + joins + where + ' LIMIT 1', line_args) if dimension not in {'category', 'product'} else None,
        'lines': ('SELECT ' + line_values + line_joins + where + ' LIMIT 1', line_args),
        'line_breakdown': (f'SELECT {expression} AS dimension, {revenue} AS delivered_line_revenue' + line_joins + where + f' AND {delivered} GROUP BY 1 ORDER BY 1 LIMIT 200', line_args),
        'sales_discount': (f'SELECT {bucket} AS period, SUM(oi.discount_amount) AS promotion_discount' + line_joins + where + ' GROUP BY 1 ORDER BY 1 LIMIT 200', line_args),
        'traffic': ('SELECT SUM(w.sessions) AS sessions, COUNT(*) AS source_count FROM commerce.web_traffic AS w WHERE w.date >= $1 AND w.date < $2 LIMIT 1', (start, end)),
        'web_sessions': (f"SELECT DATE_TRUNC('{grain}', w.date)::date AS period, SUM(w.sessions) AS sessions FROM commerce.web_traffic AS w WHERE w.date >= $1 AND w.date < $2 GROUP BY 1 ORDER BY 1 LIMIT 200", (start, end)),
    }


def numeric(value):
    if isinstance(value, Decimal):
        value = float(value)
    if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)):
        raise ValueError('Non-finite or invalid SQL metric')
    return value


async def run(agent, request, scope):
    agent._authorize(request)
    queries = plans(scope)
    outcomes = {}
    limitations = ['Synthetic commerce demo data; currency unspecified. Company sales and delivered-line revenue are separate sources.',
                   'Order and traffic source completeness is unverified; totals describe matching records, not certified complete periods. No causal explanations are established.',
                   'Missing count describes absent company sales dates. Null dimension labels are retained as unknown; unmatched dimension counts are unverified.']
    semaphore = asyncio.Semaphore(3)
    async def execute(key, plan):
        if plan is None:
            return
        sql, args = plan
        try:
            async with semaphore:
                rows, sources = await query(agent, request, sql, args)
            outcomes[key] = {'rows': rows, 'status': 'available', 'evidence': [{
                'source_table': ', '.join(sorted(sources)),
                'query_id': hashlib.sha256((sql + repr(args)).encode()).hexdigest()[:16],
                'filters': {**scope, 'period':{'start':args[0].isoformat(), 'end_exclusive':args[1].isoformat()}} if key == 'coverage_dates' else scope,
                'row_count': len(rows), 'document_id': None, 'citation': None}]}
        except PermissionError:
            outcomes[key] = {'rows': [], 'status': 'access_denied', 'evidence': []}
            limitations.append(f'{key}: access denied.')
        except Exception:
            outcomes[key] = {'rows': [], 'status': 'not_available', 'evidence': []}
            limitations.append(f'{key}: validated source query unavailable.')
    months = list(monthly_scopes(scope))
    await asyncio.gather(*(execute(k, p) for k, p in queries.items()))
    monthly_outcome = outcomes.get('monthly_company', {})
    monthly_rows = {row['period'].isoformat(): row for row in monthly_outcome.get('rows', [])}
    monthly = []
    for month in months:
        outcome = outcomes.get('company', {}) if month['period'] == scope['period'] else monthly_outcome
        row = ((outcome.get('rows') or [{}])[0] if month['period'] == scope['period']
               else monthly_rows.get(month['period']['start'], {})) if scope['dimension'] == 'all' else {}
        evidence = [{**e, 'filters': month,
                     'query_id': hashlib.sha256((e['query_id'] + month['period']['start']).encode()).hexdigest()[:16]}
                    for e in outcome.get('evidence', [])] if scope['dimension'] == 'all' else []
        month_metrics = []
        for definition in load_contract()['runtime_output_template']['metrics']:
            if definition['source'] != 'commerce.sales':
                continue
            metric = deepcopy(definition)
            value = numeric(row.get(metric['id'])) if scope['dimension'] == 'all' and row.get('source_count') else None
            metric.update(value=value, status='available' if value is not None else 'not_available',
                          evidence=evidence)
            month_metrics.append(metric)
        monthly.append({'period': month['period'], 'metrics': month_metrics,
                        'comparison': {'comparable': row.get('comparable'), 'prior_gross_profit': numeric(row.get('prior_gross_profit'))},
                        'coverage': {k: row.get(k) for k in ('current_days', 'expected_current_days', 'prior_days', 'expected_prior_days')}})
    metrics = {}
    definitions = {m['id']: m for m in load_contract()['metrics']}
    groups = {'company': [m['id'] for m in definitions.values() if m['source'] == 'commerce.sales'],
              'orders': ['order_count'], 'lines': ['delivered_line_revenue', 'delivered_average_order_value', 'promotion_discount'], 'traffic': ['sessions']}
    for key, identifiers in groups.items():
        outcome = outcomes.get(key, {'rows': [], 'status': 'not_available', 'evidence': []})
        row = outcome['rows'][0] if outcome['rows'] else {}
        for identifier in identifiers:
            definition = definitions[identifier]
            unsupported = scope['dimension'] not in definition['allowed_dimensions']
            value = numeric(row.get(identifier)) if not unsupported else None
            status = 'available' if value is not None else 'not_available' if unsupported else outcome['status']
            if value is None and status == 'available':
                status = 'no_data' if not row.get('source_count') else 'not_available'
            # COUNT on an empty population is not a supplied zero observation.
            if not row.get('source_count') and status == 'available':
                value, status = None, 'no_data'
            metrics[identifier] = {'value': value, 'status': status, 'evidence': outcome['evidence'] if not unsupported else []}
    company = (outcomes.get('company', {}).get('rows') or [{}])[0]
    quality = {k: company.get(k) for k in ('coverage_start', 'coverage_end', 'partial_period', 'missing_or_unmatched_count')}
    for k in ('coverage_start', 'coverage_end'):
        if quality[k] is not None:
            quality[k] = quality[k].isoformat()
    if quality['partial_period'] is not False:
        limitations.append('Company daily coverage is incomplete or unknown; comparison rules require complete current and prior periods.')
    if company and company.get('comparable') is not True:
        _, parameters = queries['company']
        start, end, prior = parameters
        limitations.append(
            f"Period-over-period comparison uses calendar-month totals. Daily records verify source coverage only. "
            f"{start} to {end} (end excluded): {company.get('current_days', 'unknown')} of {company.get('expected_current_days', 'unknown')} days; "
            f"{prior} to {start} (end excluded): {company.get('prior_days', 'unknown')} of {company.get('expected_prior_days', 'unknown')} days. "
            'Whole-period revenue change and aggregate comparison-dependent decisions are unavailable; monthly decisions use separate calendar-month baselines. Current-period revenue and profitability remain usable.')
    if company.get('comparable') is True and company.get('prior_revenue') == 0:
        limitations.append('Revenue change is undefined because prior-period revenue is zero.')
    if scope['dimension'] != 'all':
        limitations.append('Company-level KPIs and comparison decisions are unsupported for this dimension. Company sales cannot be allocated to order-line dimensions.')
    quality['limitations'] = limitations
    datasets = {}
    for key in ('sales_trend', 'line_breakdown', 'sales_discount', 'web_sessions'):
        datasets[key] = [{k: str(v) if k == 'dimension' and v is not None else v.isoformat() if isinstance(v, date) else numeric(v) if isinstance(v, (Decimal, int, float)) else v for k, v in row.items()}
                         for row in outcomes.get(key, {}).get('rows', [])]
        if len(datasets[key]) == 200:
            limitations.append(f'{key}: chart reached the 200-row SQL limit; additional categories may be omitted.')
    if scope['dimension'] != 'all':
        datasets['sales_trend'] = []
        datasets['web_sessions'] = []
    sources_complete = all(outcome['status'] == 'available' for outcome in outcomes.values()) and all(len(rows) < 200 for rows in datasets.values())
    coverage = outcomes.get('coverage_dates', {})
    coverage_row = (coverage.get('rows') or [{}])[0]
    return {'metrics': metrics, 'datasets': datasets, 'data_quality': quality, 'sources_complete': sources_complete, 'monthly_decisions': monthly,
            'coverage': {'coverage_status':coverage.get('status', 'unsupported' if scope['dimension'] != 'all' else 'not_available'),
                         'coverage_evidence':[{'citation_id':e['query_id'], 'source_type':'database', 'source':e['source_table'], 'metadata':e} for e in coverage.get('evidence', [])],
                         'observed_dates':coverage_row.get('dates') or []},
            'comparison': {'comparable': company.get('comparable'), 'prior_gross_profit': numeric(company.get('prior_gross_profit'))}}
