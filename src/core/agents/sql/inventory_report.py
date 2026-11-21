"""Fixed inventory SQL, using the existing SQL allowlist and requester boundary."""
from datetime import date
import hashlib

from core.agents.sql.sales_report import query, numeric


async def latest(agent, request):
    rows, _ = await query(agent, request, 'SELECT MAX(i.snapshot_date) AS snapshot_date FROM commerce.inventory AS i LIMIT 1')
    return rows[0]['snapshot_date'] if rows else None


def plans(scope, snapshot):
    from core.agents.report.inventory_operations import load_contract
    supported = load_contract()['supported_request']
    if scope['dimension'] not in supported['dimensions'] or scope['granularity'] not in supported['granularities']:
        raise ValueError('Unsupported inventory scope')
    start, end = (date.fromisoformat(scope['period'][k]) for k in ('start', 'end_exclusive'))
    if start >= end or start.day != 1 or end.day != 1 or (end.year-start.year)*12+end.month-start.month > 200:
        raise ValueError('Inventory reports require calendar periods of up to 200 months')
    dimension, value = scope['dimension'], scope['dimension_value']
    if value is not None and (dimension == 'all' or not isinstance(value, str) or not 1 <= len(value) <= 100):
        raise ValueError('Invalid inventory dimension filter')
    if dimension == 'product' and value is not None:
        if not value.isascii() or not value.isdigit() or not 0 < int(value) <= 2147483647:
            raise ValueError('Product filters require a quoted numeric product ID')
        value = int(value)
    expression = {'category': 'p.category', 'segment': 'p.segment', 'product': 'p.product_id', 'all': "'all'"}[dimension]
    def filtered(args):
        return (' AND ' + expression + f' = ${len(args)+1}', (*args, value)) if value is not None else ('', args)
    point_filter, point_args = filtered((snapshot,))
    period_filter, period_args = filtered((start, end))
    join = ' FROM commerce.inventory AS i LEFT JOIN commerce.products AS p ON i.product_id = p.product_id'
    where = ' WHERE i.snapshot_date = $1' + point_filter
    flag = lambda field: f'CASE WHEN COUNT(i.{field}) = COUNT(i.product_id) THEN COUNT(*) FILTER (WHERE i.{field} = TRUE) END'
    stockout = flag('stockout_flag')
    totals = ('SELECT COUNT(DISTINCT i.product_id) AS observed_products, COUNT(i.product_id) AS source_count, '
              'CASE WHEN COUNT(i.stock_on_hand) = COUNT(i.product_id) THEN SUM(i.stock_on_hand) END AS stock_on_hand, '
              f'{stockout} AS stockout_products, '
              f'100.0 * ({stockout}) / NULLIF(COUNT(DISTINCT i.product_id),0) AS stockout_flag_pct, '
              f"{flag('overstock_flag')} AS overstock_products, {flag('reorder_flag')} AS reorder_products, "
              'COUNT(*) FILTER (WHERE p.product_id IS NULL) AS unmatched_count' + join + where + ' LIMIT 1')
    coverage = ('SELECT COUNT(DISTINCT p.product_id) AS catalog_count, COUNT(DISTINCT p.product_id) FILTER (WHERE i.product_id IS NULL) AS missing_count '
                'FROM commerce.products AS p LEFT JOIN commerce.inventory AS i ON i.product_id = p.product_id AND i.snapshot_date = $1 '
                'WHERE TRUE' + point_filter + ' LIMIT 1')
    flag_distribution = ('SELECT p.category AS category, ' + ', '.join(
        f'{flag(field)} AS {identifier}' for field, identifier in (
            ('stockout_flag', 'stockout_products'), ('overstock_flag', 'overstock_products'), ('reorder_flag', 'reorder_products')))
        + join + where + ' GROUP BY p.category ORDER BY p.category LIMIT 200')
    trend = (f'SELECT i.snapshot_date AS snapshot_date, {stockout} AS stockout_products' + join +
             ' WHERE i.snapshot_date >= $1 AND i.snapshot_date < $2' + period_filter +
             ' GROUP BY i.snapshot_date ORDER BY i.snapshot_date LIMIT 200')
    reviews = ('SELECT AVG(r.rating) AS avg_review_rating, COUNT(r.rating) AS source_count '
               'FROM commerce.reviews AS r LEFT JOIN commerce.products AS p ON r.product_id = p.product_id '
               'WHERE r.review_date >= $1 AND r.review_date < $2' + period_filter + ' LIMIT 1')
    return {
        'snapshot': (totals, point_args) if snapshot is not None else None,
        'coverage': (coverage, point_args) if snapshot is not None else None,
        'inventory_flag_distribution': (flag_distribution, point_args) if snapshot is not None else None,
        'stockout_product_table': ('SELECT i.product_id AS product, ' + stockout + ' AS stockout_products' +
                                  join + where + ' AND i.stockout_flag = TRUE GROUP BY i.product_id ORDER BY i.product_id LIMIT 200', point_args) if snapshot is not None else None,
        'inventory_snapshots': (trend, period_args),
        'returns': ('SELECT COUNT(DISTINCT r.order_id) AS returned_order_count, COUNT(r.order_id) AS source_count '
                    'FROM commerce.returns AS r WHERE r.return_date >= $1 AND r.return_date < $2 LIMIT 1', (start, end)) if dimension == 'all' else None,
        'shipments': ('SELECT AVG(s.delivery_date - s.ship_date) AS avg_delivery_days, COUNT(s.delivery_date) AS source_count '
                      'FROM commerce.shipments AS s JOIN commerce.orders AS o ON s.order_id = o.order_id '
                      'WHERE s.ship_date >= $1 AND s.ship_date < $2 AND s.delivery_date IS NOT NULL LIMIT 1', (start, end)) if dimension == 'all' else None,
        'reviews': (reviews, period_args) if dimension in {'all', 'category', 'product'} else None,
    }


