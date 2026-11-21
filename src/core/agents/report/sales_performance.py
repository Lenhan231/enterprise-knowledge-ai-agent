"""Immutable sales contract, calendar scope, and evidence-only report assembly."""
from copy import deepcopy
from datetime import date
import json
import math
import re
from pathlib import Path
from core.agents.language import is_vietnamese
from core.agents.report.labels import localize_labels, localize_metrics, uses_vietnamese_labels

CONTRACT_PATH = Path(__file__).resolve().parents[4] / 'data/semantic/sales_performance_strict.json'
from core.agents.report.calendar_scope import FINANCIAL_OVERVIEW, parse_request, scope_text, has_sales_period, month_start


def load_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding='utf-8'))


def evaluate_decisions(report, comparison):
    metrics = {m['id']: m for m in report['metrics']}
    def value(key):
        metric = metrics[key]
        return metric['value'] if metric['status'] == 'available' else None
    revenue, profit, change = (value(k) for k in ('company_revenue', 'company_gross_profit', 'company_revenue_change_pct'))
    comparable = comparison.get('comparable') is True
    prior_profit = comparison.get('prior_gross_profit')
    results = [change < 0 if comparable and change is not None else None,
               profit <= 0 and revenue > 0 if profit is not None and revenue is not None else None,
               change > 0 and profit < prior_profit if comparable and all(v is not None for v in (change, profit, prior_profit)) else None]
    results.append(not any(results) if all(v is not None for v in results) and revenue is not None and profit is not None else None)
    for rule, triggered in zip(report['decisions'], results):
        rule.update(triggered=triggered, status='available' if triggered is not None else 'not_available',
                    evidence=[e for key in rule['required_metric_ids'] for e in metrics[key]['evidence']] if triggered is not None else [])


def monthly_scopes(scope):
    start = date.fromisoformat(scope['period']['start'])
    end = date.fromisoformat(scope['period']['end_exclusive'])
    if start >= end or start.day != 1 or end.day != 1:
        raise ValueError('Monthly decisions require calendar month boundaries')
    if (end.year-start.year)*12 + end.month-start.month > 200:
        raise ValueError('Sales reports support up to 200 calendar months per request')
    while start < end:
        following = month_start(start.year, start.month + 1)
        yield {**scope, 'period': {'start': start.isoformat(), 'end_exclusive': following.isoformat()}, 'granularity': 'month'}
        start = following


def validate_monthly_decisions(report, monthly):
    if not monthly:  # Saved reports created before monthly evaluations remain readable.
        return
    scopes = list(monthly_scopes(report['request']))
    if len(scopes) != len(monthly):
        raise ValueError('Monthly decisions must cover the requested period')
    for scope, item in zip(scopes, monthly):
        if set(item) != {'period', 'metrics', 'comparison', 'coverage', 'decisions'} or item['period'] != scope['period']:
            raise ValueError('Invalid monthly decision period')
        comparison = item['comparison']
        if (not isinstance(comparison, dict) or set(comparison) != {'comparable', 'prior_gross_profit'}
                or comparison['comparable'] is not None and type(comparison['comparable']) is not bool):
            raise ValueError('Invalid monthly comparison')
        profit = comparison['prior_gross_profit']
        if profit is not None and (type(profit) not in (int, float) or not math.isfinite(profit)):
            raise ValueError('Invalid monthly prior gross profit')
        coverage = item['coverage']
        if (not isinstance(coverage, dict) or set(coverage) != {'current_days', 'expected_current_days', 'prior_days', 'expected_prior_days'}
                or any(v is not None and (type(v) is not int or not 0 <= v <= 31) for v in coverage.values())):
            raise ValueError('Invalid monthly daily coverage')
        if comparison['comparable'] is True and any(coverage[k] is None or coverage[k] != coverage['expected_' + k] for k in ('current_days', 'prior_days')):
            raise ValueError('Monthly comparison requires complete coverage')
        expected = deepcopy(report)
        expected['request'] = scope
        company = [m for m in expected['metrics'] if m['source'] == 'commerce.sales']
        if [m['id'] for m in item['metrics']] != [m['id'] for m in company]:
            raise ValueError('Monthly metric catalog changed')
        for target, metric in zip(company, item['metrics']):
            target.update(metric)
        populate_sections(expected)
        expected['decisions'] = item['decisions']
        validate_report(expected, item['comparison'])


