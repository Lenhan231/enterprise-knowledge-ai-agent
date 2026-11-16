"""Reproducible count capability coverage; fixtures and optional read-only DB references."""
import argparse
import asyncio
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sqlite3
import sys

from sqlglot import parse_one

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from core.analytics.counting import compile_count_query
from core.analytics.metric_validation import MetricDefinitionError
from core.analytics.sql_validation import APPROVED_COLUMNS, decode_query_plan


INVENTORY = [
    {'snapshot_date': '2026-04-30', 'product_id': 9, 'stockout_flag': True, 'overstock_flag': False, 'reorder_flag': None, 'stock_on_hand': 2, 'category': 'A'},
    {'snapshot_date': '2026-05-31', 'product_id': 1, 'stockout_flag': True, 'overstock_flag': False, 'reorder_flag': True, 'stock_on_hand': 0, 'category': 'A'},
    {'snapshot_date': '2026-05-31', 'product_id': 1, 'stockout_flag': True, 'overstock_flag': False, 'reorder_flag': True, 'stock_on_hand': 0, 'category': 'A'},
    {'snapshot_date': '2026-05-31', 'product_id': 2, 'stockout_flag': True, 'overstock_flag': True, 'reorder_flag': False, 'stock_on_hand': 4, 'category': 'B'},
    {'snapshot_date': '2026-05-31', 'product_id': 3, 'stockout_flag': None, 'overstock_flag': True, 'reorder_flag': False, 'stock_on_hand': None, 'category': 'B'},
    {'snapshot_date': '2026-05-31', 'product_id': None, 'stockout_flag': True, 'overstock_flag': None, 'reorder_flag': None, 'stock_on_hand': -1, 'category': None},
]
ORDERS = [{'order_id': 1, 'order_status': 'paid'}, {'order_id': 1, 'order_status': 'paid'},
          {'order_id': 2, 'order_status': 'cancelled'}, {'order_id': None, 'order_status': None}]


def cases():
    result = []
    def add(name, counts, **changes):
        spec = {'source': 'commerce.inventory', 'counts': counts, 'time': {'mode': 'latest', 'field': 'snapshot_date'}, **changes}
        temporal = spec['time']
        question = ('latest available inventory snapshot' if temporal['mode'] == 'latest' else
                    'inventory counts on ' + temporal['start'] if temporal['mode'] == 'snapshot' else
                    'inventory counts from ' + temporal['start'] + ' through ' + temporal['end'] if temporal['mode'] == 'range' else
                    'count separate historical snapshots' if temporal['mode'] == 'history' else 'count all records')
        result.append({'name': name, 'spec': spec, 'question': question})
    for kind in ('rows', 'nonnull', 'distinct'):
        add(kind, [{'alias': 'n', 'kind': kind, **({'field': 'product_id'} if kind != 'rows' else {})}])
    for field in ('stockout_flag', 'overstock_flag', 'reorder_flag'):
        for operator, value, label in [('eq', True, 'true'), ('eq', False, 'false'), ('is_null', None, 'null'), ('is_not_null', None, 'known')]:
            add(field + '_' + label, [{'alias': 'n', 'kind': 'distinct', 'field': 'product_id',
                'filters': [{'field': field, 'operator': operator, 'value': value}]}])
    for operator in ('eq', 'lt', 'lte', 'gt', 'gte'):
        add('numeric_' + operator, [{'alias': 'n', 'kind': 'rows', 'filters': [{'field': 'stock_on_hand', 'operator': operator, 'value': 0}]}])
    trio = [{'alias': 'sku_count', 'kind': 'distinct', 'field': 'product_id'},
            *[{'alias': alias, 'kind': 'distinct', 'field': 'product_id', 'filters': [{'field': field, 'operator': 'eq', 'value': True}]}
              for alias, field in [('out_count', 'stockout_flag'), ('over_count', 'overstock_flag')]]]
    add('independent_overlapping_counts', trio)
    add('and_within_one_count', [{'alias': 'n', 'kind': 'rows', 'filters': [
        {'field': 'stockout_flag', 'operator': 'eq', 'value': True}, {'field': 'overstock_flag', 'operator': 'eq', 'value': True}]}])
    add('shared_population', trio, filters=[{'field': 'category', 'operator': 'in', 'value': ['A', 'B']}])
    add('empty_population_latest_unchanged', trio, filters=[{'field': 'category', 'operator': 'eq', 'value': 'missing'}])
    add('category_groups', trio, dimensions=['category'])
    add('exact_snapshot', trio, time={'mode': 'snapshot', 'field': 'snapshot_date', 'start': '2026-04-30'})
    add('inclusive_range_snapshot_groups', trio, time={'mode': 'range', 'field': 'snapshot_date', 'start': '2026-04-01', 'end': '2026-05-31'})
    add('history_snapshot_groups', trio, time={'mode': 'history', 'field': 'snapshot_date'})
    for kind in ('rows', 'nonnull', 'distinct'):
        add('orders_' + kind, [{'alias': 'n', 'kind': kind, **({'field': 'order_id'} if kind != 'rows' else {})}],
            source='commerce.orders', time={'mode': 'all'})
    add('renamed_count_aliases', [{**count, 'alias': 'counter_' + str(i)} for i, count in enumerate(trio)])
    return result