async def run(agent, request, scope):
    from core.agents.report.inventory_operations import load_contract
    agent._authorize(request)
    # Validate before the selection query. Date selection is global, never per SKU/category.
    plans(scope, None)
    limitations = ['Synthetic commerce demo data. Transaction coverage and historical catalog membership are unverified. '
                    'No demand forecasts, lead times, reorder quantities, SLA thresholds or causal claims are inferred.',
                    'Snapshot policy: latest observed snapshot strictly before end_exclusive for month, quarter and year; '
                    'older snapshots may be carried forward and are explicitly marked stale. Snapshot trends count each date independently.']
    limitations.extend(load_contract()['report_specific_rules']['known_issues'])
    outcomes = {}

    async def execute(key, plan):
        if plan is None:
            outcomes[key] = {'rows': [], 'status': 'not_available', 'evidence': []}
            return
        sql, args = plan
        try:
            rows, sources = await query(agent, request, sql, args)
            filters = {**scope, **({'snapshot_date': snapshot.isoformat()} if key in {'snapshot', 'coverage', 'inventory_flag_distribution', 'stockout_product_table'} else {})}
            outcomes[key] = {'rows': rows, 'status': 'available', 'evidence': [{
                'source_table': ', '.join(sorted(sources)), 'query_id': hashlib.sha256((sql+repr(args)).encode()).hexdigest()[:16],
                'filters': filters, 'row_count': len(rows), 'document_id': None, 'citation': None}]}
        except PermissionError:
            outcomes[key] = {'rows': [], 'status': 'access_denied', 'evidence': []}
            limitations.append(key + ': access denied.')
        except Exception:
            outcomes[key] = {'rows': [], 'status': 'not_available', 'evidence': []}
            limitations.append(key + ': validated source query unavailable.')

    snapshot = None
    selection_status = 'not_available'
    try:
        end = date.fromisoformat(scope['period']['end_exclusive'])
        rows, _ = await query(agent, request, 'SELECT MAX(i.snapshot_date) AS snapshot_date FROM commerce.inventory AS i WHERE i.snapshot_date < $1 LIMIT 1', (end,))
        snapshot = rows[0]['snapshot_date'] if rows else None
        selection_status = 'available'
    except PermissionError:
        selection_status = 'access_denied'
    except Exception:
        limitations.append('Inventory snapshot selection query unavailable.')
    for key, plan in plans(scope, snapshot).items():
        await execute(key, plan)
    if snapshot is None:
        limitations.append('Selected snapshot: unavailable; no authorized observed snapshot could be selected before the reporting cutoff.')
        outcomes['snapshot']['status'] = selection_status if selection_status != 'available' else 'not_available'
    else:
        limitations.append(f'Selected snapshot: {snapshot.isoformat()}. ' + ('Stale: predates the requested period.' if snapshot < date.fromisoformat(scope['period']['start']) else 'Observed within the requested period.'))
    metrics = {}
    for definition in load_contract()['metrics']:
        key = 'snapshot' if definition['grain'] == 'snapshot' else {'returned_order_count':'returns', 'avg_delivery_days':'shipments', 'avg_review_rating':'reviews'}[definition['id']]
        outcome = outcomes[key]
        row = (outcome['rows'] or [{}])[0]
        supported = scope['dimension'] in definition['allowed_dimensions']
        value = numeric(row.get(definition['id'])) if supported and row.get('source_count') else None
        status = 'available' if value is not None else outcome['status'] if supported else 'not_available'
        if value is None and status == 'available':
            status = 'no_data' if not row.get('source_count') else 'not_available'
        metrics[definition['id']] = {'value': value, 'status': status,
                                     'evidence': outcome['evidence'] if supported and (key != 'snapshot' or snapshot is not None) else []}
        if key == 'snapshot' and snapshot is not None:
            metrics[definition['id']]['evidence'] = [*metrics[definition['id']]['evidence'], *outcomes['coverage']['evidence']]
        if not supported:
            limitations.append(definition['id'] + ': not_available for dimension ' + scope['dimension'] + '; no approximation applied.')
    row = (outcomes['snapshot']['rows'] or [{}])[0]
    coverage = (outcomes['coverage']['rows'] or [{}])[0]
    missing = coverage.get('missing_count')
    unmatched = row.get('unmatched_count')
    count = missing + unmatched if missing is not None and unmatched is not None else None
    complete = (snapshot is not None and snapshot >= date.fromisoformat(scope['period']['start'])
                and count == 0 and coverage.get('catalog_count', 0) > 0
                and coverage.get('catalog_count') == row.get('source_count') == row.get('observed_products')
                and all(metrics[k]['status'] == 'available' for k in ('stockout_products', 'overstock_products', 'reorder_products')))
    limitations.append('Snapshot completeness is relative to the authorized current product catalog; historical membership is not certified. '
                        + ('Catalog-relative coverage verified.' if complete else 'Complete snapshot coverage is unverified or incomplete; I04 is withheld.'))
    datasets = {}
    for key in ('inventory_flag_distribution', 'stockout_product_table', 'inventory_snapshots'):
        datasets[key] = [{k: v.isoformat() if isinstance(v, date) else numeric(v) if k not in {'category', 'product'} else str(v) if v is not None else None
                          for k, v in record.items()} for record in outcomes[key]['rows']]
        if len(datasets[key]) == 200:
            limitations.append(key + ': reached the 200-row SQL cap; additional rows may be omitted.')
        for evidence in outcomes[key]['evidence']:
            limitations.append(f"Dashboard source [{evidence['query_id']}] {key}: {evidence['source_table']}; {evidence['row_count']} result rows; "
                               + ('selected snapshot ' + snapshot.isoformat() if key != 'inventory_snapshots' and snapshot else 'independent snapshots in requested period') + '.')
    sources_complete = all(outcome['status'] == 'available' for outcome in outcomes.values()) and all(len(rows) < 200 for rows in datasets.values())
    return {'metrics': metrics, 'datasets': datasets, 'sources_complete': sources_complete, 'data_quality': {
        'coverage_start': snapshot.isoformat() if snapshot else None, 'coverage_end': snapshot.isoformat() if snapshot else None,
        'partial_period': not complete if snapshot else None, 'missing_or_unmatched_count': count, 'limitations': limitations}}
