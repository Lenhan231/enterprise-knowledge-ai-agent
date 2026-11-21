"""Human-facing report copy without altering source metric definitions."""
from datetime import date
import re

from core.agents.report.sales_performance import load_contract, month_start
from core.agents.report.labels import INVENTORY_COPY_VI, uses_vietnamese_labels

SECTION_TITLES = {s['id']: s['title'] for s in load_contract()['section_contract']}
CURRENCY_NOTE = 'Amounts are displayed in VND as requested. The source has no currency tag; no currency conversion has been applied.'
CURRENCY_NOTE_VI = 'Số tiền hiển thị theo đơn vị VND. Nguồn không ghi đơn vị tiền tệ và chưa áp dụng quy đổi.'
SALES_ACTIONS_VI = {
    'S01': 'So sánh doanh thu theo tháng và đối chiếu hồ sơ bán hàng, giá bán và khuyến mãi theo ngày trong các kỳ liên quan. Xác minh nguyên nhân trước khi thay đổi kế hoạch kinh doanh.',
    'S02': 'Đối chiếu số liệu doanh thu, giá vốn, chiết khấu và điều kiện giá bán. Tìm nguyên nhân khiến lợi nhuận gộp bằng hoặc dưới 0 trước khi phê duyệt biện pháp xử lý.',
    'S03': 'So sánh giá vốn và lợi nhuận gộp giữa hai kỳ, rồi đối chiếu các thay đổi về giá và khuyến mãi theo ngày. Cần thêm bằng chứng để kết luận về khả năng sinh lời và nguyên nhân biến động.',
    'S04': 'Tiếp tục theo dõi định kỳ. Dữ liệu hiện có chưa kích hoạt điều kiện cảnh báo nào trong bộ quy tắc.',
}

