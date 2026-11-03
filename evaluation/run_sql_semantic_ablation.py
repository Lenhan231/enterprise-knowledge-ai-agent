"""Isolated SQL ablations using frozen November 2 questions, references and scorer."""
import argparse
import ast
import asyncio
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
import time
import types
from pathlib import Path

from evaluation import run_inventory_agents_benchmark as benchmark

ROOT = benchmark.ROOT
BASELINE = '3ba340d'
FROZEN = benchmark.OUT
OUTPUT = ROOT / 'artifacts/evaluation/sql-semantic-refactor-2026-11-03'
VARIANTS = ('baseline', 'temporal', 'ontology', 'schema', 'compiler', 'combined')
MODULES = ('core.analytics.metric_validation', 'core.analytics.metric_mapping',
           'core.analytics.text_to_sql', 'core.agents.sql_analytics_agent', 'core.reports.planning')


def function_source(source, name):
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    return '\n'.join(source.splitlines()[node.lineno-1:node.end_lineno])


def variant_sources(variant):
    """Load historical modules in-process; never change the checkout for an experiment."""
    result = {}
    for name in MODULES:
        path = 'src/' + name.replace('.', '/') + '.py'
        old = subprocess.check_output(['git', 'show', BASELINE+':'+path], cwd=ROOT).decode('utf-8')
        new = (ROOT / path).read_text(encoding='utf-8')
        source = new if variant == 'combined' else old
        if variant == 'temporal':
            if name.endswith('metric_validation'):
                source = new.replace(function_source(new, 'validate_metric_definitions'),
                                     function_source(old, 'validate_metric_definitions'))
            elif name.endswith('metric_mapping'):
                decoder = function_source(new,'decode_metric_mapping').replace(
                    "    protected = {name for name in known if METRIC_ONTOLOGY[name].get('definition_status') in {'unresolved', 'draft'}\n                 or METRIC_ONTOLOGY[name].get('approval_status') == 'unreviewed'}\n    if protected - set(mapping.metrics):",
                    '    if known - set(mapping.metrics):')
                source = old.replace('validate_metric_request, _validate_inventory_time,',
                    'validate_metric_request, _validate_inventory_time, inventory_time_scope,')
                source = source.replace(function_source(old,'decode_metric_mapping'),decoder)
        if variant == 'ontology':
            if name.endswith('metric_validation'):
                source = old+'\n\n'+function_source(new,'inventory_observation_query')+'\n'
                source = source.replace(function_source(old,'validate_metric_definitions'),
                                        function_source(new,'validate_metric_definitions'))
            elif name.endswith('metric_mapping'):
                source = old.replace('    if known - set(mapping.metrics):',
                    "    protected = {name for name in known if METRIC_ONTOLOGY[name].get('definition_status') in {'unresolved', 'draft'}}\n    if protected - set(mapping.metrics):")
                source = source.replace('validate_metric_request, _validate_inventory_time,',
                    'validate_metric_request, _validate_inventory_time, inventory_observation_query,')
                source = source.replace(function_source(old,'validate_mapped_sql'),function_source(new,'validate_mapped_sql'))
                source = source.replace('Use domain=other only for requests entirely outside inventory analytics',
                    'Use domain=other for structural inventory key/count/presence diagnostics, or requests entirely outside inventory analytics')
            elif name.endswith('sql_analytics_agent'):
                source = old.replace('validate_metric_request(question, metric_names)',
                    "validate_metric_request(question, {name for name in metric_names if get_metric_definition(name).get('definition_status') in {'unresolved', 'draft'}})", 1)
        if variant == 'schema' and name.endswith('text_to_sql'):
            source = old.replace('import json', 'import json\nimport re\nfrom core.analytics.join_validation import PRIMARY_KEYS', 1)
            source = source.replace(function_source(old, 'build_sql_prompt'),
                function_source(new, 'relevant_schema_tables')+'\n\n'+function_source(new, 'build_sql_prompt'))
        if variant == 'compiler':
            if name.endswith('metric_mapping'):
                source = old+'\n\n'+function_source(new, 'compile_inventory_query')+'\n'
            elif name.endswith('sql_analytics_agent'):
                source = new.replace("validate_metric_request(question, {name for name in metric_names\n                    if get_metric_definition(name).get('definition_status') in {'unresolved', 'draft'}\n                    or get_metric_definition(name).get('approval_status') == 'unreviewed'})",
                                     'validate_metric_request(question, metric_names)', 1)
                source = source.replace('    relevant_schema_tables,\n','').replace(
                    "if (context is not None\n                    or any(get_metric_definition(name).get('domain') == 'inventory_management' for name in metric_names)\n                    or (not metric_names and 'commerce.inventory' in relevant_schema_tables(question, {}))):",
                    "if context is not None or not metric_names or any(get_metric_definition(name).get('domain') == 'inventory_management' for name in metric_names):")
                source = source.replace('from core.analytics.commerce_decision_support import resolve_commerce_decision_domain, unavailable_commerce_dimensions\n','')
                start = source.index('        unavailable = ')
                end = source.index('        metric_names = ',start)
                source = source[:start]+source[end:]
        result[name] = source
    return result


