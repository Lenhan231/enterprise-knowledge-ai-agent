"""Frozen-reference follow-up: one SQL cohort and six predeclared Report cases."""
import argparse
import asyncio
import hashlib
import json
import shutil
import statistics
import subprocess
import time
from pathlib import Path

from evaluation import run_inventory_agents_benchmark as benchmark

FROZEN = benchmark.OUT
OUTPUT = benchmark.ROOT / 'artifacts/evaluation/sql-semantic-contracts-2026-11-03/final'
REPORT_IDS = {'R01', 'R06', 'R16', 'R17', 'R20', 'R28'}


class QuotaExhausted(RuntimeError):
    pass


def prepare(*, check_application=True, selected_group=None, selected_ids=None):
    manifest = json.loads((FROZEN/'manifest.json').read_text(encoding='utf-8'))
    for group in ('sql_analytics', 'report'):
        (OUTPUT/group).mkdir(parents=True, exist_ok=True)
        for name in ('questions.jsonl', 'references.json', 'identity-counts.json'):
            source, target = FROZEN/group/name, OUTPUT/group/name
            if source.exists():
                if target.exists() and source.read_bytes() != target.read_bytes():
                    raise ValueError('Frozen input mismatch: '+str(target))
                if not target.exists():
                    shutil.copyfile(source, target)
        if hashlib.sha256((OUTPUT/group/'references.json').read_bytes()).hexdigest() != manifest['reference_sha256'][group]:
            raise ValueError('Frozen reference hash mismatch')
    hashes = {str(p.relative_to(benchmark.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((benchmark.ROOT/'src').rglob('*.py'))}
    target = OUTPUT/'manifest.json'
    if target.exists():
        existing = json.loads(target.read_text(encoding='utf-8'))
        if check_application and existing.get('reproduction_source_sha256',existing['application_source_sha256']) != hashes:
            raise ValueError('Application changed: use a separate benchmark directory.')
    else:
        manifest = {key:manifest[key] for key in ('judge','source_sha256','reference_sha256','oracle_status')}
        manifest.update(application_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                        application_source_sha256=hashes,
                        sql_ids=[f'S{i:02}' for i in range(1,31)], report_ids=sorted(REPORT_IDS),
                        knowledge_status='deferred', status='in_progress', between_request_seconds=10)
        if selected_group and selected_ids is not None:
            manifest['sql_ids' if selected_group=='sql_analytics' else 'report_ids'] = selected_ids
        benchmark.save(target, manifest)
    benchmark.OUT = OUTPUT


def cohort(directory, group, ids=None):
    rows = list({r['id']:r for r in benchmark.read_jsonl(directory/group/'generations.jsonl')
                 if ids is None or r['id'] in ids}.values())
    by_id = {r['id']:r for r in rows}
    scores = list({(r['id'],r['metric']):r for r in benchmark.read_jsonl(directory/group/'scores.jsonl')
              if r['id'] in by_id and benchmark.current_score(r,by_id[r['id']],group)}.values())
    refs = json.loads((FROZEN/group/'references.json').read_text(encoding='utf-8'))
    metrics = {}
    for name in benchmark.METRICS[group]:
        selected = [r for r in scores if r['metric']==name]
        values = [r['score'] for r in selected if r['score'] is not None]
        metrics[name] = {'mean':statistics.mean(values) if values else None,'scored':len(values),
                         'not_applicable':sum(r['score'] is None and not r['error'] for r in selected),
                         'evaluator_errors':sum(bool(r['error']) for r in selected),
                         'pending':len(rows)-len(selected)}
    latency = [r['elapsed_seconds'] for r in rows]
    unsupported = [r for r in rows if group=='sql_analytics' and not refs[r['id']]['supported']]
    refused = [r for r in unsupported if r['result'].get('metadata',{}).get('clarification_required')]
    expected = len(ids) if ids is not None else (30 if group=='sql_analytics' else len(REPORT_IDS))
    if ids is None and (directory/'manifest.json').exists():
        manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        expected = len(manifest.get('sql_ids' if group=='sql_analytics' else 'report_ids', range(expected)))
    return {'cases':len(rows), 'expected_cases':expected, 'unattempted':expected-len(rows), 'metrics':metrics,
            'outcomes':dict(benchmark.Counter(benchmark.generation_status(r) for r in rows)),
            'executed':sum(r['result'].get('data',{}).get('query_status')=='executed' for r in rows),
            'downloads':sum(r.get('payload_available',False) for r in rows),
            'provider_failures':sum(benchmark.rate_limited(r) or r['result'].get('metadata',{}).get('error_code') in
                                    {'provider_timeout','provider_unavailable'} for r in rows),
            'unsupported_cases':len(unsupported), 'unsupported_clarifications':len(refused),
            'latency_seconds':{'p50':statistics.median(latency) if latency else None,
                'p95':statistics.quantiles(latency,n=100,method='inclusive')[94] if len(latency)>1 else None}}


def summary():
    previous = benchmark.ROOT/'artifacts/evaluation/sql-semantic-refactor-2026-11-03/combined'
    benchmark.save(OUTPUT/'comparison.json', {
        'sql_before':cohort(previous,'sql_analytics'), 'sql_after':cohort(OUTPUT,'sql_analytics'),
        'report_before':cohort(FROZEN,'report',REPORT_IDS), 'report_after':cohort(OUTPUT,'report',REPORT_IDS),
        'notes':['First responses only; no implicit confirmation acceptance. Report sample is predeclared, not all 30 cases.',
                 'Unsupported clarification counts require manual validity review; they are not automatically valid refusals.',
                 'Metrics and judge are inherited unchanged. Numerical applicability retains the frozen scorer convention.',
                 'Sequential live latency includes in-request provider waits, excludes ten-second between-request pacing.']})


async def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('verify','generate','score','summary'),required=True)
    parser.add_argument('--group',choices=('sql_analytics','report'),default='sql_analytics')
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--ids',nargs='+')
    parser.add_argument('--retry-provider-errors',action='store_true')
    args = parser.parse_args()
    OUTPUT = args.output.resolve()
    prepare(check_application=args.stage in {'generate','verify'},selected_group=args.group,selected_ids=args.ids)
    manifest = json.loads((OUTPUT/'manifest.json').read_text(encoding='utf-8'))
    ids = args.ids or manifest['sql_ids' if args.group=='sql_analytics' else 'report_ids']
    original_cases = benchmark.load_cases
    order = {identifier:index for index,identifier in enumerate(ids)}
    benchmark.load_cases = lambda group: sorted([c for c in original_cases(group) if c['id'] in order],key=lambda c:order[c['id']])
    if args.stage=='verify':
        from evaluation import run_sql_semantic_ablation as ablation
        ablation.OUTPUT = OUTPUT
        await ablation.verify_snapshot(ids)
    elif args.stage=='summary':
        summary()
    elif args.stage=='score':
        await benchmark.score((args.group,), set(ids),retry_provider_errors=args.retry_provider_errors)
        summary()
    else:
        if subprocess.run(['git','diff','--quiet','HEAD','--','src'],cwd=benchmark.ROOT).returncode:
            raise ValueError('Commit application changes before generation.')
        from core.llm.groq_provider import GroqProvider
        original, checkpoint = GroqProvider.generate, benchmark.append
        calls = []

        def measured(provider,prompt,**kwargs):
            call = {'usage':None,'error':None,'response':None}
            calls.append(call)
            try:
                answer = original(provider,prompt,**kwargs)
                call.update(response=answer,usage=provider.last_usage)
                return answer
            except Exception as error:
                call['error'] = type(error).__name__
                raise

        def append(path,row):
            if path.name=='generations.jsonl':
                row.update(llm_calls=list(calls),llm_call_count=len(calls))
                calls.clear()
            checkpoint(path,row)
            if path.name=='generations.jsonl':
                if benchmark.rate_limited(row):
                    raise QuotaExhausted('All configured keys exhausted; checkpoint saved, remaining cases deferred.')
                time.sleep(8)  # Existing runner adds two seconds, outside measured request latency.

        GroqProvider.generate, benchmark.append = measured, append
        try:
            await benchmark.generate((args.group,), set(ids),retry_provider_errors=args.retry_provider_errors)
        except QuotaExhausted as error:
            print(str(error),flush=True)
        summary()


if __name__=='__main__':
    asyncio.run(main())