def populate_sections(report):
    metrics = {m['id']: m for m in report['metrics']}
    for section in load_contract()['section_contract']:
        slots = report['sections'][section['id']]
        if section['id'] == 'sales_kpis':
            for key in slots:
                slots[key] = metrics[key]['value']
        for slot in section.get('fixed_slots', []):
            observations = []
            for key in slot['metric_ids']:
                metric = metrics[key]
                if metric['status'] == 'available' and metric['evidence']:
                    citations = ', '.join(e['query_id'] for e in metric['evidence'])
                    observations.append(f"{metric['label']}: {metric['value']} ({metric['unit']}) [{citations}].")
            slots[slot['id']] = ' '.join(observations) or None


def validate_report(report, comparison=None):
    """Reject changed definitions, unknown slots, invalid runtime values, and invented prose."""
    contract = load_contract()
    base = contract['runtime_output_template']
    if uses_vietnamese_labels(report):
        localize_labels(base)
    def keys(actual, expected):
        if not isinstance(actual, dict) or list(actual) != list(expected):
            raise ValueError('Report keys or order violate the sales contract')
    keys(report, base)
    keys(report['request'], base['request'])
    keys(report['request']['period'], base['request']['period'])
    start, end = (date.fromisoformat(v) for v in report['request']['period'].values())
    if start >= end or report['request']['granularity'] not in contract['supported_request']['granularities'] or report['request']['dimension'] not in contract['supported_request']['dimensions']:
        raise ValueError('Invalid report scope')
    if report['report_type'] != base['report_type']:
        raise ValueError('Invalid report type')
    def definitions(actual, expected, mutable):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError('Report catalog changed')
        for item, fixed in zip(actual, expected):
            keys(item, fixed)
            if any(item[k] != v for k, v in fixed.items() if k not in mutable):
                raise ValueError('Immutable report definition changed')
    definitions(report['metrics'], base['metrics'], {'value', 'status', 'evidence'})
    definitions(report['decisions'], base['decisions'], {'triggered', 'status', 'evidence'})
    for rule in report['decisions']:
        if rule['triggered'] is not None and type(rule['triggered']) is not bool:
            raise ValueError('Decision triggers must be boolean or null')
        if rule['status'] != ('available' if rule['triggered'] is not None else 'not_available'):
            raise ValueError('Invalid decision evaluation status')
    keys(report['dashboard'], base['dashboard'])
    if report['dashboard']['layout'] != 'fixed' or report['dashboard']['columns'] != 2:
        raise ValueError('Dashboard layout changed')
    definitions(report['dashboard']['widgets'], base['dashboard']['widgets'], {'data'})
    for widget in report['dashboard']['widgets']:
        if not isinstance(widget['data'], list) or len(widget['data']) > 200:
            raise ValueError('Invalid chart data')
        for row in widget['data']:
            if not isinstance(row, dict) or list(row) != [widget['x_dimension'], *widget['metric_ids']]:
                raise ValueError('Invalid chart series')
            if row[widget['x_dimension']] is not None and not isinstance(row[widget['x_dimension']], str):
                raise ValueError('Invalid chart category')
            for key in widget['metric_ids']:
                value = row[key]
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                    raise ValueError('Invalid chart observation')
    for metric in report['metrics']:
        value = metric['value']
        if metric['status'] not in contract['permitted_statuses'] or metric['status'] == 'pending':
            raise ValueError('Invalid metric status')
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError('Invalid metric value')
        if (metric['status'] == 'available') != (value is not None) or value is not None and not metric['evidence']:
            raise ValueError('Metric requires validated evidence')
        for evidence in metric['evidence']:
            keys(evidence, contract['evidence_shape'])
            if not evidence['query_id'] or not evidence['source_table']:
                raise ValueError('Missing SQL provenance')
    keys(report['data_quality'], base['data_quality'])
    quality = report['data_quality']
    if quality['partial_period'] is not None and type(quality['partial_period']) is not bool:
        raise ValueError('Invalid coverage status')
    count = quality['missing_or_unmatched_count']
    if count is not None and (type(count) is not int or count < 0):
        raise ValueError('Invalid missing-data count')
    if not isinstance(quality['limitations'], list) or any(not isinstance(item, str) for item in quality['limitations']):
        raise ValueError('Invalid data limitations')
    keys(report['sections'], base['sections'])
    for key in base['sections']:
        keys(report['sections'][key], base['sections'][key])
    expected = deepcopy(report)
    populate_sections(expected)
    if report['sections'] != expected['sections']:
        raise ValueError('Narrative is not a supported metric observation')
    if comparison is not None:
        evaluate_decisions(expected, comparison)
        if report['decisions'] != expected['decisions']:
            raise ValueError('Decision evaluation changed')
    json.dumps(report, allow_nan=False)
    return report