_SALES_LIMITATIONS_VI = {
    'Order and traffic source completeness is unverified; totals describe matching records, not certified complete periods. No causal explanations are established.':
        'Chưa xác minh được độ đầy đủ của nguồn đơn hàng và lượt truy cập. Tổng số dựa trên các bản ghi phù hợp. Dữ liệu hiện có chưa xác định nguyên nhân biến động.',
    'Company daily coverage is incomplete or unknown; comparison rules require complete current and prior periods.':
        'Dữ liệu theo ngày của công ty còn thiếu hoặc chưa xác định được độ đầy đủ. Các quy tắc so sánh cần đủ dữ liệu cho cả hai kỳ.',
    'Revenue change is undefined because prior-period revenue is zero.':
        'Không xác định được tỷ lệ thay đổi vì doanh thu kỳ trước bằng 0.',
    'Company-level KPIs and comparison decisions are unsupported for this dimension. Company sales cannot be allocated to order-line dimensions.':
        'Chưa thể phân bổ doanh thu cấp công ty theo nhóm dòng hàng đã chọn để tính chỉ số và so sánh.',
}
_COVERAGE_RANGE = re.compile(r'(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2}) \(end excluded\): (\d+|unknown) of (\d+|unknown) days')


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
    from core.agents.language import is_vietnamese
    vi = is_vietnamese(metric.get('label', ''))
    value = metric['value'] if value is None else value
    if value is None:
        return 'Không có dữ liệu' if vi else 'Unavailable'
    number = f'{value:,.2f}'.rstrip('0').rstrip('.')
    if vi:
        number = number.translate(str.maketrans(',.', '.,'))
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
    vi = report is not None and uses_vietnamese_labels(report)
    if rule['id'].startswith('I'):
        if vi and rule['triggered'] is True:
            return {
                'I01': 'Đối chiếu danh sách sản phẩm có cờ hết hàng với tồn kho có thể bán và đơn hàng đang mở. Xác minh chênh lệch trước khi thay đổi kế hoạch mua hoặc cam kết với khách hàng.',
                'I02': 'Xác nhận số dư và các cam kết mua hàng, rồi rà soát các sản phẩm có cờ cùng người lập kế hoạch tồn kho. Cần phê duyệt trước khi đặt hàng. Số lượng đặt và thời gian giao chưa được xác định.',
                'I03': 'Kiểm tra các sản phẩm có cờ tồn kho quá mức và xem chúng có đồng thời mang cờ hết hàng hay không. Xác nhận lượng có thể bán trước khi điều chuyển hoặc giảm giá. Việc thanh lý hay ghi giảm cần phê duyệt riêng.',
                'I04': 'Tiếp tục theo dõi định kỳ. Tại ngày chốt này không ghi nhận cờ hết hàng, cần đặt lại hoặc tồn kho quá mức. Kết quả chỉ phản ánh ngày chốt đã kiểm tra.',
            }[rule['id']]
        if rule['triggered'] is True:
            return {
                'I01': 'Review the flagged product list and confirm current sellable stock and open orders. Investigate discrepancies before changing purchases or customer commitments.',
                'I02': 'Confirm current stock and existing purchase commitments, then review the flagged products with the inventory planner. Obtain approval before ordering; no purchase quantity or lead time is inferred.',
                'I03': 'Inspect flagged products and check for overlapping stockout flags. Confirm current sellable quantities before considering transfers or markdowns; disposal or write-off needs separate approval.',
                'I04': 'Continue routine monitoring. No stockout, reorder or overstock flags were recorded in this covered snapshot; this does not establish current availability.',
            }[rule['id']]
        status = ('Evaluated: this predefined condition was not met.' if rule['triggered'] is False else
                  'A no-exception conclusion is withheld because snapshot coverage or flag evidence is incomplete.'
                  if rule['id'] == 'I04' else 'Cannot evaluate: the required recorded flag count is unavailable.')
        return INVENTORY_COPY_VI[status] if vi else status
    if vi and rule['triggered'] is None:
        if rule['id'] == 'S04':
            return 'Chưa thể kết luận vì ít nhất một quy tắc so sánh chưa đánh giá được.'
        if rule['id'] in {'S01', 'S03'}:
            return 'Chưa đủ dữ liệu kỳ đối chiếu để đánh giá. Xem ghi chú dữ liệu bên dưới.'
        return 'Chưa có doanh thu hoặc lợi nhuận gộp của kỳ hiện tại để đánh giá.'
    if vi:
        text = SALES_ACTIONS_VI[rule['id']] if rule['triggered'] else 'Kết quả đánh giá chưa thỏa điều kiện cảnh báo này.'
        if rule['id'] == 'S02':
            metrics = {m['id']: m for m in report['metrics']}
            text += f" Lợi nhuận gộp: {display_value(metrics['company_gross_profit'])}. Doanh thu: {display_value(metrics['company_revenue'])}."
        return text
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
    vi = uses_vietnamese_labels(report)
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
    if vi:
        date_text = quality['coverage_end'] or 'chưa xác định'
        summary = [f'Có {available}/{len(metrics)} chỉ số từ các truy vấn đã xác minh.',
                   f'Ngày chốt tồn kho: {date_text}. Số dư lấy tại ngày này.']
        summary.append('Đã đối chiếu với danh mục hiện tại. Không ghi nhận sản phẩm thiếu hoặc không khớp.'
                       if quality['partial_period'] is False and missing == 0 else
                       f'Cần kiểm tra {missing} sản phẩm còn thiếu hoặc không khớp.'
                       if missing is not None else
                       'Chưa xác minh được độ đầy đủ tại ngày chốt. Cần đối chiếu ngày chốt với danh mục sản phẩm.')
    actions = []
    for rule in report['decisions']:
        if rule['triggered'] is not True:
            continue
        key, flag = {'I01':('stockout_products','stockout'), 'I02':('reorder_products','reorder'), 'I03':('overstock_products','overstock')}.get(rule['id'],(None,None))
        why = (f"{display_value(metrics[key])} products carry the {flag} flag in the {date_text} snapshot. Flags are signals for review."
               if key else f'All three recorded flag counts are zero and catalog-relative coverage is verified for {date_text}.')
        if vi:
            flag_vi = {'stockout': 'hết hàng', 'reorder': 'cần đặt lại', 'overstock': 'tồn kho quá mức'}
            why = (f'{display_value(metrics[key])} sản phẩm có cờ {flag_vi[flag]} tại ngày {date_text}. Cần kiểm tra các cờ đã ghi nhận.'
                   if key else f'Ba loại cờ đều có số lượng bằng 0 và đã đối chiếu với danh mục hiện tại tại ngày {date_text}.')
        actions.append({'title':rule['title'], 'why':why, 'action':decision_text(rule, report),
                        'citations':list(dict.fromkeys(e['query_id'] for e in rule['evidence']))})
    insights = {'actions':actions, 'validation_summary':summary}
    if vi:
        insights['copy'] = INVENTORY_COPY_VI.copy()
        insights['data_notes'] = inventory_notes(report)
    return insights


