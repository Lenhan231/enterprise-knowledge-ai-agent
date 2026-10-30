"""Score saved paired runs against frozen database aggregates and current semantics."""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from sqlglot import exp, parse_one
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.metric_validation import validate_metric_definitions, validate_metric_request
from core.analytics.text_to_sql import APPROVED_COLUMNS, decode_query_plan


def calculation_matches(case, gold):
    """Compare values and requested groups; ties in fill rankings may use any product."""
    result = case['result']
    if not result.get('ok') or not result.get('sql'):
        return False
    selects = parse_one(result['sql'], read='postgres').selects
    measures = [p for p in selects if any(c.name == case['field'] for c in p.find_all(exp.Column))]
    if len(measures) != 1:
        return False
    expression = measures[0]
    key = expression.alias_or_name or expression.key
    dimensions = case['dimensions']
    def values(rows, field):
        return sorted((tuple(str(row.get(d)) for d in dimensions), row.get(field)) for row in rows)
    actual = values(result['rows'], key)
    expected = values(gold, 'fill_rate' if case['id'] == 'lowest_fill' else 'value')
    if len(actual) != len(expected):
        return False
    return all(a_dims == e_dims and a is not None and e is not None
               and math.isclose(float(a), float(e), rel_tol=1e-8, abs_tol=0.000001)
               for (a_dims, a), (e_dims, e) in zip(actual, expected))


def score_case(case, gold):
    result, calls = case['result'], case['generation_calls']
    score = {'id': case['id'], 'elapsed_ms': case['elapsed_ms'],
             'generation_calls': len(calls), 'executed': result.get('query_status') == 'executed',
             'clarification': bool(result.get('metadata', {}).get('clarification_required')),
             'current_semantics': False, 'sql_validation': False, 'generated_sql': False,
             'calculation': False, 'metric_correct': False}
    # Replay saved plans without execution to separate enforcement from generation changes.
    raw = calls[-1].get('response') if calls else None
    if raw:
        try:
            decoded = json.loads(raw)
            score['generated_sql'] = bool(decoded.get('sql'))
            plan = decode_query_plan(raw)
            score['sql_validation'] = bool(plan.sql)
            if plan.sql:
                names = resolve_metric_names(case['question'])
                validate_metric_request(case['question'], names)
                validate_metric_definitions(plan.sql, names, plan.parameters, APPROVED_COLUMNS, question=case['question'])
                score['current_semantics'] = True
        except (ValueError, TypeError, KeyError):
            pass
    if case.get('clarification_code'):
        score['targeted_clarification'] = (score['clarification'] and not score['executed'] and
            result.get('metadata', {}).get('metric_error_code') == case['clarification_code'])
    else:
        score['calculation'] = calculation_matches(case, gold[case['id']])
        dates = {row.get('snapshot_date') for row in result.get('rows', [])}
        expected_dates = {row['snapshot_date'] for row in gold[case['id']]}
        score['metric_correct'] = score['calculation'] and score['current_semantics'] and dates == expected_dates
    return score


def compare(before, after, gold):
    settings = ('model', 'temperature', 'reasoning_effort', 'max_output_tokens', 'case_sha256', 'pace_seconds')
    if any(before[key] != after[key] for key in settings):
        raise ValueError('Paired benchmark settings or questions differ')
    if [c['id'] for c in before['cases']] != [c['id'] for c in after['cases']]:
        raise ValueError('Paired benchmark cases differ')
    report = {'settings': {key: before[key] for key in settings}, 'supported_cases': 6, 'unresolved_cases': 2}
    for name, run in [('before', before), ('after', after)]:
        cases = [score_case(case, gold['cases']) for case in run['cases']]
        report[name] = {'cases': cases, 'totals': {key: sum(bool(c.get(key)) for c in cases) for key in
                        ('generated_sql','sql_validation','executed','calculation','metric_correct','targeted_clarification')},
                        'median_elapsed_ms': statistics.median(c['elapsed_ms'] for c in cases),
                        'supported_median_ms': statistics.median(c['elapsed_ms'] for c in cases if 'targeted_clarification' not in c)}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'after', 'gold', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite comparison evidence')
    inputs = [json.loads(getattr(args, name).read_text(encoding='utf-8')) for name in ('before','after','gold')]
    args.output.write_text(json.dumps(compare(*inputs), indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
