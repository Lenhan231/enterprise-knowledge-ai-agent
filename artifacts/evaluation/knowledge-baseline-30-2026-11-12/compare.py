"""Compare the corrected, import-verified historical cohort with integrated v3."""
import hashlib
import json
from pathlib import Path
import re
from statistics import mean

HERE = Path(__file__).resolve().parent
CURRENT = HERE.parent / 'knowledge-invoice-2026-11-10-v3'
if not CURRENT.exists():
    CURRENT = HERE.parents[2] / 'artifacts/local/agent-evaluation-20261110/artifacts/evaluation/knowledge-invoice-2026-11-10-v3'
METRICS = ('faithfulness', 'answer_relevancy', 'context_precision')


def load(folder, name):
    return json.loads((folder / name).read_text(encoding='utf-8'))


def lines(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]


def digest(row):
    return hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def run():
    cases = load(HERE, 'cases.json')['knowledge']
    assert cases == load(CURRENT, 'cases.json')['knowledge']
    assert load(HERE, 'database-before.json') == load(HERE, 'database-after.json')
    assert load(HERE, 'database-before.json')['corpus_sha256'] == load(CURRENT, 'database-before.json')['corpus_sha256']
    expected = load(HERE, 'source-provenance.json')['runtime_import_expectations']
    imports = lines(HERE / 'runtime-imports.jsonl')
    assert {r['stage'] for r in imports} == {'generate', 'score'}
    for record in imports:
        for module in record['modules'].values():
            assert expected[module['path'].replace('\\', '/')] == module['sha256']
    generations, scores, summaries = {}, {}, {}
    for label, folder in [('baseline', HERE), ('v3', CURRENT)]:
        g = lines(folder / 'knowledge/generations.jsonl')
        s = lines(folder / 'knowledge/scores.jsonl')
        assert len(g) == 30 and {r['id'] for r in g} == {c['id'] for c in cases}
        assert len(s) == 90 and {(r['id'], r['metric']) for r in s} == {(c['id'], m) for c in cases for m in METRICS}
        by_id = {r['id']: r for r in g}
        assert all(r['generation_sha256'] == digest(by_id[r['id']]) for r in s)
        generations[label], scores[label] = by_id, {(r['id'], r['metric']): r for r in s}
        summaries[label] = dict(generation_failures=[r['id'] for r in g if r.get('generation_error')],
            supported_refusals=[r['id'] for r in g if r.get('abstained') and not next(c['should_abstain'] for c in cases if c['id'] == r['id'])],
            correct_unsupported_refusals=sum(bool(r.get('abstained')) for r in g if next(c['should_abstain'] for c in cases if c['id'] == r['id'])),
            metric_errors=[dict(id=r['id'], metric=r['metric'], error=r['error']) for r in s if r['error']])
    paired = {}
    for supported_only in (False, True):
        selected = [c['id'] for c in cases if not supported_only or not c['should_abstain']]
        group = {}
        for metric in METRICS:
            pairs = [(scores['baseline'][i, metric]['score'], scores['v3'][i, metric]['score']) for i in selected]
            pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
            group[metric] = dict(cases=len(pairs), baseline=mean(a for a, b in pairs), v3=mean(b for a, b in pairs),
                change_pp=100 * mean(b-a for a, b in pairs))
        paired['supported_only' if supported_only else 'all_common'] = group
    differences = []
    normalize = lambda answer: re.sub(r'\[S\d+\]', '[S]', answer)
    for case in cases:
        identifier = case['id']
        a, b = [generations[k][identifier] for k in ('baseline', 'v3')]
        if a.get('generation_error') or b.get('generation_error'):
            continue
        differences.append(dict(id=identifier, question=case['question'], supported=not case['should_abstain'],
            same_answer=normalize(a['result']['answer']) == normalize(b['result']['answer']),
            same_context_set={c['content'] for c in a['contexts']} == {c['content'] for c in b['contexts']},
            same_context_order=[c['content'] for c in a['contexts']] == [c['content'] for c in b['contexts']],
            deltas={m: scores['v3'][identifier, m]['score'] - scores['baseline'][identifier, m]['score']
                for m in METRICS if scores['v3'][identifier, m]['score'] is not None and scores['baseline'][identifier, m]['score'] is not None}))
    result = dict(summaries=summaries, paired=paired, case_differences=differences)
    (HERE / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = ['# Corrected Knowledge baseline versus integrated v3', '',
        f"In this corrected run, v3 scores {paired['all_common']['faithfulness']['change_pp']:+.2f} percentage points on faithfulness, "
        f"{paired['all_common']['answer_relevancy']['change_pp']:+.2f} points on answer relevancy, and "
        f"{paired['all_common']['context_precision']['change_pp']:+.2f} points on context precision. "
        'The earlier apparent overall regression is not reproduced. Relevancy is effectively unchanged; this is one run, not a significance claim.', '',
        'The historical runtime is import-verified. The earlier 2026-11-11 experiment was invalid and is not used. '
        'See [method, schema adaptation and limitations](README.md). Both cohorts use identical questions, references and indexed policy data.', '']
    for name, group in paired.items():
        report += [f'## {name}', '', '| Metric | Common scored cases | Historical baseline | Integrated v3 | Change (pp) |', '|---|---:|---:|---:|---:|']
        for metric, row in group.items():
            report.append(f"| {metric} | {row['cases']} | {100*row['baseline']:.2f}% | {100*row['v3']:.2f}% | {row['change_pp']:+.2f} |")
        report.append('')
    report += ['## Outcomes', '', '| Outcome | Historical baseline | Integrated v3 |', '|---|---|---|']
    for field in ('generation_failures', 'supported_refusals', 'correct_unsupported_refusals'):
        report.append(f"| {field} | {summaries['baseline'][field]} | {summaries['v3'][field]} |")
    report += ['', 'Faithfulness is N/A for refusals. Supported-only metrics exclude the five intentionally unsupported lookups. '
        'Context precision depends on passage ranking and LLM relevance judgments; answer relevancy uses generated questions and embeddings. '
        'Neither is a deterministic correctness test. Quantization, prompt changes and hosted inference/judge variation are confounded; '
        'this run cannot establish which change caused a score difference. No statistical-significance or speed claim is made.', '',
        'Per-case score differences and equal-answer/equal-context checks are in [comparison.json](comparison.json). '
        'All raw generations, contexts, scores, runtime-import hashes and read-only database snapshots are retained.', '']
    (HERE / 'COMPARISON.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(dict(summaries=summaries, paired=paired), indent=2))


if __name__ == '__main__':
    run()
