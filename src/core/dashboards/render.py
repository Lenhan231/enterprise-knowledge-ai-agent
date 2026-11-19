"""Trusted HTML templates: model output is data, never executable markup."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from datetime import datetime
from html import escape
import math
import re
from statistics import mean
from sqlglot import parse_one, exp
from sqlglot.optimizer.scope import build_scope

from core.agents.dashboard_agent import build_chart, _unit
from core.analytics.join_validation import column_origin
from core.dashboards.formatting import format_number, format_datetime, format_value, axis_date

CSP = "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'"
COLORS = ['#117b70', '#4361b2', '#b66a16', '#974e93', '#c23b51', '#657a13']


def text(value):
    return escape(str(value if value is not None else '—'), quote=True)


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(Decimal(str(value)))
        return result if math.isfinite(result) else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def formatted(value, **options):
    return format_number(value, **options)


def display_context(payload):
    rows, metadata = payload.get('rows') or [], payload.get('metadata') or {}
    currency_source = False
    try:
        expression = parse_one(payload.get('sql') or '', read='postgres')
        projections = {item.alias_or_name: item.unalias() for item in expression.expressions}
        column = projections.get('currency')
        scope = build_scope(expression)
        if isinstance(column, exp.Column) and scope:
            if not column.table and len(scope.sources) == 1:
                column = column.copy()
                column.set('table', exp.to_identifier(next(iter(scope.sources))))
            currency_source = column_origin(scope, column) == ('commerce.invoices', 'currency')
    except Exception:
        projections = {}
    units = {key: _unit(key, projections.get(key), metadata) for row in rows for key in row}
    currencies = {row.get('currency') for row in rows}
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    if not currency_source or not isinstance(currency, str) or not re.fullmatch(r'[A-Z]{3}', currency):
        currency = None
    return units, currency


def table(rows, *, units=None, currency=None, dimension=None):
    def cell(key, value):
        identifier = key.endswith('_id') or key in {'zip', 'year', 'fiscal_year', 'currency', 'product_name', 'category', 'segment'} or key == dimension
        if identifier and not isinstance(value, datetime) and not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[T ].*)?', str(value)):
            return text(value)
        unit = (units or {}).get(key)
        return text(format_value(value, unit=unit, currency=currency if unit and unit.startswith('currency') else None))
    names = list(dict.fromkeys(key for row in rows for key in row))[:20]
    return '<div class="table"><table><thead><tr>' + ''.join(f'<th>{text(k)}</th>' for k in names) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join(f'<td>{cell(k, row.get(k))}</td>' for k in names) + '</tr>' for row in rows[:200]) + '</tbody></table></div>'


def chart_svg(chart, *, currency=None, granularity=None):
    labels, series = chart.categories, chart.series
    values = [value for s in series for value in s.values if value is not None]
    if not values:
        return '<p class="notice">No matching chart observations.</p>'
    shown = lambda value: formatted(value, unit=chart.unit, currency=currency if chart.unit.startswith('currency') or chart.unit in {'VND', 'USD', 'EUR'} else None)
    granularity = granularity or 'day'
    label_text = lambda label: axis_date(label, granularity) if chart.temporal else label
    low, high = min(0, min(values)), max(0, max(values))
    magnitude = max(abs(low), abs(high), 1)
    scale = high / magnitude - low / magnitude or 1
    y = lambda value: 235 - (value / magnitude - low / magnitude) / scale * 205
    display_unit = currency if currency and chart.unit.startswith('currency') else 'percent' if chart.unit.startswith('fraction') else chart.unit
    out = [f'<svg viewBox="0 0 640 290" role="img" aria-label="{text(chart.title)}">',
           f'<title>{text(chart.title)} · {text(display_unit)}</title>']
    if chart.type == 'donut':
        total = sum(series[0].values)
        offset = 0
        for i, (label, value) in enumerate(zip(labels, series[0].values)):
            fraction = value / total
            out.append(f'<circle cx="220" cy="140" r="85" fill="none" stroke="{COLORS[i % len(COLORS)]}" stroke-width="48" pathLength="100" stroke-dasharray="{fraction * 100} {100 - fraction * 100}" stroke-dashoffset="{-offset}" transform="rotate(-90 220 140)"><title>{text(label_text(label))}: {text(shown(value))} ({text(formatted(fraction*100, unit="percent"))})</title></circle>')
            offset += fraction * 100
        out.append(f'<text x="220" y="145" text-anchor="middle">{text(shown(total))}</text>')
    else:
        left = max(45, min(150, max(len(shown(value)) for value in (low, high))*5+14))
        width = (610-left) / max(1, len(labels))
        positions = [left + width * (j + .5) for j in range(len(labels))]
        if chart.type == 'line' and chart.temporal:
            dates = [datetime.fromisoformat(label if len(label) > 4 else label + '-01-01') for label in labels]
            duration = (dates[-1] - dates[0]).total_seconds() or 1
            positions = [left + (date - dates[0]).total_seconds() / duration * (610-left) for date in dates]
        out.append(f'<path d="M{left} {y(0):.2f}H610" stroke="#94a3b8"/>')
        for i, s in enumerate(series):
            previous = None
            for j, value in enumerate(s.values):
                if value is None:
                    previous = None
                    continue
                x = positions[j]
                title = f'<title>{text(label_text(labels[j]))} · {text(s.name)}: {text(shown(value))}</title>'
                if chart.type == 'bar':
                    bar_width = max(.1, width * .8 / len(series))
                    bar_left = x - width * .4 + i * bar_width
                    out.append(f'<rect x="{bar_left:.2f}" y="{min(y(0), y(value)):.2f}" width="{bar_width:.2f}" height="{max(.5, abs(y(value)-y(0))):.2f}" fill="{COLORS[i]}">{title}</rect>')
                else:
                    if previous is not None:
                        out.append(f'<path d="M{previous[0]:.2f} {previous[1]:.2f}L{x:.2f} {y(value):.2f}" stroke="{COLORS[i]}" stroke-width="2" fill="none"/>')
                    out.append(f'<circle cx="{x:.2f}" cy="{y(value):.2f}" r="3" fill="{COLORS[i]}">{title}</circle>')
                    previous = (x, y(value))
        step = max(1, math.ceil(len(labels) / 6))
        for j in range(0, len(labels), step):
            out.append(f'<text x="{positions[j]:.2f}" y="265" text-anchor="middle" font-size="11">{text(label_text(labels[j])[:24])}</text>')
        for value in (low, high):
            out.append(f'<text x="3" y="{y(value):.2f}" font-size="10">{text(shown(value))}</text>')
    out.append('</svg>')
    if chart.type == 'donut':
        out.append('<p>' + ' · '.join(f'<span style="color:{COLORS[i % len(COLORS)]}">{text(label_text(label))}: {text(shown(value))}</span>' for i,(label,value) in enumerate(zip(labels,series[0].values))) + '</p>')
    else:
        out.append('<p>' + ' · '.join(f'<span style="color:{COLORS[i]}">{text(s.name)}</span>' for i, s in enumerate(series)) + '</p>')
    return ''.join(out) + f'<small>{text(display_unit)} · Display values are rounded; original observations remain in the saved data.</small>'


def _tile_content(tile, result, *, include_observations=True, chart=None):
    if not result or result.status not in {'complete', 'empty'}:
        return f'<p class="notice">{text(result.message if result else "Source unavailable")}</p>'
    rows = result.payload.get('rows') or []
    if not rows:
        return '<p class="notice">No matching observations. This is not a zero value.</p>'
    names = list(rows[0])
    units, currency = display_context(result.payload)
    measures = tile.measures or [key for key in names if any(number(row.get(key)) is not None for row in rows) and key != tile.dimension]
    if any(key not in names for key in [*measures, *([tile.dimension] if tile.dimension else [])]):
        raise ValueError('Selected fields are unavailable. Edit this tile.')
    if tile.kind == 'kpi':
        if len(rows) != 1 or len(measures) != 1:
            raise ValueError('A KPI needs one aggregate row and one measure; showing observations.')
        value = number(rows[0].get(measures[0]))
        unit = units.get(measures[0])
        shown = formatted(Decimal(str(rows[0][measures[0]])), unit=unit, currency=currency if unit and unit.startswith('currency') else None) if value is not None else 'No observed value'
        return f'<p class="kpi">{shown}</p><p>{text(measures[0])}</p>'
    if tile.kind == 'summary':
        items = []
        for key in measures:
            values = [number(row.get(key)) for row in rows]
            observed = [value for value in values if value is not None]
            if observed:
                options = {'unit': units.get(key), 'currency': currency if (units.get(key) or '').startswith('currency') else None}
                items.append(f'<li>{text(key)}: {formatted(len(observed), unit="count")} observed; min {formatted(min(observed), **options)}; max {formatted(max(observed), **options)}; mean {formatted(mean(observed), **options)}</li>')
        if not items:
            raise ValueError('No numeric observations are available for this summary.')
        return '<p>Descriptive statistics of returned observations only.</p><ul>' + ''.join(items) + '</ul>'
    if tile.kind == 'table':
        return table([{key: row.get(key) for key in names if not tile.measures or key in {*measures, tile.dimension}} for row in rows], units=units, currency=currency, dimension=tile.dimension)
    try:
        payload = deepcopy(result.payload)
        if tile.dimension:
            payload['rows'] = [{key: row.get(key) for key in [tile.dimension, *measures]} for row in rows]
        for row in payload['rows']:
            for key in measures:
                if key in row and row[key] is not None and number(row[key]) is not None:
                    row[key] = number(row[key])
        contract = payload.get('metadata', {}).get('request_contract')
        if contract:
            contract.pop('charts', None)
            contract['chart_type'] = tile.kind
        chart = chart or build_chart(payload, f'{tile.kind} chart')
        if chart.unit in {'VND', 'USD', 'EUR'} and currency is None:
            chart = chart.model_copy(update={'unit': 'currency (unconfirmed)'})
        chart.title = tile.title
        observations = '<details><summary>Source observations</summary>' + table(rows, units=units, currency=currency, dimension=tile.dimension) + '</details>' if include_observations else ''
        grain = re.search(r"DATE_TRUNC\(\s*'(day|month|quarter|year)'", payload.get('sql') or '', re.I)
        dimension_grain = tile.dimension if tile.dimension in {'month','quarter','year'} else None
        return chart_svg(chart, currency=currency, granularity=grain[1].lower() if grain else dimension_grain) + observations
    except ValueError as error:
        raise ValueError('Chart unavailable: ' + str(error)) from error


def tile_presentation(tile, result, *, include_observations=True, chart=None):
    if not result or result.status not in {'complete', 'empty'}:
        message = result.message if result and result.message else 'Source unavailable'
        return f'<p class="notice">{text(message)}</p>', 'unavailable', message
    try:
        html = _tile_content(tile, result, include_observations=include_observations, chart=chart)
        return html, 'complete' if result.payload.get('rows') else 'empty', ''
    except ValueError as error:
        message = str(error)
        units, currency = display_context(result.payload)
        return f'<p class="notice">{text(message)}</p>' + table(result.payload.get('rows') or [], units=units, currency=currency, dimension=tile.dimension), 'unavailable', message


def tile_content(tile, result):
    return tile_presentation(tile, result)[0]


def render_dashboard(document, *, charts=None, saved=True):
    results = {result.id: result for result in document.results}
    tiles, observed = [], set()
    for tile in document.tiles:
        content, status, _ = tile_presentation(tile, results.get(tile.query_id), include_observations=tile.query_id not in observed, chart=(charts or {}).get(tile.id))
        tiles.append(f'<article class="span-{tile.span}"><h2>{text(tile.title)}</h2>{content}<small>Dataset: {text(tile.query_id)}</small></article>')
        if tile.kind in {'line', 'bar', 'donut', 'table'} and status == 'complete':
            observed.add(tile.query_id)
    tiles = ''.join(tiles)
    sources = []
    represented = {tile.query_id for tile in document.tiles if tile.kind in {'line', 'bar', 'donut', 'table'}}
    for result in document.results:
        parameters = ', '.join(str(value) for value in result.payload.get('parameters', [])) or 'None'
        evidence = f'<details><summary>{text(result.id)} · {text(result.status)}</summary><p>{text(result.question)}</p><p>{text(result.message)}</p><p>Error type: {text(result.payload.get("metadata", {}).get("error_type", "None reported"))}</p><pre>{text(result.payload.get("sql") or result.payload.get("attempted_sql") or "SQL text unavailable")}</pre><pre>{text(parameters)}</pre><p>{text(result.payload.get("metadata", {}).get("limitations", []))}</p>'
        if result.id not in represented and result.payload.get('rows'):
            units, currency = display_context(result.payload)
            evidence += '<details><summary>Source observations</summary>' + table(result.payload['rows'], units=units, currency=currency) + '</details>'
        sources.append(evidence + '</details>')
    sources = ''.join(sources)
    label = f'SQL-backed business dashboard · {text(document.status)} · Revision {formatted(document.revision, unit="count")}' if saved else f'Live SQL overview · {text(document.status)}'
    timestamps = f'Data refreshed {text(format_datetime(document.data_updated_at))}.' + (f' Saved {text(format_datetime(document.updated_at))}.' if saved else '')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{escape(CSP, quote=True)}"><title>{text(document.title)}</title>
<style>body{{margin:0;background:#f2f5f7;color:#172d36;font:15px system-ui,sans-serif;padding:30px}}header,main,footer{{max-width:1300px;margin:auto}}h1{{font-size:32px;letter-spacing:-1px}}h2{{font-size:19px}}main{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}}article{{background:white;border:1px solid #d9e2e7;border-radius:14px;padding:22px;min-width:0}}.span-2{{grid-column:span 2}}.kpi{{font-size:42px;font-weight:700;margin:16px 0;color:#117b70}}small{{color:#526774}}svg{{width:100%;max-height:350px}}.table{{overflow:auto;max-height:380px}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #e4e9ed;white-space:nowrap}}details{{margin:14px 0}}summary{{cursor:pointer}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.notice{{color:#84510a}}footer{{margin-top:24px}}@media(max-width:700px){{body{{padding:15px}}main{{grid-template-columns:1fr}}.span-2{{grid-column:span 1}}}}</style></head>
<body><header><small>{label}</small><h1>{text(document.title)}</h1><p>{text(document.description)}</p><p>Scope: {text(document.scope or 'As specified in source questions')}</p><p><small>{timestamps}</small></p></header><main>{tiles}</main><footer><h2>Sources and limitations</h2><p>Charts and statistics describe returned SQL observations. Missing values are unknown. Currency is unconfirmed unless the source explicitly identifies it.</p>{sources}</footer></body></html>'''
