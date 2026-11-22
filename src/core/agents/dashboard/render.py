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

from core.agents.dashboard.charts import build_chart, _unit
from core.agents.sql.join_validation import column_origin
from core.agents.dashboard.formatting import format_number, format_datetime, format_value, axis_date
from core.agents.language import VIETNAMESE_STATUS, is_vietnamese, vietnamese_field

CSP = "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'"
COLORS = ['#0a66d8', '#64748b', '#7aa8e8', '#b45309', '#7c3aed', '#0f766e']


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


def table(rows, *, units=None, currency=None, dimension=None, vi=False):
    def cell(key, value):
        if vi and isinstance(value, bool):
            return 'Có' if value else 'Không'
        identifier = key.endswith('_id') or key in {'zip', 'year', 'fiscal_year', 'currency', 'product_name', 'category', 'segment'} or key == dimension
        if identifier and not isinstance(value, datetime) and not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[T ].*)?', str(value)):
            return text(value)
        unit = (units or {}).get(key)
        return text(format_value(value, unit=unit, currency=currency if unit and unit.startswith('currency') else None))
    names = list(dict.fromkeys(key for row in rows for key in row))[:20]
    return '<div class="table"><table><thead><tr>' + ''.join(f'<th>{text(vietnamese_field(k) if vi else k)}</th>' for k in names) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join(f'<td>{cell(k, row.get(k))}</td>' for k in names) + '</tr>' for row in rows[:200]) + '</tbody></table></div>'


def _sector(cx, cy, inner, outer, start, end):
    """Ring segment from `start` to `end` (fractions of a turn, 0 at 12 o'clock, clockwise)."""
    if end - start >= .9999:
        return (f'M{cx - outer} {cy}a{outer} {outer} 0 1 0 {2 * outer} 0a{outer} {outer} 0 1 0 {-2 * outer} 0Z'
                f'M{cx - inner} {cy}a{inner} {inner} 0 1 0 {2 * inner} 0a{inner} {inner} 0 1 0 {-2 * inner} 0Z')
    point = lambda r, f: (cx + r * math.sin(2 * math.pi * f), cy - r * math.cos(2 * math.pi * f))
    large = 1 if end - start > .5 else 0
    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = point(outer, start), point(outer, end), point(inner, end), point(inner, start)
    return f'M{x1:.2f} {y1:.2f}A{outer} {outer} 0 {large} 1 {x2:.2f} {y2:.2f}L{x3:.2f} {y3:.2f}A{inner} {inner} 0 {large} 0 {x4:.2f} {y4:.2f}Z'


def _tip(x, y, head, rows, W, flip=None):
    """SVG tooltip shown by CSS on :hover (the dashboard document runs no script)."""
    # name starts after the dot (27) or the edge (13); a 24 px gap; the value is bold and right-aligned 13 px in
    width = max([len(head) * 7.4 + 26] + [(27 if len(row) > 3 else 13) + len(row[0]) * 6.9 + 24 + len(row[1]) * 7.6 + 13 for row in rows])
    height = 30 + 20 * len(rows)
    left = x + 14
    if flip is True or (flip is None and left + width > W - 6):
        left = x - 14 - width
    left = max(6, min(left, W - width - 6))
    out = [f'<g class="tip" transform="translate({left:.1f} {y:.1f})"><rect width="{width:.1f}" height="{height}" rx="9"/>',
           f'<text class="t1" x="13" y="21">{text(head)}</text>']
    for k, (name, value, *extra) in enumerate(rows):
        cls = f' class="{extra[0]}"' if extra else ''
        dot = f'<circle cx="17" cy="{41 + 20 * k}" r="4" fill="{extra[1]}"/>' if len(extra) > 1 else ''
        out.append(f'{dot}<text x="{27 if dot else 13}" y="{45 + 20 * k}">{text(name)}</text><text{cls} x="{width - 13:.1f}" y="{45 + 20 * k}" text-anchor="end">{text(value)}</text>')
    return ''.join(out) + '</g>'