def install_variant(variant):
    for name, source in variant_sources(variant).items():
        module = types.ModuleType(name)
        module.__file__ = str(ROOT / ('src/'+name.replace('.', '/')+'.py'))
        module.__package__ = name.rsplit('.',1)[0]
        sys.modules[name] = module
        exec(compile(source, module.__file__, 'exec'), module.__dict__)


def prepare(variant):
    destination = OUTPUT / variant
    for group in ('sql_analytics', 'report'):
        (destination/group).mkdir(parents=True, exist_ok=True)
        for filename in ('questions.jsonl', 'references.json', 'identity-counts.json'):
            source = FROZEN/group/filename
            target = destination/group/filename
            if source.exists():
                if target.exists() and target.read_bytes() != source.read_bytes():
                    raise ValueError('Frozen input changed: '+str(target))
                if not target.exists():
                    shutil.copyfile(source, target)
    manifest = destination/'manifest.json'
    hashes = {name: hashlib.sha256(source.encode()).hexdigest() for name, source in variant_sources(variant).items()}
    if not manifest.exists() or not (destination/'sql_analytics/generations.jsonl').exists():
        data = json.loads((FROZEN/'manifest.json').read_text())
        data.update(ablation_variant=variant, application_baseline=BASELINE,
                    baseline_reference_directory=str(FROZEN.relative_to(ROOT)),
                    between_request_seconds=10,
                    application_source_sha256=hashes)
        benchmark.save(manifest,data)
    data = json.loads(manifest.read_text())
    if isinstance(data['source_sha256'],dict):
        data['application_source_sha256'] = data['source_sha256']
        data['source_sha256'] = json.loads((FROZEN/'manifest.json').read_text())['source_sha256']
    if data['application_source_sha256'] != hashes:
        raise ValueError('Application changed since this variant was generated; use a separate output directory.')
    for key in ('completed_at','sql_completed_at','focused_validation','benchmark_tests','sql_status',
                'report_status','generation_harness_history'):
        data.pop(key,None)
    data['status'] = 'ablation_run; see comparison.json for completion and coverage'
    benchmark.save(manifest,data)
    return destination


