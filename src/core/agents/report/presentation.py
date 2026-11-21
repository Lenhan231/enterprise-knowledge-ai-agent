"""Human-facing report copy without altering source metric definitions."""
from datetime import date
import re

from core.agents.report.sales_performance import load_contract, month_start
from core.agents.report.labels import uses_vietnamese_labels

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
        from core.agents.language import is_vietnamese
        return 'Không có dữ liệu' if is_vietnamese(metric.get('label', '')) else 'Unavailable'
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
    label = (f'Thay đổi doanh thu công ty theo tháng ({start:%m/%Y} so với {prior:%m/%Y})'
             if uses_vietnamese_labels(report) else f'Company revenue month-over-month change ({start:%Y-%m} vs {prior:%Y-%m})')
    change = {**change, 'label': label}
    return [change if m['id'] == change['id'] else m for m in report['metrics']]


def observations(report, section, monthly=()):
    vi = uses_vietnamese_labels(report)
    metrics = {m['id']: m for m in comparison_metrics(report, monthly)}
    specification = next(s for s in load_contract()['section_contract'] if s['id'] == section)
    result = []
    for slot in specification.get('fixed_slots', []):
        available = [metrics[k] for k in slot['metric_ids'] if metrics[k]['status'] == 'available']
        text = ' '.join(f"{m['label']}: {display_value(m)}." if vi else f"The {m['label'].lower()} is {display_value(m)}."
                        for m in available)
        if not text and slot['id'] == 'revenue_movement':
            text = ('Chưa đủ dữ liệu để so sánh doanh thu giữa các kỳ. Xem ghi chú dữ liệu bên dưới.'
                    if vi else 'Period-over-period revenue change is unavailable for this scope. See the data notes below.')
        if not text:
            continue
        result.append({'text': text, 'metric_ids': [m['id'] for m in available]})
    return result


def decision_text(rule, report=None):
    if rule['id'].startswith('I'):
        if rule['triggered'] is True:
            return {
                'I01': 'Review the flagged product list and confirm current sellable stock and open orders. Investigate discrepancies before changing purchases or customer commitments.',
                'I02': 'Confirm current stock and existing purchase commitments, then review the flagged products with the inventory planner. Obtain approval before ordering; no purchase quantity or lead time is inferred.',
                'I03': 'Inspect flagged products and check for overlapping stockout flags. Confirm current sellable quantities before considering transfers or markdowns; disposal or write-off needs separate approval.',
                'I04': 'Continue routine monitoring. No stockout, reorder or overstock flags were recorded in this covered snapshot; this does not establish current availability.',
            }[rule['id']]
        if rule['triggered'] is False:
            return 'Evaluated: this predefined condition was not met.'
        return ('A no-exception conclusion is withheld because snapshot coverage or flag evidence is incomplete.'
                if rule['id'] == 'I04' else 'Cannot evaluate: the required recorded flag count is unavailable.')
    if rule['triggered'] is True:
        text = {
            'S01': 'Compare revenue by month and review dated sales, pricing and promotion records for the affected periods. Confirm the cause before changing commercial plans.',
            'S02': 'Review revenue and COGS source entries, discounts and pricing conditions. Investigate the nonpositive gross profit before approving a corrective action.',
            'S03': 'Compare current and prior COGS and gross profit, then review dated pricing and promotion changes. Revenue growth alone does not establish improved profitability or its cause.',
            'S04': 'Continue routine monitoring. None of the predefined risk conditions were met; this is not a certification of business health.',
        }[rule['id']]
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


def inventory_insights(report):
    metrics = {m['id']: m for m in report['metrics']}
    quality = report['data_quality']
    available = sum(m['status'] == 'available' and m['value'] is not None for m in metrics.values())
    date_text = quality['coverage_end'] or 'unavailable'
    missing = quality['missing_or_unmatched_count']
    summary = [f'{available} of {len(metrics)} fixed metric values are available from validated source queries.',
               f'Selected inventory snapshot: {date_text}. Balances use this date only.']
    summary.append('Catalog-relative snapshot coverage verified; no missing or unmatched products.'
        if quality['partial_period'] is False and missing == 0 else
        f'Snapshot coverage needs review: {missing} missing or unmatched products.' if missing is not None else
        'Snapshot coverage could not be verified. Confirm the snapshot and product catalog before relying on a no-exception conclusion.')
    actions = []
    for rule in report['decisions']:
        if rule['triggered'] is not True:
            continue
        key, flag = {'I01':('stockout_products','stockout'), 'I02':('reorder_products','reorder'), 'I03':('overstock_products','overstock')}.get(rule['id'],(None,None))
        why = (f"{display_value(metrics[key])} products carry the {flag} flag in the {date_text} snapshot. Flags are signals for review."
               if key else f'All three recorded flag counts are zero and catalog-relative coverage is verified for {date_text}.')
        actions.append({'title':rule['title'], 'why':why, 'action':decision_text(rule, report),
                        'citations':list(dict.fromkeys(e['query_id'] for e in rule['evidence']))})
    return {'actions':actions, 'validation_summary':summary}


