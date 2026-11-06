"""Compare two completed frozen SQL cohorts without rescoring either one."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from sqlglot import parse_one
from evaluation import run_inventory_agents_benchmark as benchmark
from evaluation.run_sql_contract_benchmark import cohort


def completed(directory, ids=None):
    path=directory/'sql_analytics'
    attempts=benchmark.read_jsonl(path/'generations.jsonl')
    generations={r['id']:r for r in attempts}
    scores={(r['id'],r['metric']):r for r in benchmark.read_jsonl(path/'scores.jsonl')
            if r['id'] in generations and benchmark.current_score(r,generations[r['id']],'sql_analytics')}
    expected = set(ids) if ids is not None else {f'S{i:02}' for i in range(1,31)}
    assert set(generations)==expected, 'Incomplete generation cohort'
    assert len(scores)==len(expected)*3 and not any(r.get('error') for r in scores.values()), 'Incomplete/error evaluation'
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    summary=cohort(directory,'sql_analytics')
    summary.update(application_revision=manifest['application_revision'],total_attempts=len(attempts),
        provider_failures=sum(benchmark.provider_failed(r) for r in generations.values()),
        provider_failed_attempts=sum(benchmark.provider_failed(r) for r in attempts))
    return generations,scores,summary


def merge_incremental(base, updates, output):
    """Replace only measured cases; retain immutable source cohorts and case provenance."""
    assert not output.exists(), 'Use a new directory for the incremental benchmark'
    old_manifest, new_manifest = [json.loads((d/'manifest.json').read_text(encoding='utf-8')) for d in (base,updates)]
    ids = new_manifest['sql_ids']
    old_rows, old_scores, _ = completed(base)
    new_rows, new_scores, _ = completed(updates, ids)
    assert old_manifest['judge']==new_manifest['judge'], 'Judge changed'
    for name in ('agent_model','agent_temperature'):
        assert old_manifest.get(name)==new_manifest.get(name), 'Agent configuration changed: '+name
    for name in ('questions.jsonl','references.json','identity-counts.json'):
        assert (base/'sql_analytics'/name).read_bytes()==(updates/'sql_analytics'/name).read_bytes(), 'Frozen inputs changed: '+name
    assert set(ids) <= set(old_rows), 'Unknown replacement cases'
    assert not any(benchmark.provider_failed(r) for r in new_rows.values()), 'Unresolved provider failure'
    old_rows.update(new_rows)
    old_scores.update(new_scores)
    (output/'sql_analytics').mkdir(parents=True)
    for name in ('questions.jsonl','references.json','identity-counts.json'):
        shutil.copyfile(base/'sql_analytics'/name, output/'sql_analytics'/name)
    for key in sorted(old_rows):
        benchmark.append(output/'sql_analytics/generations.jsonl', old_rows[key])
        for metric in benchmark.METRICS['sql_analytics']:
            benchmark.append(output/'sql_analytics/scores.jsonl', old_scores[(key,metric)])
    provenance = {key:dict(source=str(updates if key in ids else base),
                          application_revision=(new_manifest if key in ids else old_manifest)['application_revision'])
                  for key in sorted(old_rows)}
    manifest = dict(old_manifest, application_revision='mixed; see case_provenance',
                    benchmark_type='incremental', retained_count=len(old_rows)-len(ids), rerun_count=len(ids),
                    replaced_ids=ids, case_provenance=provenance, sql_ids=sorted(old_rows))
    # A composite result has no single application snapshot and cannot resume generation.
    manifest.pop('application_source_sha256', None)
    manifest.pop('reproduction_source_sha256', None)
    benchmark.save(output/'manifest.json', manifest)
    completed(output)


def bound_sql(row):
    data=row['result'].get('data',{})
    return parse_one(benchmark.bind_sql(data['sql'],data.get('parameters',[])),read='postgres').sql(dialect='postgres') if data.get('sql') else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--overlay',type=Path,help='Completed subset to merge over --before into a new --after directory')
    args=parser.parse_args()
    if args.overlay:
        merge_incremental(args.before,args.overlay,args.after)
    before,b_scores,b_summary=completed(args.before)
    after,a_scores,a_summary=completed(args.after)
    manifests=[json.loads((d/'manifest.json').read_text(encoding='utf-8')) for d in (args.before,args.after)]
    assert manifests[0]['judge']==manifests[1]['judge'], 'Judge changed'
    for name in ('questions.jsonl','references.json','identity-counts.json'):
        hashes=[hashlib.sha256((d/'sql_analytics'/name).read_bytes()).hexdigest() for d in (args.before,args.after)]
        assert hashes[0]==hashes[1], 'Frozen inputs changed: '+name
    cases=[]
    for key in sorted(before):
        metrics={name:{'before':b_scores[(key,name)]['score'],'after':a_scores[(key,name)]['score']}
                 for name in benchmark.METRICS['sql_analytics']}
        cases.append(dict(id=key,before_status=benchmark.generation_status(before[key]),
            after_status=benchmark.generation_status(after[key]),metrics=metrics,
            identical_bound_sql=bound_sql(before[key]) is not None and bound_sql(before[key])==bound_sql(after[key])))
    variability=[r['id'] for r in cases if r['identical_bound_sql'] and
                 r['metrics']['sql_semantic_equivalence']['before']!=r['metrics']['sql_semantic_equivalence']['after']]
    numeric=[r['metrics']['numerical_accuracy'] for r in cases
             if all(r['metrics']['numerical_accuracy'][side] is not None for side in ('before','after'))]
    benchmark.save(args.after/'paired-summary.json',dict(before=b_summary,after=a_summary,cases=cases,
        identical_sql_semantic_score_changes=variability,
        common_numerical_applicability=dict(cases=len(numeric),
            before_mean=sum(r['before'] for r in numeric)/len(numeric) if numeric else None,
            after_mean=sum(r['after'] for r in numeric)/len(numeric) if numeric else None),
        notes=['Archived baseline vs new live run; identical frozen inputs and judge, not a simultaneous A/B run.',
               'Identical-SQL judge score changes are evaluator variability, not demonstrated code improvements.',
               'Numerical common applicability is a descriptive intersection; neither scorer nor references were changed.']))
    print(json.dumps(dict(before=b_summary,after=a_summary,identical_sql_semantic_score_changes=variability),indent=2))


if __name__=='__main__':
    main()