async def verify_snapshot():
    from core.database.commerce_repository import create_repository_from_env
    from evaluation.inventory_benchmark_metrics import compare_rows
    repo = await create_repository_from_env()
    matches = {}
    try:
        async with repo.pool.acquire() as connection:
            async with connection.transaction(readonly=True, isolation='repeatable_read'):
                await connection.execute("SET LOCAL statement_timeout='5000ms'")
                refs = json.loads((FROZEN/'sql_analytics/references.json').read_text())
                for identifier, reference in refs.items():
                    if not reference['supported']:
                        continue
                    actual = json.loads(benchmark.dumps([dict(r) for r in await connection.fetch(reference['reference']['sql'])]))
                    matches[identifier] = compare_rows(actual, reference['reference']['rows'])
                    print('snapshot',identifier,matches[identifier],flush=True)
    finally:
        await repo.close()
    benchmark.save(OUTPUT/'snapshot-verification.json', {'reference_matches':matches,
        'all_match':all(matches.values()), 'note':'Repeatable-read verification of oracle results, not a persisted database snapshot.'})
    if not all(matches.values()):
        raise RuntimeError('Database no longer matches frozen reference results; do not claim comparable accuracy.')


def comparison():
    """Keep coverage and infrastructure failures alongside every accuracy estimate."""
    refs = json.loads((FROZEN/'sql_analytics/references.json').read_text())
    focused = {'S02','S03','S04','S10','S11','S14','S23','S26','S27','S28'}
    from evaluation.inventory_benchmark_metrics import sql_numerical_accuracy
    numeric_ids = {identifier for identifier, ref in refs.items() if ref['supported']
                   and sql_numerical_accuracy([],ref['reference']['rows']) is not None}

    def cohort(folder, identifiers=None):
        rows = list({r['id']:r for r in benchmark.read_jsonl(folder/'sql_analytics/generations.jsonl')}.values())
        rows = [r for r in rows if identifiers is None or r['id'] in identifiers]
        for row in rows:
            row.setdefault('result', {'metadata':{}, 'data':{}})
        by_id = {r['id']:r for r in rows}
        scores = list({(r['id'],r['metric']):r for r in benchmark.read_jsonl(folder/'sql_analytics/scores.jsonl')}.values())
        scores = [r for r in scores if r['id'] in by_id and benchmark.current_score(r,by_id[r['id']],'sql_analytics')]
        latencies = [r['elapsed_seconds'] for r in rows]
        calls = [c for r in rows for c in r.get('llm_calls',[])]
        instrumented = sum('llm_calls' in r for r in rows)
        supported = [r for r in rows if refs[r['id']]['supported']]
        metrics = {}
        for metric in benchmark.METRICS['sql_analytics']:
            selected = [r for r in scores if r['metric']==metric]
            values = [r['score'] for r in selected if r['score'] is not None]
            metrics[metric] = {'mean':statistics.mean(values) if values else None,
                'scored':len(values), 'not_applicable':sum(r['score'] is None and not r['error'] for r in selected),
                'evaluator_errors':sum(bool(r['error']) for r in selected),'pending':len(rows)-len(selected)}
        expected_cases = len(identifiers) if identifiers is not None else 30
        return {'cases':len(rows), 'expected_cases':expected_cases,
            'generation_pending':expected_cases-len(rows), 'metrics':metrics,
            'outcomes':dict(benchmark.Counter(benchmark.generation_status(r) for r in rows)),
            'supported_clarifications':sum(bool(r['result']['metadata'].get('clarification_required')) for r in supported),
            'supported_cases':len(supported),
            'validation_failures':sum(r['result']['metadata'].get('error_type') in {'SQLValidationError','MetricDefinitionError'}
                and not r['result']['metadata'].get('clarification_required') for r in rows),
            'provider_rate_limit_failures':sum(benchmark.rate_limited(r) for r in rows),
            'query_execution_success':sum(r['result'].get('data',{}).get('query_status')=='executed' for r in rows),
            'latency_seconds':{'p50':statistics.median(latencies) if latencies else None,
                'p95':statistics.quantiles(latencies,n=100,method='inclusive')[94] if len(latencies)>1 else None},
            'llm_calls':{'total':len(calls) if instrumented else None,'per_request':len(calls)/instrumented if instrumented else None,
                         'instrumented_requests':instrumented,
                         'failed_calls':sum(bool(c['error']) for c in calls)},
            'reported_tokens':{key:sum((c.get('usage') or {}).get(key,0) or 0 for c in calls)
                for key in ('input_tokens','output_tokens','total_tokens')},
            'unmetered_calls':sum(c.get('usage') is None for c in calls)}

    data = {'final_application_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'frozen_baseline':cohort(FROZEN),
        'full_comparison':{v:cohort(OUTPUT/v) for v in ('baseline','combined')},
        'verified_live_6ed9a19':cohort(OUTPUT/'live-6ed9a19'),
        'quota_limited_95aa2b3':cohort(OUTPUT/'quota-95aa2b3'),
        'focused_ablation':{v:cohort(OUTPUT/v,focused) for v in VARIANTS},
        'focused_combined_6ed9a19':cohort(OUTPUT/'live-6ed9a19',focused),
        'fixed_numeric_applicability':{'case_ids':sorted(numeric_ids),
            'baseline':cohort(OUTPUT/'baseline',numeric_ids)['metrics']['numerical_accuracy'],
            'live_6ed9a19':cohort(OUTPUT/'live-6ed9a19',numeric_ids)['metrics']['numerical_accuracy']},
        'notes':['No source references, metric formulas, model or judge settings changed.',
            'The 95aa2b3 run stopped after five cases (four daily-quota failures) and is retained separately. Current combined coverage and provider failures are reported in full_comparison.combined.',
            'The earlier complete live cohort without final quota failures is application revision 6ed9a19, before standalone transaction routing and the explicit unreviewed-alias guard.',
            'Supported clarifications are a proxy, not certified unnecessary-clarification labels.',
            'The inherited scorer gives failed supported questions numerical zero before checking numerical applicability. S14 becomes N/A when it executes because its reference contains only identifiers/names. Raw metrics are retained; a supplementary fixed-eligibility numerical comparison excludes date/identifier-only cases in both cohorts.',
            'Latency includes provider retries/cooldowns inside a request, excludes the same 10-second between-request pacing.',
            'Sequential unrandomized runs are descriptive measurements, not a controlled live-performance guarantee.',
            'Token totals include reported successful-call usage only; unavailable usage is counted separately.',
            'Cross-domain aggregate joins remain restricted; do not interpret refusal as absent source data.']}
    benchmark.save(OUTPUT/'comparison.json',data)
    print(json.dumps(data,indent=2))


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=VARIANTS, default='combined')
    parser.add_argument('--stage',choices=('verify','generate','score','summary','comparison'),default='generate')
    parser.add_argument('--ids',nargs='*',default=[])
    args = parser.parse_args()
    if args.stage == 'comparison':
        comparison()
        return
    if args.stage == 'verify':
        await verify_snapshot()
        return
    benchmark.OUT = prepare(args.variant)
    install_variant(args.variant)
    if args.stage == 'generate':
        from core.llm.groq_provider import GroqProvider
        original = GroqProvider.generate
        calls = []

        def measured(provider, prompt, **kwargs):
            call = {'usage':None, 'error':None, 'response':None}
            calls.append(call)
            try:
                answer = original(provider,prompt,**kwargs)
                call['usage'] = provider.last_usage
                call['response'] = answer
                return answer
            except Exception as error:
                call['error'] = type(error).__name__
                raise

        GroqProvider.generate = measured
        append = benchmark.append

        def checkpoint(path,row):
            if path.name == 'generations.jsonl':
                row['llm_calls'] = list(calls)
                row['llm_call_count'] = len(calls)
                calls.clear()
            append(path,row)
            if path.name == 'generations.jsonl':
                # Outside request timing/deadlines; avoid competing for the shared provider quotas.
                time.sleep(8)  # Original runner adds another two seconds.

        benchmark.append = checkpoint
        await benchmark.generate(('sql_analytics',),set(args.ids))
    elif args.stage == 'score':
        await benchmark.score(('sql_analytics',),set(args.ids))
    benchmark.summarize()


if __name__ == '__main__':
    asyncio.run(main())
