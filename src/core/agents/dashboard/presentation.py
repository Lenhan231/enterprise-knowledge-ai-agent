"""Bind presentation to observed SQL outputs; never infer a different business metric."""
import re
from datetime import date, datetime
from types import SimpleNamespace

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError, SqlglotError
from sqlglot.lineage import lineage

from core.agents.dashboard.render import number, tile_presentation
from core.agents.dashboard.models import TileSpec
from core.agents.dashboard.charts import requested_chart_type
from core.agents.sql.metric_ontology import METRIC_ONTOLOGY, _normalize


def canonical(name):
    return re.sub(r'^(?:total|sum)_|_(?:total|sum)$', '', name.lower())


def output_roles(payload):
    try:
        tree = parse_one(payload.get('sql', ''), read='postgres')
        projections = {item.alias_or_name: item.unalias() for item in tree.selects}
        grouped = set()
        for item in (tree.args.get('group') or exp.Group()).expressions:
            if isinstance(item, exp.Literal) and item.is_int:
                index = int(item.this) - 1
                if 0 <= index < len(tree.selects):
                    grouped.add(tree.selects[index].alias_or_name)
            else:
                grouped.update(name for name, projection in projections.items()
                               if projection == item or isinstance(item, exp.Column) and item.name == name)
        return projections, grouped
    except (ParseError, ValueError, AttributeError, TypeError):
        return {}, set()


def temporal(values):
    return bool(values) and all(isinstance(value, (date, datetime)) or
        isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[ T].*)?', value) for value in values)


def bind_fields(document):
    datasets = {result.id: result.payload for result in document.results}
    for tile in document.tiles:
        if tile.kind == 'table' and not tile.measures and tile.dimension is None:
            continue
        payload = datasets.get(tile.query_id, {})
        rows = payload.get('rows') or []
        if not rows:
            continue
        names = list(rows[0])
        projections, grouped = output_roles(payload)
        def bind(name):
            if name in names:
                return name
            matches = [key for key in names if canonical(key) == canonical(name)]
            return matches[0] if len(matches) == 1 else name
        tile.measures = [bind(name) for name in tile.measures]
        if tile.dimension:
            tile.dimension = bind(tile.dimension)
        dimensions = [name for name in names if name in grouped]
        dates = [name for name in names if name in projections and temporal([row.get(name) for row in rows])]
        if tile.dimension is None or tile.dimension not in names and tile.dimension.lower() in {
                'date', 'month', 'period', 'snapshot_date', 'order_date'}:
            if len(dates) == 1:
                tile.dimension = dates[0]
            elif tile.dimension is None and len(dimensions) == 1:
                tile.dimension = dimensions[0]
        if not tile.measures:
            inferred = [name for name in names if name not in grouped and name != tile.dimension
                        and any(number(row.get(name)) is not None for row in rows)
                        and (not projections or name in projections and projections[name].find(exp.AggFunc))]
            if len(inferred) <= 4:
                tile.measures = inferred


def table_requested(question):
    return bool(re.search(r'^\s*(?:a\s+)?table\b|\b(?:show|display|render|return|use|as|switch to)\s+(?:a\s+)?(?:data\s+)?table\b|\bin\s+a\s+table\b|(?:dạng|hiển thị)\s+bảng', question, re.I))


def presentation_choice(question):
    try:
        chart = requested_chart_type(question)
    except ValueError:
        return None
    if chart and re.search(r'\btable\b|\bbảng\b', question, re.I):
        return None
    if table_requested(question):
        return None if chart else 'table'
    return chart


def presentation_only(reply, tile):
    """Recognize display commands; unfamiliar/data-changing text returns to query planning."""
    if not presentation_choice(reply) or any(mark in reply for mark in ('"', "'", '=', '<', '>')):
        return False
    aliases = set(tile.measures)
    for name in tile.measures:
        known = METRIC_ONTOLOGY.get(canonical(name), {}).get('aliases', ())
        if isinstance(known, dict):
            aliases.update(alias for values in known.values() for alias in values)
        else:
            aliases.update(known)
    text = _normalize(reply).replace('_', ' ')
    for alias in sorted(aliases, key=len, reverse=True):
        text = re.sub(r'(?<!\w)' + re.escape(_normalize(alias).replace('_', ' ')) + r'(?!\w)', ' ', text)
    display_words = set(('use show display render switch change convert put make please instead just '
        'a an the chart charts line bar donut doughnut pie table it this that these those all data '
        'result results observations in as to of and me '
        'hiển thị chuyển sang dạng bảng biểu đồ cột thanh đường tròn toàn bộ dữ liệu kết quả này bằng vui lòng giúp tôi thay thế').split())
    words = re.findall(r'\w+', text)
    return bool(words) and set(words) <= display_words


def set_representation(tile, kind, result):
    generated_title = (tile.kind.title() + ': ' + ', '.join(tile.measures).replace('_', ' '))[:120]
    if tile.title == generated_title:
        tile.title = (kind.title() + ': ' + ', '.join(tile.measures).replace('_', ' '))[:120]
    tile.kind = kind
    if kind == 'table':
        tile.measures, tile.dimension = [], None
    result.payload.get('metadata', {}).pop('_presentation_clarification', None)


