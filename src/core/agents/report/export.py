"""PDF export using the installed PyMuPDF renderer."""
from html import escape
from datetime import date, timedelta
from pathlib import Path
import tempfile
import re

import fitz

from core.agents.report.presentation import SECTION_TITLES, calendar_rows, comparison_metrics, data_notes, decision_text, default_chart_types, display_value, observations


def chart_svg(widget, metrics, kind, granularity):
    rows = widget['data']
    values = [row[key] for row in rows for key in widget['metric_ids'] if row[key] is not None]
    if not values:
        return None
    low, high = min(0, *values), max(0, *values)
    span = high - low or 1
    x = lambda index: 65 + (index + .5) * 530 / len(rows)
    y = lambda value: 185 - (value - low) / span * 150
    height = 240 + max(0, len(widget['metric_ids']) - 2) * 12
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="660" height="{height}" viewBox="0 0 660 {height}"><rect width="660" height="{height}" fill="white"/><line x1="65" x2="610" y1="{y(0)}" y2="{y(0)}" stroke="#64756c"/>']
    for series, key in enumerate(widget['metric_ids']):
        color = ('#0b7a66', '#a15c20', '#6951a8')[series % 3]
        segment = []
        def flush():
            if segment:
                parts.append(f'<polyline points="{" ".join(segment)}" stroke="{color}" fill="none" stroke-width="2"/>')
            segment.clear()
        for i, row in enumerate(rows):
            value = row[key]
            if i and widget['x_dimension'] == 'period':
                month_index = lambda period: int(period[:4]) * 12 + int(period[5:7])
                if month_index(row['period']) - month_index(rows[i-1]['period']) != {'month': 1, 'quarter': 3, 'year': 12}[granularity]:
                    flush()
            if value is None:
                flush(); continue
            if kind == 'bar':
                width = min(32, 400 / len(rows)) / len(widget['metric_ids'])
                parts.append(f'<rect x="{x(i) + series*width}" y="{min(y(value), y(0))}" width="{width}" height="{abs(y(value)-y(0))}" fill="{color}"/>')
            else:
                segment.append(f'{x(i)},{y(value)}')
                parts.append(f'<circle cx="{x(i)}" cy="{y(value)}" r="3" fill="{color}"/>')
        if kind == 'line': flush()
        parts.append(f'<text x="65" y="{225 + 11*series}" font-family="sans-serif" font-size="10" fill="{color}">{escape(metrics[key]["label"])}</text>')
    for i in (range(len(rows)) if len(rows) <= 12 else sorted({0, len(rows)//2, len(rows)-1})):
        label = str(rows[i][widget['x_dimension']] or 'Unknown')
        if widget['x_dimension'] == 'period': label = label[:7]
        parts.append(f'<text x="{x(i)}" y="207" text-anchor="middle" font-family="sans-serif" font-size="9">{escape(label)}</text>')
    parts.append(f'<text x="4" y="30" font-family="sans-serif" font-size="9">{high:,.0f}</text><text x="4" y="185" font-family="sans-serif" font-size="9">{low:,.0f}</text></svg>')
    return ''.join(parts)


def export_pdf(document):
    if document.report['report_type'] == 'inventory_operations':
        with tempfile.TemporaryDirectory() as directory:
            return render_pdf(inventory_parts(document, directory), directory)
    report, layout = document.report, document.presentation
    from core.agents.report.labels import SALES_SECTIONS_VI, uses_vietnamese_labels
    vi = uses_vietnamese_labels(report)
    chart_types = {**default_chart_types(report), **layout.chart_types}
    shown_metrics = comparison_metrics(report, document.monthly_decisions)
    metrics = {m['id']: m for m in shown_metrics}
    period = report['request']['period']
    end = date.fromisoformat(period['end_exclusive']) - timedelta(days=1)
    parts = [f'<h1>{escape(document.title)}</h1><p class="subtitle">{period["start"]} {"đến" if vi else "to"} {end}</p>']
    if layout.text_edits:
        parts.append('<p class="note">Includes user-edited narrative.</p>')
    with tempfile.TemporaryDirectory() as directory:
        visible_sections = 0
        for section in layout.section_order:
            if section in layout.hidden_sections: continue
            section_title = (SALES_SECTIONS_VI if vi else SECTION_TITLES)[section]
            parts.append(f'<h2{" class=new-page" if visible_sections and (section == "performance_analysis" or section == "decision_support" and document.monthly_decisions) else ""}>{escape(section_title)}</h2>')
            visible_sections += 1
            if section in layout.text_edits:
                parts.extend('<p>' + escape(line) + '</p>' for line in layout.text_edits[section].splitlines() if line.strip())
            elif section == 'sales_kpis':
                parts.append('<table><tr><th>Chỉ số bán hàng</th><th>Giá trị</th></tr>' if vi
                             else '<table><tr><th>Sales KPI</th><th>Value</th></tr>')
                parts.extend(f'<tr><td>{escape(m["label"])}</td><td>{display_value(m)}</td></tr>' for m in shown_metrics)
                parts.append('</table>')
            elif section == 'decision_support':
                parts.append('<p>' + escape(document.insights['decision_summary']) + '</p>')
                for action in document.insights['actions']:
                    parts.append(f'<h3>{escape(action["title"])}</h3><p>Why review this: {escape(action.get("why", ""))}</p><p>Recommended next step: {escape(action["action"])}</p><p>Periods: {escape(", ".join(action["periods"]))}</p>')
                if document.monthly_decisions:
                    parts.append('<p>Rules compare each month with its preceding calendar month.</p>')
                    parts.extend(f'<p class="note">{escape(rule["id"])}: {escape(rule["title"])}</p>' for rule in report['decisions'])
                    parts.append('<table><tr><th>Month</th><th>S01</th><th>S02</th><th>S03</th><th>S04</th></tr>')
                    for group in document.monthly_decisions:
                        cells = ''.join('<td>' + ('Triggered' if rule['triggered'] is True else 'Not triggered' if rule['triggered'] is False else 'Unavailable') + '</td>' for rule in group['decisions'])
                        parts.append(f'<tr><td>{escape(group["period"]["start"][:7])}</td>{cells}</tr>')
                    parts.append('</table>')
                else:
                    parts.extend(f'<h3>{escape(rule["title"])}</h3><p>{escape(decision_text(rule, report))}</p>' for rule in report['decisions'])
            elif section != 'performance_analysis':
                parts.extend(f'<p>{escape(item["text"])}</p>' for item in observations(report, section, document.monthly_decisions)
                             if section != 'key_findings_and_explanations' or not document.insights['findings'] or not item['text'].startswith('Period-over-period'))
                if section == 'key_findings_and_explanations':
                    parts.extend(f'<p>{escape(item["text"])}</p>' for item in document.insights['findings'])
                    if document.insights['document_context']:
                        parts.append('<h3>Retrieved document context</h3><p>Quoted source context; relevance to the reported movement and causality are not established.</p>')
                        parts.extend(f'<blockquote>{escape(item["text"])}</blockquote>' for item in document.insights['document_context'])
                    else:
                        parts.append('<p>No usable documentary explanation was retrieved. SQL findings and rule evaluations remain available independently. See Data needed below.</p>')
            if section == 'performance_analysis':
                chart_count = 0
                table_before_chart = False
                for widget in report['dashboard']['widgets']:
                    if widget['id'] in {'sales_kpis', 'order_kpis'}: continue
                    widget = {**widget, 'data': calendar_rows(widget, report['request'])}
                    kind = chart_types.get(widget['id'], widget['type'])
                    start_page = kind in {'line', 'bar'} and (table_before_chart or chart_count > 0 and chart_count % 2 == 0)
                    if start_page:
                        table_before_chart = False
                        chart_count = 0
                    parts.append(f'<div class="figure{" new-page" if start_page else ""}"><h3>{escape(widget["title"])}</h3>')
                    if kind == 'kpi_row':
                        if widget['id'] == 'line_breakdown':
                            parts.append('<p class="kpi">' + display_value(metrics['delivered_line_revenue']) + '</p>')
                        else:
                            parts.extend(f'<p>{escape(metrics[k]["label"])}: {display_value(metrics[k])}</p>' for k in widget['metric_ids'])
                    elif kind == 'table':
                        table_before_chart = True
                        parts.append('<table><tr><th>Period / dimension</th>' + ''.join(f'<th>{escape(metrics[k]["label"])}</th>' for k in widget['metric_ids']) + '</tr>')
                        for row in widget['data']:
                            cells = ''.join('<td>' + (display_value({**metrics[k], 'value': row[k]})) + '</td>' for k in widget['metric_ids'])
                            parts.append(f'<tr><td>{escape(str(row[widget["x_dimension"]] or "Unknown"))}</td>{cells}</tr>')
                        parts.append('</table>')
                    else:
                        svg = chart_svg(widget, metrics, kind, report['request']['granularity'])
                        if svg:
                            chart_count += 1
                            filename = widget['id'] + '.svg'
                            Path(directory, filename).write_text(svg, encoding='utf-8')
                            parts.append(f'<img src="{filename}" width="490" height="178"/>')
                        else: parts.append('<p>No chart observations for this period.</p>')
                    parts.append('</div>')
        parts.append('<h2 class="new-page">Ghi chú dữ liệu</h2>' if vi else '<h2 class="new-page">Data notes</h2>')
        parts.append('<h3>Dữ liệu cần bổ sung</h3>' if vi else '<h3>Data needed</h3>')
        parts.extend(f'<p class="note">{escape(text)}</p>' for text in document.insights['data_needs'])
        if document.monthly_decisions and report['request']['granularity'] == 'month':
            note = ('Chỉ số so sánh tháng mới nhất có dữ liệu doanh thu với tháng liền trước. Nếu thiếu dữ liệu để so sánh, chỉ số sẽ hiển thị là không có dữ liệu.'
                    if vi else 'The month-over-month KPI compares the latest observed month with its preceding calendar month. Totals cover the full requested period. Incomplete comparisons remain unavailable.')
            parts.append(f'<p class="note">{note}</p>')
        parts.extend(f'<p class="note">{escape(note)}</p>' for note in data_notes(report))
        for group in document.monthly_decisions:
            if group['comparison']['comparable'] is True and next(m['value'] for m in group['metrics'] if m['id'] == 'company_revenue_change_pct') is not None:
                continue
            c = group['coverage']
            counts = {key: 'unknown' if value is None else str(value) for key, value in c.items()}
            parts.append(f'<p class="note">{escape(group["period"]["start"][:7])} decision baseline: current month {counts["current_days"]}/{counts["expected_current_days"]} daily records; preceding month {counts["prior_days"]}/{counts["expected_prior_days"]}. Missing coverage or zero prior revenue prevents growth comparisons.</p>')
        return render_pdf(parts, directory)


def inventory_parts(document, directory):
    from core.agents.report.inventory_operations import SECTION_TITLES
    from core.agents.report.presentation import inventory_source_name, inventory_display_value
    report = document.report
    metrics = {m['id']: m for m in report['metrics']}
    period = report['request']['period']
    end = date.fromisoformat(period['end_exclusive']) - timedelta(days=1)
    parts = [f'<h1>{escape(document.title)}</h1><p class="subtitle">{period["start"]} to {end}</p>']
    sources, widget_sources = {}, {}

    def add_source(identifier, source):
        if identifier not in sources:
            sources[identifier] = {**source, 'number': len(sources) + 1}

    for metric in report['metrics']:
        for evidence in metric['evidence']:
            add_source(evidence['query_id'], evidence)
    for note in report['data_quality']['limitations']:
        match = re.match(r'^Dashboard source \[([a-f0-9]+)\] (\w+): (.*)$', note)
        if match:
            identifier, widget, description = match.groups()
            widget_sources[widget] = [identifier]
            add_source(identifier, {'source_table': description.split(';')[0],
                'title': next((w['title'] for w in report['dashboard']['widgets'] if w['id'] == widget), 'Chart source'),
                'filters': {} if widget == 'inventory_snapshots' else {'snapshot_date': report['data_quality']['coverage_end']}})
    for item in document.inventory_context.documents:
        add_source(item.citation_id, {**item.model_dump(), 'source_table': item.source})

    def cite_ids(identifiers):
        return ''.join(f'<a href="#inventory-source-{sources[key]["number"]}" style="color:#52635c;text-decoration:none"><sup>[{sources[key]["number"]}]</sup></a>'
                       for key in dict.fromkeys(identifiers) if key in sources)

    def cite(evidence):
        return cite_ids([e['query_id'] for e in evidence])

    def metric_table(identifiers):
        return ('<table class="inventory-table"><tr><th>Measure</th><th>Value</th></tr>' + ''.join(
            '<tr><td>' + escape(metrics[key]['label']) + cite(metrics[key]['evidence']) + '</td><td>' +
            escape(inventory_display_value(metrics[key])) + '</td></tr>' for key in identifiers) + '</table>')

    notes = data_notes(report)
    ownership = {'inventory_kpis': 'snapshot_scorecard', 'inventory_flag_distribution': 'product_risks',
                 'stockout_product_table': 'product_risks', 'operations_kpis': 'fulfillment_and_returns', 'inventory_snapshots': 'fulfillment_and_returns'}
    for section, title in SECTION_TITLES.items():
        if section == 'data_quality':
            parts.append('<h2>Validation summary</h2>')
            parts.extend('<p class="note">' + escape(text) + '</p>' for text in document.insights['validation_summary'])
            parts.extend('<p class="note">' + escape(text) + '</p>' for text in notes
                         if any(marker in text.lower() for marker in ('unavailable', 'could not', 'access is restricted', 'may be omitted')))
            parts.append('<p class="note">Source definitions and limitations remain in the saved report. Missing values are never treated as zero.</p>')
            continue
        parts.append(f'<h2{" class=new-page" if section in {"product_risks", "fulfillment_and_returns"} else ""}>{escape(title)}</h2>')
        if section == 'operations_summary':
            parts.append('<p class="note">Synthetic commerce demonstration data; source completeness and current business balances are not independently certified.</p>')
            parts.extend(f'<p>{escape(note)}</p>' for note in notes if note.startswith('Selected snapshot:'))
            parts.append('<p>' + ('This annual report uses one inventory snapshot. It does not add stock balances across months.'
                         if report['request']['granularity'] == 'year' else 'Inventory figures describe one snapshot.') + '</p>')
            parts.append('<p>Available fulfillment, return and review records are filtered to the requested reporting dates; complete transaction coverage is unverified.</p>')
            if metrics['stock_on_hand']['value'] is not None and metrics['observed_products']['value'] is not None:
                parts.append(f'<p>The selected snapshot records {inventory_display_value(metrics["stock_on_hand"])} across {display_value(metrics["observed_products"])} observed products.' +
                             cite([*metrics['stock_on_hand']['evidence'], *metrics['observed_products']['evidence']]) + '</p>')
            else:
                parts.append('<p>Snapshot totals are unavailable for this reporting period. Check the validation summary for missing inputs.</p>')
        for widget in report['dashboard']['widgets']:
            if ownership[widget['id']] != section:
                continue
            figure = widget['type'] in {'line', 'bar'}
            if figure:
                parts.append('<div class="figure">')
            evidence_ids = widget_sources.get(widget['id'], [e['query_id'] for key in widget['metric_ids'] for e in metrics[key]['evidence']] if widget['type'] == 'kpi_row' else [])
            parts.append(f'<h3>{escape(widget["title"])}' + cite_ids(evidence_ids) + '</h3>')
            if widget['type'] == 'kpi_row':
                parts.append(metric_table(widget['metric_ids']))
            elif widget['type'] == 'table':
                if widget['data']:
                    parts.append('<table class="inventory-table"><tr><th>Product</th><th>Stockout flags</th></tr>')
                    parts.extend(f'<tr><td>{escape(str(row["product"]))}</td><td>{row["stockout_products"]}</td></tr>' for row in widget['data'])
                    parts.append('</table>')
                else:
                    parts.append('<p>' + ('No stockout flags were observed at the selected snapshot.' if metrics['stockout_products']['value'] == 0
                                 else 'The stockout product list is unavailable for this scope.') + '</p>')
            else:
                svg = chart_svg(widget, metrics, widget['type'], report['request']['granularity'])
                if svg:
                    filename = widget['id'] + '.svg'
                    Path(directory, filename).write_text(svg, encoding='utf-8')
                    parts.append(f'<img src="{filename}" width="490" height="178"/>')
                else:
                    parts.append('<p>No chart observations available.</p>')
            if widget['id'] == 'inventory_flag_distribution':
                parts.append('<p class="note">A product may carry more than one flag.</p>')
            if widget['id'] == 'inventory_snapshots':
                parts.append('<p class="note">Each point is an independent snapshot; stock balances are never added across dates.</p>')
            if figure:
                parts.append('</div>')
        if section == 'snapshot_scorecard':
            parts.append(metric_table(['stockout_flag_pct', 'overstock_products']))
        if section == 'policy_evidence':
            if document.inventory_context.documents:
                parts.append('<p>Quoted policy context. These passages do not by themselves verify approval, effective dates or compliance.</p>')
                for item in document.inventory_context.documents:
                    parts.append('<blockquote>' + escape(item.content) + cite_ids([item.citation_id]) + '</blockquote>')
            else:
                status = document.inventory_context.retrieval_status
                message = ('Policy evidence is unavailable because document access is restricted.' if status == 'access_denied' else
                           'No matching authorized inventory policy passage was retrieved.' if status == 'no_evidence' else
                           'Policy evidence could not be retrieved. No policy-compliance conclusion has been added.')
                parts.append('<p>' + message + '</p>')
        if section == 'fixed_decisions':
            actions = document.insights['actions']
            if not actions:
                parts.append('<p>No recommendation can be confirmed. Verify the selected snapshot and flag inputs before acting.</p>')
            for action in actions:
                parts.append('<div class="inventory-decision"><h3>' + escape(action['title']) + cite_ids(action['citations']) +
                             '</h3><p>Why review this: ' + escape(action['why']) + '</p><p>Recommended next step: ' + escape(action['action']) + '</p></div>')
            for rule in report['decisions']:
                if rule['triggered'] is not True:
                    parts.append('<h3>' + escape(rule['title']) + '</h3><p class="note">' + escape(decision_text(rule, report)) + '</p>')
    parts.append('<h2>Sources</h2>')
    for source in sources.values():
        description = ('Role-authorized policy passage.' if source.get('source_type') == 'document' else source.get('title') or
                       ('Selected snapshot: ' + source['filters']['snapshot_date'] + '.' if source.get('filters', {}).get('snapshot_date') else
                        'Source queried for the requested reporting dates.'))
        parts.append(f'<p id="inventory-source-{source["number"]}" class="note">[{source["number"]}] ' +
                     escape(inventory_source_name(source['source_table'])) + '. ' + escape(description) + '</p>')
    if not sources:
        parts.append('<p>No source observations were returned for this period.</p>')
    return parts


def render_pdf(parts, directory):
    css = 'body{font-family:sans-serif;font-size:10pt;color:#14211d;line-height:1.3} h1{font-size:24pt;color:#075c4d}h2{font-size:16pt;margin-top:18pt}h3{font-size:10.5pt}h2,h3{page-break-after:avoid}p{margin:6pt 0}table{border-collapse:collapse;width:100%;margin:10pt 0}th,td{border-bottom:1px solid #dfe6e3;padding:7pt;text-align:left}th{background:#edf5f1}.subtitle,.note{color:#52635c}.note{font-size:8.5pt}.kpi{font-size:22pt;color:#075c4d}.new-page{page-break-before:always}.figure{page-break-inside:avoid;margin-top:14pt}img{max-width:100%}a{color:#075c4d;text-decoration:none}blockquote{border-left:2pt solid #0b7a66;padding-left:10pt;margin:10pt 0}'
    # Unfilled inventory headers avoid repeated background bands in MuPDF output.
    css += '.inventory-table th{background:transparent}.inventory-decision{page-break-inside:avoid}'
    story = fitz.Story(html=''.join(parts), user_css=css, archive=fitz.Archive(directory))
    size = fitz.paper_rect('a4')
    pdf = story.write_with_links(lambda *_: (size, size + (42, 42, -42, -42), None))
    for index, page in enumerate(pdf):
        page.insert_text((42, size.height - 22), f'{index + 1} / {len(pdf)}', fontsize=8, color=(.35,.42,.38))
    return pdf.tobytes(garbage=4, deflate=True)