def _sales_limitation_vi(note):
    if note.startswith('Period-over-period comparison'):
        ranges = _COVERAGE_RANGE.findall(note)
        if len(ranges) == 2:
            coverage = ' '.join(f'Từ {start} đến trước {end}: {days}/{expected} ngày.'
                                for start, end, days, expected in ranges).replace('unknown', 'chưa rõ')
            return ('So sánh giữa các kỳ dựa trên tổng theo tháng dương lịch. Dữ liệu theo ngày dùng để kiểm tra độ đầy đủ. '
                    + coverage + ' Chưa đủ dữ liệu để tính thay đổi doanh thu toàn kỳ và đánh giá các quy tắc phụ thuộc vào phép so sánh đó. '
                    'Các quy tắc theo tháng dùng kỳ đối chiếu riêng. Doanh thu và lợi nhuận kỳ hiện tại vẫn có thể sử dụng.')
    key, separator, reason = note.partition(': ')
    if separator:
        if reason == 'access denied.':
            return f'{key}: Nguồn dữ liệu giới hạn quyền truy cập.'
        if reason == 'validated source query unavailable.':
            return f'{key}: Không lấy được dữ liệu từ truy vấn đã xác minh.'
        limit = re.fullmatch(r'chart reached the (\d+)-row SQL limit; additional categories may be omitted\.', reason)
        if limit:
            return f'{key}: Đã đạt giới hạn {limit[1]} dòng SQL. Có thể còn nhóm dữ liệu chưa hiển thị.'
    return _SALES_LIMITATIONS_VI.get(note, note)


def data_notes(report, *, include_currency=True):
    if report['report_type'] == 'inventory_operations':
        return inventory_notes(report)
    vi = uses_vietnamese_labels(report)
    notes = [CURRENCY_NOTE_VI if vi else CURRENCY_NOTE] if include_currency else []
    if any(w['x_dimension'] == 'period' and w['type'] != 'kpi_row'
           and len(calendar_rows(w, report['request'])) > len(w['data']) for w in report['dashboard']['widgets']):
        notes.append('Biểu đồ để trống các kỳ thiếu dữ liệu.' if vi else 'Unobserved calendar periods are shown as gaps, not zero values.')
    detailed = any(note.startswith('Period-over-period comparison') for note in report['data_quality']['limitations'])
    for note in report['data_quality']['limitations']:
        if note.startswith('Synthetic commerce'):
            notes.append('Dữ liệu thương mại mô phỏng. Doanh thu công ty và doanh thu từ hàng đã giao đến từ hai nguồn riêng.'
                         if vi else 'Synthetic commerce demonstration data. Company sales and delivered-order sales are independent sources.')
        elif note.startswith('Missing count describes') or detailed and note.startswith('Company daily coverage'):
            continue
        else:
            notes.append(_sales_limitation_vi(note) if vi else note)
    return notes


def inventory_source_name(source, *, vi=False):
    labels = {'commerce.inventory': 'Inventory records', 'commerce.products': 'Product catalog',
              'commerce.returns': 'Return records', 'commerce.orders': 'Order records',
              'commerce.shipments': 'Shipment records', 'commerce.reviews': 'Customer reviews'}
    names = []
    for name in source.split(', '):
        if name in labels:
            names.append(INVENTORY_COPY_VI[labels[name]] if vi else labels[name])
        else:
            name = name.replace('\\', '/').rsplit('/', 1)[-1]
            name = re.sub(r'\.(?:pdf|docx?|xlsx?|csv|md|txt)$', '', name, flags=re.I)
            names.append(re.sub(r'^\d{2}[_ -]+', '', name).replace('_', ' '))
    return ', '.join(names)


def inventory_display_value(metric):
    from core.agents.language import is_vietnamese
    suffixes = {'units': ' đơn vị', 'calendar_days': ' ngày', 'rating_1_to_5': ' / 5'} if is_vietnamese(metric['label']) else {
        'units': ' units', 'calendar_days': ' days', 'rating_1_to_5': ' / 5'}
    suffix = suffixes.get(metric['unit'], '')
    return display_value(metric) + (suffix if metric['value'] is not None else '')