def chart_svg(chart, *, currency=None, granularity=None, vi=False, wide=False):
    W = 1240 if wide else 640  # full-width tiles get a wider canvas instead of letterboxing
    labels, series = chart.categories, chart.series
    values = [value for s in series for value in s.values if value is not None]
    if not values:
        return '<p class="notice">Không có dữ liệu phù hợp cho biểu đồ.</p>' if vi else '<p class="notice">No matching chart observations.</p>'
    shown = lambda value: formatted(value, unit=chart.unit, currency=currency if chart.unit.startswith('currency') or chart.unit in {'VND', 'USD', 'EUR'} else None)
    granularity = granularity or 'day'
    label_text = lambda label: axis_date(label, granularity) if chart.temporal else label
    low, high = min(0, min(values)), max(0, max(values))
    magnitude = max(abs(low), abs(high), 1)
    scale = high / magnitude - low / magnitude or 1
    y = lambda value: 235 - (value / magnitude - low / magnitude) / scale * 205
    display_unit = currency if currency and chart.unit.startswith('currency') else 'percent' if chart.unit.startswith('fraction') else chart.unit
    if vi:
        display_unit = {'percent': 'Phần trăm', 'count': 'Số lượng', 'number': 'Số',
                        'currency (unconfirmed)': 'Chưa xác nhận tiền tệ',
                        'currency': 'Tiền tệ', 'unknown_currency': 'Chưa xác nhận tiền tệ'}.get(display_unit, display_unit)
    # No <title>: the browser's own tooltip would cover the hover read-out; aria-label names the chart.
    out = [f'<svg class="c-{chart.type}" viewBox="0 0 {W} 290" role="img" aria-label="{text(chart.title)} · {text(display_unit)}">']
    overlay = []  # hover groups are painted last, so no bar or line covers a tooltip
    if chart.type == 'donut':
        total = sum(series[0].values)
        offset = 0
        reveal = f'reveal{abs(id(chart))}'  # the ring is uncovered by a stroke that draws once around the circle
        out.append(f'<defs><mask id="{reveal}" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="290"><circle class="draw" cx="{W//2}" cy="140" r="85" fill="none" stroke="#fff" stroke-width="70" pathLength="100" stroke-dasharray="100" stroke-dashoffset="0" transform="rotate(-90 {W//2} 140)"/></mask></defs><g mask="url(#{reveal})">')
        segments = []
        for i, (label, value) in enumerate(zip(labels, series[0].values)):
            fraction = value / total
            color = COLORS[i % len(COLORS)]
            geometry = f'cx="{W//2}" cy="140" r="85" fill="none" pathLength="100" stroke-dasharray="{fraction * 100} {100 - fraction * 100}" stroke-dashoffset="{-offset}" transform="rotate(-90 {W//2} 140)"'
            out.append(f'<circle class="v v-{i}" {geometry} stroke="{color}" stroke-width="48"/>')
            percent = formatted(fraction * 100, unit="percent")
            segments.append(f'<g class="seg seg-{i}" role="img" aria-label="{text(label_text(label))}: {text(shown(value))} ({text(percent)})"><path class="hit" d="{_sector(W//2, 140, 56, 114, offset / 100, (offset + fraction * 100) / 100)}" fill="transparent" fill-rule="evenodd"/>'
                            f'<text class="ctr" x="{W//2}" y="128" text-anchor="middle">{text(label_text(label)[:22])}</text><text class="ctr big" x="{W//2}" y="154" text-anchor="middle">{text(shown(value))}</text><text class="ctr" x="{W//2}" y="174" text-anchor="middle">{text(percent)}</text>'
                            + _tip(W//2 + 108, 70, label_text(label), [('Value' if not vi else 'Giá trị', shown(value)), ('Share' if not vi else 'Tỷ trọng', percent)], W, flip=False) + '</g>')
            offset += fraction * 100
        out.append('</g>')
        out.append(f'<text class="total" x="{W//2}" y="135" text-anchor="middle">{"Tổng" if vi else "Total"}</text><text class="total big" x="{W//2}" y="158" text-anchor="middle">{text(shown(total))}</text>')
        out.extend(segments)
    else:
        left = max(45, min(150, max(len(shown(value)) for value in (low, high))*5+14))
        width = (W-30-left) / max(1, len(labels))
        positions = [left + width * (j + .5) for j in range(len(labels))]
        if chart.type == 'line' and chart.temporal:
            dates = [datetime.fromisoformat(label if len(label) > 4 else label + '-01-01') for label in labels]
            duration = (dates[-1] - dates[0]).total_seconds() or 1
            positions = [left + (date - dates[0]).total_seconds() / duration * (W-30-left) for date in dates]
        out.append(f'<path d="M{left} {y(0):.2f}H{W-30}" stroke="#94a3b8"/>')
        for i, s in enumerate(series):
            previous = None
            for j, value in enumerate(s.values):
                if value is None:
                    previous = None
                    continue
                x = positions[j]
                if chart.type == 'bar':
                    bar_width = max(.1, width * .8 / len(series))
                    bar_left = x - width * .4 + i * bar_width
                    out.append(f'<rect x="{bar_left:.2f}" y="{min(y(0), y(value)):.2f}" width="{bar_width:.2f}" height="{max(.5, abs(y(value)-y(0))):.2f}" rx="3" fill="{COLORS[i]}"/>')
                    name = vietnamese_field(s.name) if vi else s.name
                    overlay.append(f'<g class="pt" role="img" aria-label="{text(label_text(labels[j]))} · {text(name)}: {text(shown(value))}"><rect class="hit" x="{bar_left:.2f}" y="20" width="{bar_width:.2f}" height="225" fill="transparent"/>'
                               + _tip(bar_left + bar_width / 2, max(4, min(y(0), y(value)) - 62), label_text(labels[j]), [(name, shown(value), 'v', COLORS[i])], W) + '</g>')
                else:
                    if previous is not None:
                        if len(series) == 1:  # soft area under a single line
                            out.append(f'<path d="M{previous[0]:.2f} {previous[1]:.2f}L{x:.2f} {y(value):.2f}L{x:.2f} {y(0):.2f}L{previous[0]:.2f} {y(0):.2f}Z" fill="#0a66d8" fill-opacity=".08"/>')
                        out.append(f'<path d="M{previous[0]:.2f} {previous[1]:.2f}L{x:.2f} {y(value):.2f}" stroke="{COLORS[i]}" stroke-width="2" stroke-linecap="round" fill="none"/>')
                    out.append(f'<circle cx="{x:.2f}" cy="{y(value):.2f}" r="3" fill="{COLORS[i]}"/>')
                    previous = (x, y(value))
        if chart.type == 'line':
            for j in range(len(labels)):
                x = positions[j]
                lo = (positions[j - 1] + x) / 2 if j else left
                hi = (x + positions[j + 1]) / 2 if j + 1 < len(labels) else W - 30
                rows, dots = [], []
                for i, s in enumerate(series):
                    value = s.values[j]
                    if value is None:
                        continue
                    name = vietnamese_field(s.name) if vi else s.name
                    rows.append((name, shown(value), 'v', COLORS[i]))
                    dots.append(f'<circle class="hdot" cx="{x:.2f}" cy="{y(value):.2f}" r="5" fill="{COLORS[i]}"/>')
                if not rows:
                    continue
                if len(series) == 1 and j and series[0].values[j - 1] not in (None, 0):
                    change = (series[0].values[j] - series[0].values[j - 1]) / abs(series[0].values[j - 1]) * 100
                    rows.append(('Change' if not vi else 'Thay đổi', f'{"↑" if change >= 0 else "↓"} {abs(change):.1f}%', 'up' if change >= 0 else 'down'))
                first = next(v for v in (s.values[j] for s in series) if v is not None)
                overlay.append(f'<g class="pt" role="img" aria-label="{text(label_text(labels[j]))}: ' + text(', '.join(f'{n} {v}' for n, v, *_ in rows)) + '">'
                           f'<rect class="hit" x="{lo:.2f}" y="20" width="{max(1, hi - lo):.2f}" height="225" fill="transparent"/>'
                           f'<line class="cross" x1="{x:.2f}" x2="{x:.2f}" y1="20" y2="{y(0):.2f}"/>' + ''.join(dots)
                           + _tip(x, 24, label_text(labels[j]), rows, W) + '</g>')
        step = max(1, math.ceil(len(labels) / 6))
        for j in range(0, len(labels), step):
            out.append(f'<text x="{positions[j]:.2f}" y="265" text-anchor="middle" font-size="11">{text(label_text(labels[j])[:24])}</text>')
        for value in (low, high):
            out.append(f'<text x="3" y="{y(value):.2f}" font-size="10">{text(shown(value))}</text>')
    out.extend(overlay)
    out.append('</svg>')
    if chart.type == 'donut':
        out.append('<p>' + ''.join(f'<span class="key key-{i}"><i style="background:{COLORS[i % len(COLORS)]}"></i>{text(label_text(label))}: {text(shown(value))}</span>' for i,(label,value) in enumerate(zip(labels,series[0].values))) + '</p>')
    else:
        out.append('<p>' + ''.join(f'<span class="key"><i style="background:{COLORS[i]}"></i>{text(vietnamese_field(s.name) if vi else s.name)}</span>' for i, s in enumerate(series)) + '</p>')
    note = ('Giá trị hiển thị đã được làm tròn. Dữ liệu lưu trữ giữ nguyên giá trị gốc.'
            if vi else 'Display values are rounded; original observations remain in the saved data.')
    return ''.join(out) + f'<small>{text(display_unit)}<span class="rounding"> · {note}</span></small>'


def _tile_content(tile, result, *, include_observations=True, chart=None, vi=False):
    rows = result.payload.get('rows') or []
    if not rows:
        return ('<p class="notice">Không có dữ liệu phù hợp. Giá trị chưa xác định.</p>' if vi
                else '<p class="notice">No matching observations. This is not a zero value.</p>')
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
        shown = formatted(Decimal(str(rows[0][measures[0]])), unit=unit, currency=currency if unit and unit.startswith('currency') else None) if value is not None else ('Không có giá trị quan sát' if vi else 'No observed value')
        return f'<p class="kpi">{shown}</p><p>{text(vietnamese_field(measures[0]) if vi else measures[0])}</p>'
    if tile.kind == 'summary':
        items = []
        for key in measures:
            values = [number(row.get(key)) for row in rows]
            observed = [value for value in values if value is not None]
            if observed:
                options = {'unit': units.get(key), 'currency': currency if (units.get(key) or '').startswith('currency') else None}
                if vi:
                    items.append(f'<li>{text(vietnamese_field(key))}: {formatted(len(observed), unit="count")} quan sát, nhỏ nhất {formatted(min(observed), **options)}, lớn nhất {formatted(max(observed), **options)}, trung bình {formatted(mean(observed), **options)}</li>')
                else:
                    items.append(f'<li>{text(key)}: {formatted(len(observed), unit="count")} observed; min {formatted(min(observed), **options)}; max {formatted(max(observed), **options)}; mean {formatted(mean(observed), **options)}</li>')
        if not items:
            raise ValueError('No numeric observations are available for this summary.')
        intro = 'Thống kê mô tả từ các quan sát trả về.' if vi else 'Descriptive statistics of returned observations only.'
        return f'<p>{intro}</p><ul>' + ''.join(items) + '</ul>'
    if tile.kind == 'table':
        return table([{key: row.get(key) for key in names if not tile.measures or key in {*measures, tile.dimension}} for row in rows], units=units, currency=currency, dimension=tile.dimension, vi=vi)
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
        source_label = 'Dữ liệu nguồn' if vi else 'Source observations'
        observations = f'<details><summary>{source_label}</summary>' + table(rows, units=units, currency=currency, dimension=tile.dimension, vi=vi) + '</details>' if include_observations else ''
        grain = re.search(r"DATE_TRUNC\(\s*'(day|month|quarter|year)'", payload.get('sql') or '', re.I)
        dimension_grain = tile.dimension if tile.dimension in {'month','quarter','year'} else None
        return chart_svg(chart, currency=currency, granularity=grain[1].lower() if grain else dimension_grain, vi=vi, wide=tile.span == 2) + observations
    except ValueError as error:
        raise ValueError('Chart unavailable: ' + str(error)) from error


def tile_presentation(tile, result, *, include_observations=True, chart=None, vi=False):
    if not result or result.status not in {'complete', 'empty'}:
        message = result.message if result and result.message and (not vi or is_vietnamese(result.message)) else (
            'Không lấy được dữ liệu nguồn.' if vi else 'Source unavailable')
        return f'<p class="notice">{text(message)}</p>', 'unavailable', message
    try:
        html = _tile_content(tile, result, include_observations=include_observations, chart=chart, vi=vi)
        return html, 'complete' if result.payload.get('rows') else 'empty', ''
    except ValueError as error:
        message = 'Dữ liệu trả về chưa phù hợp với cách hiển thị đã chọn.' if vi else str(error)
        units, currency = display_context(result.payload)
        return f'<p class="notice">{text(message)}</p>' + table(result.payload.get('rows') or [], units=units, currency=currency, dimension=tile.dimension, vi=vi), 'unavailable', message


def tile_content(tile, result):
    return tile_presentation(tile, result)[0]


def render_dashboard(document, *, charts=None, saved=True):
    vi = is_vietnamese(document.description)
    dataset_label = 'Bộ dữ liệu' if vi else 'Dataset'
    source_label = 'Dữ liệu nguồn' if vi else 'Source observations'
    status_label = lambda value: VIETNAMESE_STATUS.get(value, value) if vi else value
    results = {result.id: result for result in document.results}
    tiles, observed = [], set()
    for tile in document.tiles:
        content, status, _ = tile_presentation(tile, results.get(tile.query_id), include_observations=tile.query_id not in observed, chart=(charts or {}).get(tile.id), vi=vi)
        tiles.append(f'<article class="span-{tile.span}"><h2>{text(tile.title)}</h2>{content}<small class="ds">{dataset_label}: {text(tile.query_id)}</small></article>')
        if tile.kind in {'line', 'bar', 'donut', 'table'} and status == 'complete':
            observed.add(tile.query_id)
    tiles = ''.join(tiles)
    sources = []
    represented = {tile.query_id for tile in document.tiles if tile.kind in {'line', 'bar', 'donut', 'table'}}
    for result in document.results:
        parameters = ', '.join(str(value) for value in result.payload.get('parameters', [])) or ('Không có' if vi else 'None')
        error_type = result.payload.get('metadata', {}).get('error_type', 'Không có' if vi else 'None reported')
        sql = result.payload.get('sql') or result.payload.get('attempted_sql') or ('Không có câu lệnh SQL' if vi else 'SQL text unavailable')
        evidence = f'<details><summary>{text(result.id)} · {text(status_label(result.status))}</summary><p>{text(result.question)}</p><p>{text(result.message)}</p><p>{"Loại lỗi" if vi else "Error type"}: {text(error_type)}</p><pre>{text(sql)}</pre><pre>{text(parameters)}</pre><p>{text(result.payload.get("metadata", {}).get("limitations", []))}</p>'
        if result.id not in represented and result.payload.get('rows'):
            units, currency = display_context(result.payload)
            evidence += f'<details><summary>{source_label}</summary>' + table(result.payload['rows'], units=units, currency=currency, vi=vi) + '</details>'
        sources.append(evidence + '</details>')
    sources = ''.join(sources)
    label = f'SQL-backed business dashboard · {text(document.status)} · Revision {formatted(document.revision, unit="count")}' if saved else f'Live SQL overview · {text(document.status)}'
    timestamps = f'Data refreshed {text(format_datetime(document.data_updated_at))}.' + (f' Saved {text(format_datetime(document.updated_at))}.' if saved else '')
    if vi:
        label = f'Dashboard dữ liệu SQL · {text(status_label(document.status))}' + (f' · Phiên bản {formatted(document.revision, unit="count")}' if saved else '')
        timestamps = f'Cập nhật dữ liệu lúc {text(format_datetime(document.data_updated_at))}.' + (f' Lưu lúc {text(format_datetime(document.updated_at))}.' if saved else '')
    scope = document.scope or ('Theo yêu cầu truy vấn' if vi else 'As specified in source questions')
    footer = ('Biểu đồ và thống kê mô tả các quan sát do SQL trả về. Giá trị hiển thị đã được làm tròn; dữ liệu lưu trữ giữ nguyên giá trị gốc. Giá trị thiếu chưa được xác định. Đơn vị tiền tệ cần được xác nhận từ nguồn.'
              if vi else 'Charts and statistics describe returned SQL observations. Display values are rounded; original observations remain in the saved data. Missing values are unknown. Currency is unconfirmed unless the source explicitly identifies it.')
    return f'''<!doctype html><html lang="{'vi' if vi else 'en'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{escape(CSP, quote=True)}"><title>{text(document.title)}</title>
<style>:root{{--ink:#0f172a;--mut:#64748b;--line:#e5e7eb;--bg:#fff;--soft:#f8fafc;--accent:#0a66d8}}:root[data-theme=dark]{{--ink:#e5e7eb;--mut:#94a3b8;--line:#2a2d33;--bg:#161618;--soft:#1f2024;--accent:#4c9dff;color-scheme:dark}}[data-theme=dark] [fill="#0a66d8"]{{fill:#4c9dff}}[data-theme=dark] [stroke="#0a66d8"]{{stroke:#4c9dff}}[data-theme=dark] i[style*="#0a66d8"]{{background:#4c9dff!important}}[data-theme=dark] .notice{{color:#fbbf24}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,system-ui,-apple-system,'Segoe UI',sans-serif;padding:28px}}header,main,footer{{max-width:1300px;margin:auto}}header small{{color:var(--mut)}}h1{{font-size:26px;font-weight:650;letter-spacing:-.02em;margin:6px 0 4px}}h2{{font-size:13px;font-weight:600;color:var(--mut);margin:0 0 10px}}article>h2{{display:flex;align-items:center;gap:10px;font-size:24px;font-weight:700;color:var(--ink);letter-spacing:-.015em;line-height:1.25;margin:0 0 16px}}article>h2::before{{content:"";flex:none;width:4px;height:1.05em;border-radius:2px;background:var(--accent)}}main{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:20px}}article{{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:20px;min-width:0}}.span-2{{grid-column:span 2}}.kpi{{font-size:36px;font-weight:650;letter-spacing:-.02em;margin:8px 0 4px;color:var(--ink);font-variant-numeric:tabular-nums}}small{{color:var(--mut);font-size:13px}}svg{{width:100%;height:auto;display:block;overflow:visible}}svg .hit{{pointer-events:all}}svg .tip,svg .hdot,svg .cross,svg .ctr{{opacity:0;pointer-events:none;transition:opacity .12s}}svg .tip rect{{fill:var(--bg);stroke:var(--line);filter:drop-shadow(0 6px 16px rgba(0,0,0,.14))}}svg .tip text{{fill:var(--mut);font-size:12px}}svg .tip .t1{{fill:var(--ink);font-weight:600;font-size:13px}}svg .tip .v{{fill:var(--ink);font-weight:600}}svg .tip .up{{fill:var(--accent);font-weight:600}}svg .tip .down{{fill:#c2410c;font-weight:600}}svg .cross{{stroke:var(--mut);stroke-dasharray:3 3}}svg .hdot{{stroke:var(--bg);stroke-width:2}}svg .pt:hover .tip,svg .pt:hover .hdot,svg .pt:hover .cross,svg .seg:hover .tip,svg .seg:hover .ctr{{opacity:1}}svg .pt:hover .hit{{fill:rgba(10,102,216,.05)}}svg .total{{transition:opacity .12s}}svg:has(.seg:hover) .total{{opacity:0}}svg .ctr{{font-size:12px}}svg .ctr.big,svg .total.big{{font-size:22px;font-weight:650;fill:var(--ink)}}svg .v{{transition:opacity .15s,stroke-width .15s}}svg:has(.seg:hover) .v{{opacity:.3}}svg:has(.seg-0:hover) .v-0{{opacity:1;stroke-width:56}}article:has(.seg-0:hover) .key-0,article:has(.key-0:hover) .key-0{{background:color-mix(in srgb,var(--accent) 13%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 38%,transparent)}}article:has(.key-0:hover) svg .v{{opacity:.3}}article:has(.key-0:hover) svg .v-0{{opacity:1;stroke-width:56}}svg:has(.seg-1:hover) .v-1{{opacity:1;stroke-width:56}}article:has(.seg-1:hover) .key-1,article:has(.key-1:hover) .key-1{{background:color-mix(in srgb,var(--accent) 13%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 38%,transparent)}}article:has(.key-1:hover) svg .v{{opacity:.3}}article:has(.key-1:hover) svg .v-1{{opacity:1;stroke-width:56}}svg:has(.seg-2:hover) .v-2{{opacity:1;stroke-width:56}}article:has(.seg-2:hover) .key-2,article:has(.key-2:hover) .key-2{{background:color-mix(in srgb,var(--accent) 13%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 38%,transparent)}}article:has(.key-2:hover) svg .v{{opacity:.3}}article:has(.key-2:hover) svg .v-2{{opacity:1;stroke-width:56}}svg:has(.seg-3:hover) .v-3{{opacity:1;stroke-width:56}}article:has(.seg-3:hover) .key-3,article:has(.key-3:hover) .key-3{{background:color-mix(in srgb,var(--accent) 13%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 38%,transparent)}}article:has(.key-3:hover) svg .v{{opacity:.3}}article:has(.key-3:hover) svg .v-3{{opacity:1;stroke-width:56}}svg:has(.seg-4:hover) .v-4{{opacity:1;stroke-width:56}}article:has(.seg-4:hover) .key-4,article:has(.key-4:hover) .key-4{{background:color-mix(in srgb,var(--accent) 13%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 38%,transparent)}}article:has(.key-4:hover) svg .v{{opacity:.3}}article:has(.key-4:hover) svg .v-4{{opacity:1;stroke-width:56}}svg:has(.seg-5:hover) .v-5{{opacity:1;stroke-width:56}}article:has(.seg-5:hover) .key-5,article:has(.key-5:hover) .key-5{{background:color-mix(in srgb,var(--accent) 13%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 38%,transparent)}}article:has(.key-5:hover) svg .v{{opacity:.3}}article:has(.key-5:hover) svg .v-5{{opacity:1;stroke-width:56}}svg.c-bar .pt:hover .hit{{fill:rgba(10,102,216,.05)}}.key{{padding:3px 9px;border-radius:8px;transition:background .12s}}svg text{{fill:var(--mut);font-family:inherit}}svg path[stroke="#94a3b8"]{{stroke:var(--line)}}.table{{overflow:auto;max-height:380px}}table{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}}th{{position:sticky;top:0;background:var(--soft);color:var(--mut);font-weight:600;font-size:12px}}td,th{{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}}tbody tr:hover{{background:var(--soft)}}details{{margin:12px 0}}summary{{cursor:pointer;color:var(--accent)}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--soft);padding:10px;border-radius:8px;font-size:12px}}.key{{display:inline-flex;align-items:center;gap:6px;margin:0 8px 4px 0;font-size:14px}}.key i{{width:9px;height:9px;border-radius:3px;display:inline-block}}.rounding,.ds{{display:none}}:root[data-embed] body{{padding:0;background:transparent}}:root[data-embed] header,:root[data-embed] main,:root[data-embed] footer{{max-width:none}}:root[data-embed] header small,:root[data-embed] header h1,:root[data-embed] header p:nth-of-type(1),:root[data-embed] header p:nth-of-type(3){{display:none}}:root[data-embed] header p:nth-of-type(2){{margin:0 0 4px}}:root[data-embed] main{{margin-top:8px}}:root[data-embed] svg{{max-height:380px}}svg text[font-size]{{font-size:12px}}header p{{margin:2px 0;color:var(--mut)}}header p:nth-of-type(2){{font-size:12px}}@media(prefers-reduced-motion:no-preference){{@keyframes rise{{from{{opacity:0;transform:translateY(12px)}}}}@keyframes wipe{{from{{clip-path:inset(0 100% 0 0)}}to{{clip-path:inset(0 0 0 0)}}}}@keyframes grow{{from{{transform:scaleY(0)}}}}article{{animation:rise .6s cubic-bezier(.2,.7,.2,1) both}}article:nth-child(2){{animation-delay:.09s}}article:nth-child(3){{animation-delay:.18s}}article:nth-child(n+4){{animation-delay:.27s}}svg.c-line{{animation:wipe 1s .3s cubic-bezier(.3,.6,.2,1) both}}svg.c-bar rect{{transform-box:fill-box;transform-origin:50% 100%;animation:grow .7s .25s cubic-bezier(.2,.7,.2,1) both}}svg.c-donut .draw{{animation:draw 1.2s .25s cubic-bezier(.45,.05,.25,1) both}}@keyframes draw{{from{{stroke-dashoffset:100}}}}}}.notice{{color:#92400e}}footer{{margin-top:24px;color:var(--mut)}}@media(max-width:700px){{body{{padding:14px}}main{{grid-template-columns:1fr}}.span-2{{grid-column:span 1}}}}</style></head>
<body><header><small>{label}</small><h1>{text(document.title)}</h1><p>{text(document.description)}</p><p>{"Phạm vi" if vi else "Scope"}: {text(scope)}</p><p><small>{timestamps}</small></p></header><main>{tiles}</main><footer><h2>{"Nguồn và giới hạn" if vi else "Sources and limitations"}</h2><p>{footer}</p>{sources}</footer></body></html>'''
