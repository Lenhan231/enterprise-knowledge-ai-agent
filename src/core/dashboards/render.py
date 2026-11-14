"""Trusted HTML templates: model output is data, never executable markup."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from datetime import datetime
from html import escape
import math
from statistics import mean

from core.agents.dashboard_agent import build_chart

CSP = "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'"
COLORS = ['#117b70', '#4361b2', '#b66a16', '#974e93']


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


def formatted(value):
    if value and abs(value) < .000001:
        return f'{value:.6g}'
    return f'{value:,.6f}'.rstrip('0').rstrip('.')


def table(rows):
    names = list(dict.fromkeys(key for row in rows for key in row))[:20]
    return '<div class="table"><table><thead><tr>' + ''.join(f'<th>{text(k)}</th>' for k in names) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join(f'<td>{text(row.get(k))}</td>' for k in names) + '</tr>' for row in rows[:200]) + '</tbody></table></div>'


def chart_svg(chart):
    labels, series = chart.categories, chart.series
    values = [value for s in series for value in s.values if value is not None]
    low, high = min(0, min(values)), max(0, max(values))
    magnitude = max(abs(low), abs(high), 1)
    scale = high / magnitude - low / magnitude or 1
    y = lambda value: 235 - (value / magnitude - low / magnitude) / scale * 205
    out = [f'<svg viewBox="0 0 640 290" role="img" aria-label="{text(chart.title)}">',
           f'<title>{text(chart.title)} · {text(chart.unit)}</title>']
    if chart.type == 'donut':
        total = sum(series[0].values)
        offset = 0
        for i, (label, value) in enumerate(zip(labels, series[0].values)):
            fraction = value / total
            out.append(f'<circle cx="220" cy="140" r="85" fill="none" stroke="{COLORS[i % 4]}" stroke-width="48" pathLength="100" stroke-dasharray="{fraction * 100} {100 - fraction * 100}" stroke-dashoffset="{-offset}" transform="rotate(-90 220 140)"><title>{text(label)}: {value:g} ({fraction:.1%})</title></circle>')
            offset += fraction * 100
        out.append(f'<text x="220" y="145" text-anchor="middle">{total:,.4g}</text>')
    else:
        width = 560 / max(1, len(labels))
        positions = [45 + width * (j + .5) for j in range(len(labels))]
        if chart.type == 'line' and chart.temporal:
            dates = [datetime.fromisoformat(label if len(label) > 4 else label + '-01-01') for label in labels]
            duration = (dates[-1] - dates[0]).total_seconds() or 1
            positions = [45 + (date - dates[0]).total_seconds() / duration * 560 for date in dates]
        out.append(f'<path d="M45 {y(0):.2f}H610" stroke="#94a3b8"/>')
        for i, s in enumerate(series):
            previous = None
            for j, value in enumerate(s.values):
                if value is None:
                    previous = None
                    continue
                x = positions[j]
                title = f'<title>{text(labels[j])} · {text(s.name)}: {value:g}</title>'
                if chart.type == 'bar':
                    bar_width = max(.1, width * .8 / len(series))
                    left = x - width * .4 + i * bar_width
                    out.append(f'<rect x="{left:.2f}" y="{min(y(0), y(value)):.2f}" width="{bar_width:.2f}" height="{max(.5, abs(y(value)-y(0))):.2f}" fill="{COLORS[i]}">{title}</rect>')
                else:
                    if previous is not None:
                        out.append(f'<path d="M{previous[0]:.2f} {previous[1]:.2f}L{x:.2f} {y(value):.2f}" stroke="{COLORS[i]}" stroke-width="2" fill="none"/>')
                    out.append(f'<circle cx="{x:.2f}" cy="{y(value):.2f}" r="3" fill="{COLORS[i]}">{title}</circle>')
                    previous = (x, y(value))
        step = max(1, math.ceil(len(labels) / 6))
        for j in range(0, len(labels), step):
            out.append(f'<text x="{positions[j]:.2f}" y="265" text-anchor="middle" font-size="11">{text(labels[j][:18])}</text>')
        for value in (low, high):
            out.append(f'<text x="3" y="{y(value):.2f}" font-size="10">{value:.3g}</text>')
    out.append('</svg>')
    if chart.type == 'donut':
        out.append('<p>' + ' · '.join(f'{text(label)}: {value:g}' for label, value in zip(labels, series[0].values)) + '</p>')
    else:
        out.append('<p>' + ' · '.join(f'<span style="color:{COLORS[i]}">{text(s.name)}</span>' for i, s in enumerate(series)) + '</p>')
    return ''.join(out) + f'<small>{text(chart.unit)} · Exact values in source table below</small>'


def tile_content(tile, result):
    if not result or result.status not in {'complete', 'empty'}:
        return f'<p class="notice">{text(result.message if result else "Source unavailable")}</p>'
    rows = result.payload.get('rows') or []
    if not rows:
        return '<p class="notice">No matching observations. This is not a zero value.</p>'
    names = list(rows[0])
    measures = tile.measures or [key for key in names if any(number(row.get(key)) is not None for row in rows) and key != tile.dimension]
    if any(key not in names for key in [*measures, *([tile.dimension] if tile.dimension else [])]):
        return '<p class="notice">Selected fields are unavailable. Edit this tile.</p>' + table(rows)
    if tile.kind == 'kpi':
        if len(rows) != 1 or len(measures) != 1:
            return '<p class="notice">A KPI needs one aggregate row and one measure; showing observations.</p>' + table(rows)
        value = number(rows[0].get(measures[0]))
        shown = formatted(Decimal(str(rows[0][measures[0]]))) if value is not None else 'No observed value'
        return f'<p class="kpi">{shown}</p><p>{text(measures[0])}</p>'
    if tile.kind == 'summary':
        items = []
        for key in measures:
            values = [number(row.get(key)) for row in rows]
            observed = [value for value in values if value is not None]
            if observed:
                items.append(f'<li>{text(key)}: {len(observed)} observed; min {formatted(min(observed))}; max {formatted(max(observed))}; mean {formatted(mean(observed))}</li>')
        return '<p>Descriptive statistics of returned observations only.</p><ul>' + ''.join(items) + '</ul>'
    if tile.kind == 'table':
        return table([{key: row.get(key) for key in names if not tile.measures or key in {*measures, tile.dimension}} for row in rows])
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
            contract['chart_type'] = tile.kind
        chart = build_chart(payload, f'{tile.kind} chart')
        chart.title = tile.title
        return chart_svg(chart) + '<details><summary>Source observations</summary>' + table(rows) + '</details>'
    except ValueError as error:
        return f'<p class="notice">Chart unavailable: {text(error)}</p>' + table(rows)


def render_dashboard(document):
    results = {result.id: result for result in document.results}
    tiles = ''.join(f'<article class="span-{tile.span}"><h2>{text(tile.title)}</h2>{tile_content(tile, results.get(tile.query_id))}<small>Dataset: {text(tile.query_id)}</small></article>' for tile in document.tiles)
    sources = ''.join(f'<details><summary>{text(result.id)} · {text(result.status)}</summary><p>{text(result.question)}</p><p>{text(result.message)}</p><p>Error type: {text(result.payload.get("metadata", {}).get("error_type", "None reported"))}</p><pre>{text(result.payload.get("sql") or result.payload.get("attempted_sql") or "SQL text unavailable")}</pre><pre>{text(result.payload.get("parameters", []))}</pre><p>{text(result.payload.get("metadata", {}).get("limitations", []))}</p></details>' for result in document.results)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{escape(CSP, quote=True)}"><title>{text(document.title)}</title>
<style>body{{margin:0;background:#f2f5f7;color:#172d36;font:15px system-ui,sans-serif;padding:30px}}header,main,footer{{max-width:1300px;margin:auto}}h1{{font-size:32px;letter-spacing:-1px}}h2{{font-size:19px}}main{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}}article{{background:white;border:1px solid #d9e2e7;border-radius:14px;padding:22px;min-width:0}}.span-2{{grid-column:span 2}}.kpi{{font-size:42px;font-weight:700;margin:16px 0;color:#117b70}}small{{color:#526774}}svg{{width:100%;max-height:350px}}.table{{overflow:auto;max-height:380px}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #e4e9ed;white-space:nowrap}}details{{margin:14px 0}}summary{{cursor:pointer}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.notice{{color:#84510a}}footer{{margin-top:24px}}@media(max-width:700px){{body{{padding:15px}}main{{grid-template-columns:1fr}}.span-2{{grid-column:span 1}}}}</style></head>
<body><header><small>SQL-backed business dashboard · {text(document.status)} · Revision {document.revision}</small><h1>{text(document.title)}</h1><p>{text(document.description)}</p><p>Scope: {text(document.scope or 'As specified in source questions')}</p><p><small>Data refreshed {text(document.data_updated_at.isoformat())}. Saved {text(document.updated_at.isoformat())}.</small></p></header><main>{tiles}</main><footer><h2>Sources and limitations</h2><p>Charts and statistics describe returned SQL observations. Missing values are unknown. Currency is unconfirmed unless the source explicitly identifies it.</p>{sources}</footer></body></html>'''
