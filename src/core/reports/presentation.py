"""Human-facing report copy without altering source metric definitions."""
from datetime import date

from core.reports.sales_performance import load_contract, month_start

SECTION_TITLES = {s['id']: s['title'] for s in load_contract()['section_contract']}
CURRENCY_NOTE = 'Amounts are displayed in VND as requested. The source has no currency tag; no currency conversion has been applied.'


def default_chart_types(report):
    types = {'line_breakdown': 'kpi_row'}
    start = date.fromisoformat(report['request']['period']['start'])
    if report['request']['period']['end_exclusive'] == month_start(start.year, start.month + 1).isoformat():
        types.update({w['id']: 'kpi_row' for w in report['dashboard']['widgets']
                      if w['x_dimension'] == 'period' and w['type'] != 'kpi_row'})
    return types


def calendar_rows(widget, scope):
    """Keep the requested calendar axis; absent SQL observations stay null."""
    if widget['x_dimension'] != 'period':
        return widget['data']
    start = date.fromisoformat(scope['period']['start'])
    end = date.fromisoformat(scope['period']['end_exclusive'])
    step = {'month': 1, 'quarter': 3, 'year': 12}[scope['granularity']]
    current = date(start.year, (start.month - 1) // step * step + 1, 1)
    observed = {row['period']: row for row in widget['data']}
    rows = []
    while current < end:
        period = current.isoformat()
        rows.append(dict(observed.get(period, {'period': period, **dict.fromkeys(widget['metric_ids'])})))
        current = month_start(current.year, current.month + step)
    return rows


def display_value(metric, value=None):
    value = metric['value'] if value is None else value
    if value is None:
        return 'Unavailable'
    number = f'{value:,.2f}'.rstrip('0').rstrip('.')
    if metric['unit'] == 'percent':
        return number + '%'
    if metric['unit'].startswith('unknown_currency'):
        return number + ' VND'
    return number


def comparison_metrics(report, monthly=()):
    """Show a labelled monthly comparison while retaining the canonical whole-period facts."""
    if not monthly or report['request']['granularity'] != 'month':
        return report['metrics']
    observed = [m for m in monthly if any(v['id'] == 'company_revenue' and v['value'] is not None for v in m['metrics'])]
    selected = (observed or monthly)[-1]
    start = date.fromisoformat(selected['period']['start'])
    prior = month_start(start.year, start.month-1)
    change = next(m for m in selected['metrics'] if m['id'] == 'company_revenue_change_pct')
    change = {**change, 'label': f'Company revenue month-over-month change ({start:%Y-%m} vs {prior:%Y-%m})'}
    return [change if m['id'] == change['id'] else m for m in report['metrics']]


def observations(report, section, monthly=()):
    metrics = {m['id']: m for m in comparison_metrics(report, monthly)}
    specification = next(s for s in load_contract()['section_contract'] if s['id'] == section)
    result = []
    for slot in specification.get('fixed_slots', []):
        available = [metrics[k] for k in slot['metric_ids'] if metrics[k]['status'] == 'available']
        text = ' '.join(f"The {m['label'].lower()} is {display_value(m)}." for m in available)
        if not text and slot['id'] == 'revenue_movement':
            text = 'Period-over-period revenue change is unavailable for this scope. See the data notes below.'
        if not text:
            continue
        result.append({'text': text, 'metric_ids': [m['id'] for m in available]})
    return result


def decision_text(rule, report=None):
    if rule['triggered'] is True:
        text = rule['action']
    elif rule['triggered'] is False:
        text = 'Evaluated: this predefined risk condition was not met.'
    else:
        text = None
    if text is not None:
        if rule['id'] == 'S02' and report is not None:
            metrics = {m['id']: m for m in report['metrics']}
            text += f" Gross profit is {display_value(metrics['company_gross_profit'])} and revenue is {display_value(metrics['company_revenue'])}."
        return text
    if rule['id'] == 'S04':
        return 'A no-trigger conclusion is withheld because at least one comparison rule cannot be evaluated.'
    if rule['id'] in {'S01', 'S03'}:
        return 'Cannot evaluate this comparison with the selected scope and available baseline. See the data notes below.'
    return 'Cannot evaluate: current-period revenue or gross profit is unavailable.'


def data_notes(report):
    notes = [CURRENCY_NOTE]
    if any(w['x_dimension'] == 'period' and w['type'] != 'kpi_row'
           and len(calendar_rows(w, report['request'])) > len(w['data']) for w in report['dashboard']['widgets']):
        notes.append('Unobserved calendar periods are shown as gaps, not zero values.')
    detailed = any(note.startswith('Period-over-period comparison') for note in report['data_quality']['limitations'])
    for note in report['data_quality']['limitations']:
        if note.startswith('Synthetic commerce'):
            notes.append('Synthetic commerce demonstration data. Company sales and delivered-order sales are independent sources.')
        elif note.startswith('Missing count describes') or detailed and note.startswith('Company daily coverage'):
            continue
        else:
            notes.append(note)
    return notes