def _chart_groups(tile, result):
    """Partition only when the same renderer accepts every measure and resulting chart."""
    if (tile.kind not in {'line', 'bar', 'donut'} or len(tile.measures) < 2
            or tile_presentation(tile, result)[1] == 'complete'):
        return []
    groups = []
    for measure in tile.measures:
        if tile_presentation(tile.model_copy(update={'measures': [measure]}), result)[1] != 'complete':
            return []
        for group in groups:
            if tile_presentation(tile.model_copy(update={'measures': [*group, measure]}), result)[1] == 'complete':
                group.append(measure)
                break
        else:
            groups.append([measure])
    if len(groups) != 2:
        return []
    return [tile.model_copy(update={'id': tile.id if index == 0 else tile.id[:29] + '_1',
                'title': (tile.kind.title() + ': ' + ', '.join(group).replace('_', ' '))[:120],
                'measures': group}) for index, group in enumerate(groups)]


def automatic_chart_tiles(tiles, result, question):
    """Consolidate redundant automatic styles; explicit user chart choices are never rewritten."""
    try:
        if requested_chart_type(question):
            return tiles
    except ValueError:
        return tiles
    bind_fields(SimpleNamespace(tiles=tiles, results=[result]))
    groups = {}
    for tile in tiles:
        if tile.kind in {'line', 'bar', 'donut'}:
            groups.setdefault((tile.query_id, tile.dimension, tuple(sorted(tile.measures))), []).append(tile)
    replacements, removed = {}, set()
    for (_, dimension, _), group in groups.items():
        if len(group) < 2 or not dimension:
            continue
        rows = result.payload.get('rows') or []
        preferred = 'line' if temporal([row.get(dimension) for row in rows]) else 'bar'
        for kind in dict.fromkeys((preferred, 'bar')):
            candidate = group[0].model_copy(update={'kind': kind})
            if tile_presentation(candidate, result)[1] == 'complete' or _chart_groups(candidate, result):
                candidate.title = (kind.title() + ': ' + ', '.join(candidate.measures).replace('_', ' '))[:120]
                replacements[group[0].id] = candidate
                removed.update(tile.id for tile in group[1:])
                break
    return [replacements.get(tile.id, tile) for tile in tiles if tile.id not in removed]


def automatic_tiles(result, question):
    table = TileSpec(id='data', title='Source data', kind='table', query_id=result.id, span=2)
    rows = result.payload.get('rows') or []
    if result.status != 'complete' or not rows:
        return [table]
    charts = result.payload.get('metadata', {}).get('request_contract', {}).get('charts')
    if charts:
        return [TileSpec(id=f'chart{i}', title=(', '.join(chart['measures']) + ' by ' + chart['dimension']).replace('_', ' ').title()[:120],
                         kind=chart['type'], query_id=result.id, dimension=chart['dimension'], measures=chart['measures'], span=2)
                for i, chart in enumerate(charts)]
    try:
        requested = requested_chart_type(question)
    except ValueError:
        result.payload.setdefault('metadata', {})['_presentation_clarification'] = (
            'SQL completed, but the returned chart mapping does not identify a separate type and measures '
            'for each requested chart. Please specify the chart type and metric for each chart, or choose a table.')
        return [table]
    if not requested and table_requested(question):
        return [table]
    projections, grouped = output_roles(result.payload)
    aggregates = [name for name, expression in projections.items()
                  if name in rows[0] and expression.find(exp.AggFunc) and not expression.find(exp.Window)
                  and name not in grouped
                  and all(row.get(name) is None or number(row[name]) is not None for row in rows)]
    ungrouped = aggregates and not any(select.args.get('group')
        for select in parse_one(result.payload['sql'], read='postgres').find_all(exp.Select))
    if not requested and len(rows) == 1 and ungrouped:
        return [TileSpec(id=f'kpi{i}', title=name.replace('_', ' ').title()[:120], kind='kpi',
                         query_id=result.id, measures=[name]) for i, name in enumerate(aggregates[:8])]
    candidate = TileSpec(id='chart', title='Query result', kind=requested or 'bar', query_id=result.id, span=2)
    bind_fields(SimpleNamespace(tiles=[candidate], results=[result]))
    if candidate.measures:
        candidate.title = (', '.join(name.replace('_', ' ').title() for name in candidate.measures)
                           + (' by ' + candidate.dimension.replace('_', ' ').title() if candidate.dimension else ''))[:120]
    # Raw detail rows do not establish aggregate statistics or a dashboard grain.
    if not requested and not aggregates and candidate.dimension is None:
        return [table]
    if not requested and candidate.dimension and (temporal([row.get(candidate.dimension) for row in rows])
            or candidate.dimension in {'year', 'fiscal_year'}):
        candidate.kind = 'line'
    _, status, reason = tile_presentation(candidate, result)
    if status != 'complete':
        if _chart_groups(candidate, result):
            return [candidate]
        result.message = (result.message + '\n' + reason).strip()[:1200]
        return [candidate] if requested else [table]
    return [candidate]