def data_notes(report):
    if report['report_type'] == 'inventory_operations':
        return inventory_notes(report)
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


def inventory_source_name(source):
    labels = {'commerce.inventory': 'Inventory records', 'commerce.products': 'Product catalog',
              'commerce.returns': 'Return records', 'commerce.orders': 'Order records',
              'commerce.shipments': 'Shipment records', 'commerce.reviews': 'Customer reviews'}
    names = []
    for name in source.split(', '):
        if name in labels:
            names.append(labels[name])
        else:
            name = name.replace('\\', '/').rsplit('/', 1)[-1]
            name = re.sub(r'\.(?:pdf|docx?|xlsx?|csv|md|txt)$', '', name, flags=re.I)
            names.append(re.sub(r'^\d{2}[_ -]+', '', name).replace('_', ' '))
    return ', '.join(names)


def inventory_display_value(metric):
    suffix = {'units': ' units', 'calendar_days': ' days', 'rating_1_to_5': ' / 5'}.get(metric['unit'], '')
    return display_value(metric) + (suffix if metric['value'] is not None else '')


def inventory_notes(report):
    labels = {'snapshot': 'Inventory snapshot', 'coverage': 'Snapshot coverage',
              'inventory_flag_distribution': 'Flag distribution', 'stockout_product_table': 'Stockout product list',
              'inventory_snapshots': 'Snapshot history', 'returns': 'Returned orders',
              'shipments': 'Shipment duration', 'reviews': 'Review ratings'}
    notes = []
    for note in report['data_quality']['limitations']:
        if note.startswith(('Dashboard source [', 'Policy source [', 'Policy Evidence:')):
            continue
        if note.startswith('Synthetic commerce'):
            note = 'Synthetic commerce demonstration data. Transaction records and historical catalog membership are not certified complete. No forecasts, service commitments, reorder quantities or causal conclusions are inferred.'
        elif note.startswith('Snapshot policy:'):
            note = 'Inventory balances use one observed snapshot before the reporting period ends. Older snapshots are labelled stale; the history chart shows each snapshot independently.'
        elif note.startswith(('days_of_supply', 'fill_rate')):
            note = 'Days of supply, fill rate and sell-through metrics are excluded because their source definitions are not validated.'
        elif note.startswith('stockout/reorder/overstock'):
            note = 'Stockout, reorder and overstock flags can overlap; do not add these product counts together.'
        elif note.startswith('Snapshot completeness'):
            note = ('Coverage is checked against the current product catalog; historical membership is not certified. ' +
                    ('Catalog coverage is verified for the selected snapshot.' if report['data_quality']['partial_period'] is False else
                     'Complete snapshot coverage is unverified or incomplete; the no-exception conclusion is withheld.'))
        elif note == 'Inventory snapshot selection query unavailable.':
            note = 'A snapshot date could not be verified from the available inventory records.'
        else:
            metric = next((m for m in report['metrics'] if note.startswith(m['id'] + ': not_available')), None)
            label = labels.get(note.split(':')[0])
            if metric:
                note = metric['label'] + ': unavailable for this breakdown. No approximation has been applied.'
            elif label and 'access denied' in note:
                note = label + ': source access is restricted.'
            elif label and 'validated source query unavailable' in note:
                note = label + ': the source could not be retrieved or verified.'
            elif label and '200-row' in note:
                note = label + ': the first 200 results are shown; additional records may be omitted.'
        if note not in notes:
            notes.append(note)
    reasons = {'no_data': 'No matching observations for these dates.', 'access_denied': 'Source access is restricted.',
               'unresolved': 'The metric definition or reporting scope is unresolved.'}
    for metric in report['metrics']:
        if metric['value'] is None and not any(note.startswith(metric['label'] + ':') for note in notes):
            notes.append(metric['label'] + ': ' + reasons.get(metric['status'], 'Unavailable for this scope or source.'))
    return notes