def inventory_notes(report):
    vi = uses_vietnamese_labels(report)
    labels = {'snapshot': 'Inventory snapshot', 'coverage': 'Snapshot coverage',
              'inventory_flag_distribution': 'Flag distribution', 'stockout_product_table': 'Stockout product list',
              'inventory_snapshots': 'Snapshot history', 'returns': 'Returned orders',
              'shipments': 'Shipment duration', 'reviews': 'Review ratings'}
    notes = []
    for note in report['data_quality']['limitations']:
        if note.startswith(('Dashboard source [', 'Policy source [', 'Policy Evidence:')):
            continue
        if vi:
            note = _inventory_limitation_vi(note, report, labels)
            if note not in notes:
                notes.append(note)
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
            reason = reasons.get(metric['status'], 'Unavailable for this scope or source.')
            notes.append(metric['label'] + ': ' + (INVENTORY_COPY_VI[reason] if vi else reason))
    return notes


def _inventory_limitation_vi(note, report, labels):
    if note.startswith('Selected snapshot:'):
        snapshot = report['data_quality']['coverage_end']
        if not snapshot:
            return 'Ngày chốt tồn kho: chưa tìm thấy bản ghi được cấp quyền trước khi kết thúc kỳ.'
        suffix = 'Ngày chốt này trước kỳ yêu cầu.' if snapshot < report['request']['period']['start'] else 'Ngày chốt này nằm trong kỳ yêu cầu.'
        return f'Ngày chốt tồn kho: {snapshot}. {suffix}'
    prefixes = {
        'Synthetic commerce': 'Dữ liệu thương mại mô phỏng. Chưa xác minh được độ đầy đủ của dữ liệu giao dịch và danh mục theo từng thời điểm. Báo cáo không suy ra dự báo, cam kết dịch vụ, lượng đặt lại hay nguyên nhân.',
        'Snapshot policy:': 'Số dư lấy từ một ngày chốt quan sát được trước khi kết thúc kỳ. Ngày chốt cũ được đánh dấu. Biểu đồ lịch sử hiển thị từng ngày chốt riêng.',
        'days_of_supply': 'Số ngày đủ hàng, tỷ lệ đáp ứng và tỷ lệ bán hết chưa được xác minh định nghĩa từ nguồn.',
        'fill_rate': 'Số ngày đủ hàng, tỷ lệ đáp ứng và tỷ lệ bán hết chưa được xác minh định nghĩa từ nguồn.',
        'stockout/reorder/overstock': 'Các cờ hết hàng, cần đặt lại và tồn kho quá mức có thể trùng nhau. Số sản phẩm được tính riêng theo từng cờ.',
        'Inventory snapshot selection query unavailable.': 'Chưa xác minh được ngày chốt từ dữ liệu tồn kho hiện có.',
        'No warehouse, supplier, supplier lead time, SLA, forecast, or purchase order data':
            'Nguồn không có dữ liệu kho, nhà cung cấp, thời gian giao của nhà cung cấp, cam kết dịch vụ, dự báo hoặc đơn mua hàng.',
    }
    for prefix, translated in prefixes.items():
        if note.startswith(prefix):
            return translated
    if note.startswith('Snapshot completeness'):
        return ('Độ đầy đủ tại ngày chốt được đối chiếu với danh mục hiện tại. '
                'Thành phần danh mục trong quá khứ chưa được xác minh.')
    key, _, detail = note.partition(': ')
    metric = next((m for m in report['metrics'] if m['id'] == key), None)
    if metric and detail.startswith('not_available'):
        return f'{metric["label"]}: không có dữ liệu cho nhóm đã chọn.'
    if key in labels:
        label = INVENTORY_COPY_VI[labels[key]]
        if 'access denied' in detail:
            return f'{label}: quyền truy cập nguồn bị giới hạn.'
        if 'validated source query unavailable' in detail:
            return f'{label}: chưa truy xuất hoặc xác minh được nguồn.'
        limit = re.search(r'(\d+)-row', detail)
        if limit:
            return f'{label}: hiển thị {limit[1]} dòng đầu tiên. Có thể còn bản ghi chưa hiển thị.'
    return note