def matches(row, conditions):
    for item in conditions:
        value, wanted, operator = row[item['field']], item.get('value'), item['operator']
        if operator == 'is_null': valid = value is None
        elif operator == 'is_not_null': valid = value is not None
        elif value is None: valid = False
        elif operator == 'in': valid = value in wanted
        elif operator == 'eq': valid = value == wanted
        elif operator == 'lt': valid = value < wanted
        elif operator == 'lte': valid = value <= wanted
        elif operator == 'gt': valid = value > wanted
        else: valid = value >= wanted
        if not valid: return False
    return True


def oracle(spec, source_rows):
    temporal = spec['time']; mode = temporal['mode']; field = temporal.get('field')
    latest = max((row[field] for row in source_rows if row[field] is not None), default=None) if mode == 'latest' else None
    rows = [row for row in source_rows if matches(row, spec.get('filters', []))]
    if mode == 'latest': rows = [row for row in rows if row[field] == latest]
    elif mode in {'snapshot', 'range'}:
        rows = [row for row in rows if row[field] is not None and temporal['start'] <= row[field] <= temporal.get('end', temporal['start'])]
    dimensions = list(spec.get('dimensions', []))
    if spec['source'] == 'commerce.inventory' and mode in {'range', 'history'} and field not in dimensions:
        dimensions.insert(0, field)
    groups = {} if dimensions else {(): []}
    for row in rows: groups.setdefault(tuple(row[d] for d in dimensions), []).append(row)
    result = []
    for key, population in groups.items():
        output = dict(zip(dimensions, key))
        if spec['source'] == 'commerce.inventory' and mode in {'latest', 'snapshot'} and 'snapshot_date' not in dimensions:
            output['snapshot_date'] = latest if mode == 'latest' else temporal['start']
        for count in spec['counts']:
            subset = [row for row in population if matches(row, count.get('filters', []))]
            values = [row[count['field']] for row in subset if row[count['field']] is not None] if count['kind'] != 'rows' else []
            output[count['alias']] = len(subset) if count['kind'] == 'rows' else len(set(values)) if count['kind'] == 'distinct' else len(values)
        result.append(output)
    return sorted(result, key=lambda row: repr(sorted(row.items())))


def reference_plan(spec):
    """Independent SQL uses CASE operands, never the compiler's FILTER AST builder."""
    params = []
    def bind(value):
        params.append(value); return '$' + str(len(params))
    def predicates(items):
        result = []
        for item in items:
            field = 'r.' + item['field']; op = item['operator']
            if op in {'is_null', 'is_not_null'}: result.append(field + (' IS NULL' if op == 'is_null' else ' IS NOT NULL'))
            elif op == 'in': result.append(field + ' IN (' + ', '.join(bind(v) for v in item['value']) + ')')
            else: result.append(field + ' ' + {'eq': '=', 'lt': '<', 'lte': '<=', 'gt': '>', 'gte': '>='}[op] + ' ' + bind(item['value']))
        return result
    temporal = spec['time']; mode = temporal['mode']; field = temporal.get('field'); source = spec['source']
    dimensions = list(spec.get('dimensions', []))
    if source == 'commerce.inventory' and mode in {'range', 'history'} and field not in dimensions: dimensions.insert(0, field)
    projections = ['r.' + d + ' AS ' + d for d in dimensions]
    maximum = '(SELECT MAX(z.' + field + ') FROM ' + source + ' z)' if mode == 'latest' else None
    if source == 'commerce.inventory' and mode in {'latest', 'snapshot'} and 'snapshot_date' not in dimensions:
        projections.insert(0, (maximum if mode == 'latest' else 'CAST(' + bind(temporal['start']) + ' AS DATE)') + ' AS snapshot_date')
    for count in spec['counts']:
        conditions = predicates(count.get('filters', []))
        operand = '1' if count['kind'] == 'rows' else 'r.' + count['field']
        if conditions: operand = 'CASE WHEN ' + ' AND '.join(conditions) + ' THEN ' + operand + ' ELSE NULL END'
        projections.append('COUNT(' + ('DISTINCT ' if count['kind'] == 'distinct' else '') + operand + ') AS ' + count['alias'])
    where = predicates(spec.get('filters', []))
    if mode == 'latest': where.append('r.' + field + ' = ' + maximum)
    elif mode in {'snapshot', 'range'}:
        where += ['r.' + field + ' >= ' + bind(temporal['start']), 'r.' + field + ' <= ' + bind(temporal.get('end', temporal['start']))]
    sql = 'SELECT ' + ', '.join(projections) + ' FROM ' + source + ' r'
    if where: sql += ' WHERE ' + ' AND '.join(where)
    if dimensions: sql += ' GROUP BY ' + ', '.join('r.' + d for d in dimensions)
    sql += ' LIMIT 200' if dimensions else ' LIMIT 1'
    return decode_query_plan(json.dumps({'sql': sql, 'parameters': params}))


