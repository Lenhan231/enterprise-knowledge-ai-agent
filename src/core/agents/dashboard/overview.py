"""Ephemeral overview from fixed, authorized SQL; no model or saved-artifact writes."""
import asyncio
from datetime import date, datetime

from core.agents.sql.agent import SQLAnalyticsAgent
from core.agents.sql.sales_report import query, numeric
from core.agents.dashboard.models import DashboardDocument, QuerySpec, QueryResult, TileSpec, MAX_CONCURRENT_QUERIES, now
from core.agents.dashboard.formatting import format_value
from core.models.agents import ChartSpec, ChartSeries

SNAPSHOT_SQL = 'SELECT MAX(i.snapshot_date) AS snapshot_date FROM commerce.inventory AS i LIMIT 1'
OVERVIEW_QUERIES = {
    'stock': """WITH ranked AS (
        SELECT i.product_id, p.product_name, i.stock_on_hand,
        RANK() OVER (ORDER BY i.stock_on_hand DESC NULLS LAST, i.product_id) AS position
        FROM commerce.inventory AS i LEFT JOIN commerce.products AS p ON i.product_id = p.product_id
        WHERE i.snapshot_date = $1)
        SELECT CASE WHEN r.position <= 5 THEN r.product_id END AS product_id,
        CASE WHEN r.position <= 5 THEN r.product_name ELSE 'Other products' END AS product_name,
        CASE WHEN COUNT(r.stock_on_hand) = COUNT(*) THEN SUM(r.stock_on_hand) END AS stock_on_hand,
        COUNT(*) FILTER (WHERE r.stock_on_hand IS NULL OR r.stock_on_hand < 0) AS invalid_balances
        FROM ranked AS r GROUP BY 1, 2 ORDER BY stock_on_hand DESC NULLS LAST, product_id LIMIT 6""",
    'purchases': """SELECT p.category AS category, SUM(oi.quantity) AS units_purchased
        FROM commerce.order_items AS oi JOIN commerce.orders AS o ON oi.order_id = o.order_id
        LEFT JOIN commerce.products AS p ON oi.product_id = p.product_id
        WHERE o.order_status = 'delivered' GROUP BY p.category
        ORDER BY units_purchased DESC NULLS LAST, p.category LIMIT 10""",
    'sales': """SELECT DATE_TRUNC('month', s.date)::date AS month, SUM(s.revenue) AS revenue
        FROM commerce.sales AS s GROUP BY 1 ORDER BY 1 DESC LIMIT 12""",
}


async def build_overview(agent, request):
    SQLAnalyticsAgent._authorize(request)
    specs = [QuerySpec(id=key, question=question) for key, question in (
        ('stock', 'Top five products by stock on hand at the latest observed snapshot, with all remaining products grouped as Other products.'),
        ('purchases', 'Top ten categories by delivered item quantity across available order history.'),
        ('sales', 'Company revenue for the latest twelve observed calendar months; source currency is unconfirmed.'))]
    tiles = [TileSpec(id=key, query_id=key, title=title, kind=kind, dimension=dimension, measures=[measure], span=span)
             for key, title, kind, dimension, measure, span in (
        ('stock', 'Product stock share', 'donut', 'product_name', 'stock_on_hand', 1),
        ('purchases', 'What customers buy most', 'bar', 'category', 'units_purchased', 1),
        ('sales', 'Monthly company revenue', 'line', 'month', 'revenue', 2))]
    snapshot, snapshot_error = None, None
    try:
        rows, _ = await query(agent, request, SNAPSHOT_SQL)
        snapshot = rows[0]['snapshot_date'] if rows else None
        if isinstance(snapshot, str):
            snapshot = date.fromisoformat(snapshot)
    except Exception:
        snapshot_error = 'The latest inventory snapshot could not be verified.'
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_QUERIES)

    async def execute(spec, tile):
        parameters = (snapshot,) if spec.id == 'stock' else ()
        if spec.id == 'stock' and snapshot is None:
            return QueryResult(id=spec.id, question=spec.question, status='failed', message=snapshot_error or 'No observed inventory snapshot is available.'), None
        sql = OVERVIEW_QUERIES[spec.id]
        payload = {'sql': sql, 'parameters': [v.isoformat() if isinstance(v, date) else v for v in parameters],
                   'rows': [], 'metadata': {'limitations': [spec.question]}}
        try:
            async with semaphore:
                rows, sources = await query(agent, request, sql, parameters)
            if spec.id == 'sales':
                rows = sorted(rows, key=lambda row: row['month'])
            payload['rows'] = [{key: value.isoformat() if isinstance(value, (date, datetime)) else value for key, value in row.items()} for row in rows]
            unit = 'currency (unconfirmed)' if spec.id == 'sales' else 'units'
            payload['metadata'].update(source=sorted(sources), columns=[{'name':tile.measures[0], 'unit':unit}])
            if not rows:
                return QueryResult(id=spec.id, question=spec.question, status='empty', payload=payload), None
            if spec.id == 'stock' and any(row['invalid_balances'] for row in rows):
                raise ValueError('Stock share is unavailable because the selected snapshot contains missing or negative balances.')
            values = [numeric(row.get(tile.measures[0])) for row in rows]
            if not any(value is not None for value in values):
                raise ValueError('No numeric observations are available for this source.')
            if spec.id == 'stock' and (any(value is None or value < 0 for value in values) or sum(values) <= 0):
                raise ValueError('Stock shares require known, nonnegative balances and a positive total; no share can be inferred for this snapshot.')
            if spec.id == 'stock':
                labels = [f"{row.get('product_name') or 'Product'} (#{row['product_id']})" if row['product_id'] is not None else 'Other products' for row in rows]
            else:
                labels = [str(row.get(tile.dimension)) if row.get(tile.dimension) is not None else 'Unknown category' for row in rows]
            chart = ChartSpec(type=tile.kind, title=tile.title, categories=labels,
                series=[ChartSeries(name=tile.measures[0].replace('_', ' ').title(), values=values)],
                unit=unit, x_label=tile.dimension, y_label=unit, temporal=spec.id == 'sales')
            return QueryResult(id=spec.id, question=spec.question, status='complete', payload=payload), chart
        except ValueError as error:
            return QueryResult(id=spec.id, question=spec.question, status='failed', payload=payload, message=str(error)), None
        except Exception:
            return QueryResult(id=spec.id, question=spec.question, status='failed', payload=payload,
                               message='This overview source is unavailable. Other charts remain independent.'), None

    outcomes = await asyncio.gather(*(execute(spec, tile) for spec, tile in zip(specs, tiles)))
    results = [result for result, _ in outcomes]
    charts = {tile.id: chart for tile, (_, chart) in zip(tiles, outcomes) if chart is not None}
    refreshed = now()
    document = DashboardDocument(title='Business overview',
        description='Observed inventory, delivered purchases and company revenue. Synthetic commerce data; no currency is assumed.',
        scope=f"Inventory snapshot: {format_value(snapshot) if snapshot else 'unavailable'}. Purchases: available delivered-order history. Revenue: latest 12 observed months. Source completeness is unverified.",
        queries=specs, tiles=tiles, results=results, data_updated_at=refreshed, updated_at=refreshed,
        status='complete' if len(charts) == 3 else 'partial' if charts else 'failed',
        tile_status={tile.id:{'status':result.status, 'message':result.message} for tile, result in zip(tiles,results)})
    return document, charts