def aggregate_outputs(payload):
    try:
        outputs = lineage(None, payload.get('sql', ''), dialect='postgres')
    except (SqlglotError, ValueError):
        return set()
    return {name for name, node in outputs.items()
            if any(item.expression.find(exp.AggFunc) for item in node.walk())
            and not any(item.expression.find(exp.Window) for item in node.walk())}


def summary_tiles(result, question, tiles):
    # shortcut: recognize explicit English/Vietnamese statistics phrases; add a control for broader language support.
    requested = re.search(r'\b(?:statistical summary|summary statistics?|summary statistic|descriptive statistics?|statistics summary)\b|thống kê mô tả|tóm tắt thống kê', question, re.I)
    rows = result.payload.get('rows') or []
    if not requested or result.status != 'complete' or len(rows) < 2:
        return []
    _, grouped = output_roles(result.payload)
    aggregates = aggregate_outputs(result.payload)
    charts = [tile for tile in tiles if tile.kind in {'line', 'bar', 'donut'}]
    summaries = []
    for index, tile in enumerate(charts):
        measures = [name for name in tile.measures if name in aggregates and name not in grouped]
        if not measures or tile_presentation(tile, result)[1] != 'complete':
            continue
        identifier = 'summary' if len(charts) == 1 else f'summary{index}'
        title = 'Descriptive statistics' + (': ' + ', '.join(measures).replace('_', ' ') if len(charts) > 1 else '')
        summaries.append(TileSpec(id=identifier, title=title[:120], kind='summary', query_id=result.id,
                                  measures=measures, span=2))
    return summaries


def presentation_clarification(document):
    """Offer only alternatives that the renderer can build from this same result."""
    results = {result.id: result for result in document.results}
    for tile in document.tiles:
        result = results.get(tile.query_id)
        if result and result.payload.get('metadata', {}).get('_presentation_clarification'):
            return tile.id, result.payload['metadata']['_presentation_clarification']
        if tile.kind not in {'line', 'bar', 'donut', 'kpi', 'summary'} or not result or result.status != 'complete':
            continue
        _, status, reason = tile_presentation(tile, result)
        if status != 'unavailable':
            continue
        alternatives = []
        for kind in ('line', 'bar', 'donut', 'table'):
            candidate = tile.model_copy(update={'kind': kind})
            if kind == 'table':
                candidate.measures, candidate.dimension = [], None
            if kind != tile.kind and tile_presentation(candidate, result)[1] == 'complete':
                alternatives.append(kind + (' chart' if kind != 'table' else ''))
            elif _chart_groups(candidate, result):
                alternatives.append('separate ' + kind + ' charts, grouped by compatible measures')
        columns = ', '.join((result.payload.get('rows') or [{}])[0])[:300]
        measures = ', '.join(tile.measures)[:160]
        label = tile.kind + ' chart' if tile.kind in {'line', 'bar', 'donut'} else tile.kind + ' output'
        question = (f'SQL completed for {tile.query_id}, but the requested {label} is not suitable. '
                f'{reason[:300]} Requested measures: {measures}. Returned columns: {columns}. '
                f'Supported with these results: {", ".join(alternatives)}. '
                'Which representation would you like? For different chart types, specify the measures for each chart. '
                'Keep at most two charts per dataset; measures sharing one chart need a comparable unit.')[:1200]
        return tile.id, question
    return None


def reconcile(document):
    bind_fields(document)
    results = {result.id: result for result in document.results}
    question = document.description
    for turn in document.clarifications:
        if presentation_choice(turn.reply):
            question = turn.reply
    single_chart = re.search(r'\b(?:one|single|1)\s+(?:(?:line|bar|donut|doughnut)\s+)?chart\b(?!\s+(?:per|for each)\b)', question, re.I)
    for tile in list(document.tiles):
        groups = [] if single_chart else _chart_groups(tile, results.get(tile.query_id))
        chart_count = sum(t.query_id == tile.query_id and t.kind in {'line', 'bar', 'donut'} for t in document.tiles)
        other_ids = {t.id for t in document.tiles if t is not tile}
        if (groups and chart_count - 1 + len(groups) <= 2 and len(document.tiles) - 1 + len(groups) <= 8
                and not other_ids & {t.id for t in groups}):
            index = document.tiles.index(tile)
            document.tiles[index:index + 1] = groups
    used = {tile.query_id for tile in document.tiles}
    document.queries = [query for query in document.queries if query.id in used]
    document.results = [result for result in document.results if result.id in used]
    results = {result.id: result for result in document.results}
    document.tile_status = {}
    for tile in document.tiles:
        _, status, message = tile_presentation(tile, results.get(tile.query_id))
        document.tile_status[tile.id] = {'status': status, 'message': message}
    count = sum(item['status'] != 'unavailable' for item in document.tile_status.values())
    document.status = 'complete' if count == len(document.tiles) else 'partial' if count else 'failed'
    return document
