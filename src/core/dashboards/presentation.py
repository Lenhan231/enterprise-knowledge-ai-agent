"""Bind presentation to observed SQL outputs; never infer a different business metric."""
import re
from datetime import date, datetime

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from core.dashboards.render import number, tile_presentation


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


def reconcile(document):
    bind_fields(document)
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