async def generate_sales_report(agent, request):
    from core.models.agents import AgentResult, Evidence
    from core.agents.dashboard.charts import sales_report_widgets
    sql = agent.analytics_agent
    from core.agents.sql.agent import SQLAnalyticsAgent
    SQLAnalyticsAgent._authorize(request)
    scope = parse_request(request.question, latest=await sql.sales_report_latest(request) if 'latest' in scope_text(request.question) else None)
    result = await sql.run_sales_report(request, scope)
    report = deepcopy(load_contract()['runtime_output_template'])
    report['request'] = scope
    for metric in report['metrics']:
        metric.update(result['metrics'][metric['id']])
    report['data_quality'].update(result['data_quality'])
    vi = is_vietnamese(request.question)
    if vi:
        localize_labels(report)
    if re.search(FINANCIAL_OVERVIEW, request.question, re.I):
        report['data_quality']['limitations'].append(
            'Phạm vi tài chính gồm doanh thu, giá vốn, lợi nhuận gộp và biên lợi nhuận gộp từ dữ liệu bán hàng. '
            'Nguồn hiện tại không cung cấp bảng cân đối kế toán hoặc báo cáo lưu chuyển tiền tệ.')
    report['dashboard'] = sales_report_widgets(report['dashboard'], report['metrics'], result['datasets'], scope)
    populate_sections(report)
    evaluate_decisions(report, result['comparison'])
    validate_report(report, result['comparison'])
    monthly = result.get('monthly_decisions', [])
    for item in monthly:
        if vi:
            localize_metrics(item['metrics'])
        evaluated = {'metrics': item['metrics'], 'decisions': deepcopy(report['decisions'])}
        evaluate_decisions(evaluated, item['comparison'])
        item['decisions'] = evaluated['decisions']
    validate_monthly_decisions(report, monthly)
    from core.agents.report.sales_context import retrieve_context, SalesContext, build_insights
    context = await retrieve_context(agent.knowledge_agent, request, scope)
    context = SalesContext.model_validate({**context.model_dump(), **result.get('coverage', {})})
    insights = build_insights(report, monthly, context)
    payload = json.dumps(report, ensure_ascii=False, allow_nan=False).encode('utf-8')
    partial = (not result['sources_complete'] or any(m['status'] != 'available' for m in report['metrics'])
               or report['data_quality']['partial_period'] is not False)
    evidence = {e['query_id']: e for group in [report, *monthly] for metric in group['metrics'] for e in metric['evidence']}
    return AgentResult(answer=payload.decode('utf-8'), agent='report', data={'report': report, 'section_count': 5, 'monthly_decisions': monthly,
                                                                         'sales_context':context.model_dump(mode='json'), 'insights':insights},
                       evidence=[Evidence(citation_id=e['query_id'], source_type='database', source=e['source_table'],
                                          metadata=e) for e in evidence.values()] + context.coverage_evidence + context.documents,
                       metadata={'ok': not partial, 'status': 'partial' if partial else 'complete', 'report_type': 'sales_performance',
                                 'retrieval_status':context.retrieval_status,
                                 'limitations': report['data_quality']['limitations']}), payload, 'application/json'