def negative_cases():
    base = cases()[20]['spec']
    changes = [{'joins': []}, {'source': 'private.users'}, {'source': 'commerce.inventory; DROP TABLE x'},
        {'counts': []}, {'counts': [{'alias': 'n', 'kind': 'rows'}] * 9},
        {'counts': [{'alias': 'n', 'kind': 'rows'}] * 2}, {'counts': [{'alias': 'bad alias', 'kind': 'rows'}]},
        {'counts': [{'alias': 'n', 'kind': 'distinct'}]}, {'counts': [{'alias': 'n', 'kind': 'rows', 'field': 'product_id'}]},
        {'counts': [{'alias': 'n', 'kind': 'distinct', 'field': 'password'}]},
        {'counts': [{'alias': 'n', 'kind': 'rows', 'filters': [{'field': 'stockout_flag', 'operator': 'eq', 'value': None}]}]},
        {'counts': [{'alias': 'n', 'kind': 'rows', 'filters': [{'field': 'stockout_flag', 'operator': 'gt', 'value': True}]}]},
        {'counts': [{'alias': 'n', 'kind': 'rows', 'filters': [{'field': 'category', 'operator': 'in', 'value': []}]}]},
        {'dimensions': ['password']}, {'time': {'mode': 'latest', 'field': 'product_id'}},
        {'time': {'mode': 'range', 'field': 'snapshot_date', 'start': '2026-06-01', 'end': '2026-01-01'}},
        {'time': {'mode': 'snapshot', 'field': 'snapshot_date', 'start': '2026-02-30'}}, {'time': {'mode': 'all'}}]
    return [{'name': 'reject_' + str(i), 'spec': {**deepcopy(base), **change}, 'question': 'latest available inventory snapshot'} for i, change in enumerate(changes)]


async def evaluate(live=False):
    report = {'scope': '32 single-source count cases; not all SQL or all natural-language requests', 'fixture': [], 'rejection': [], 'live': []}
    with sqlite3.connect(':memory:') as db:
        db.execute("ATTACH DATABASE ':memory:' AS commerce")
        for table, rows in [('inventory', INVENTORY), ('orders', ORDERS)]:
            fields = list(rows[0]); db.execute('CREATE TABLE commerce.' + table + '(' + ','.join(fields) + ')')
            db.executemany('INSERT INTO commerce.' + table + ' VALUES (' + ','.join('?' for _ in fields) + ')', [tuple(r[f] for f in fields) for r in rows])
        for case in cases():
            plan, _, _ = compile_count_query(case['spec'], APPROVED_COLUMNS, case['question'])
            cursor = db.execute(parse_one(plan.sql, read='postgres').sql(dialect='sqlite'), [str(p) if isinstance(p, date) else p for p in plan.parameters])
            actual = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor]
            actual.sort(key=lambda row: repr(sorted(row.items())))
            expected = oracle(case['spec'], INVENTORY if case['spec']['source'] == 'commerce.inventory' else ORDERS)
            report['fixture'].append({'case': case['name'], 'passed': actual == expected})
    for case in negative_cases():
        try: compile_count_query(case['spec'], APPROVED_COLUMNS, case['question']); passed = False
        except MetricDefinitionError: passed = True
        report['rejection'].append({'case': case['name'], 'passed': passed})
    if live:
        from dotenv import load_dotenv
        from core.database.commerce_repository import LazyCommerceRepository
        load_dotenv()
        repo = LazyCommerceRepository()
        try:
            schema = await repo.get_schema()
            for case in cases():
                try:
                    plan, _, _ = compile_count_query(case['spec'], schema['tables'], case['question'], schema['date_columns'])
                    reference = reference_plan(case['spec'])
                    actual = await repo.execute_approved_query(plan.sql, *plan.parameters)
                    expected = await repo.execute_approved_query(reference.sql, *reference.parameters)
                    canonical = lambda rows: sorted([json.dumps(row, sort_keys=True, default=str) for row in rows])
                    report['live'].append({'case': case['name'], 'passed': canonical(actual) == canonical(expected)})
                except Exception as error:
                    report['live'].append({'case': case['name'], 'passed': False, 'error_type': type(error).__name__})
        finally: await repo.close()
    report['summary'] = {group: {'passed': sum(case['passed'] for case in report[group]), 'total': len(report[group])}
                         for group in ('fixture', 'rejection', 'live')}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Compare against independent read-only database queries')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.live))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['summary']))
    if any(values['passed'] != values['total'] for values in report['summary'].values()): raise SystemExit(1)


if __name__ == '__main__': main()
