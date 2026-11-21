"""Live count intent trials against independently specified count contracts and SQL."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from core.agents.sql.agent import SQLAnalyticsAgent
from core.database.commerce_repository import LazyCommerceRepository
from core.agents.dashboard.agent import DashboardDocumentAgent
from core.llm.groq_provider import GroqProvider
from core.models.agents import AgentRequest, VerifiedIdentity
from scripts.agents.evaluate_count_queries import reference_plan


def trials():
    latest = {'mode': 'latest', 'field': 'snapshot_date'}
    identities = {'alias': 'sku_count', 'kind': 'distinct', 'field': 'product_id'}
    def flagged(alias, field, value):
        return {**identities, 'alias': alias, 'filters': [{'field': field, 'operator': 'eq', 'value': value}]}
    return [
        ('three_sku_counts', 'Create an inventory dashboard showing SKU count and stockout and overstock flag counts for the latest available inventory snapshot.',
         {'source': 'commerce.inventory', 'time': latest, 'counts': [identities, flagged('out_count', 'stockout_flag', True), flagged('over_count', 'overstock_flag', True)]}),
        ('rows_nonnull_distinct', 'Count all inventory rows, non-null product IDs and distinct product IDs at the latest available inventory snapshot.',
         {'source': 'commerce.inventory', 'time': latest, 'counts': [{'alias': 'records', 'kind': 'rows'},
             {'alias': 'known_ids', 'kind': 'nonnull', 'field': 'product_id'}, identities]}),
        ('independent_true_false', 'Count distinct product IDs with stockout_flag=true and count distinct product IDs with overstock_flag=false at the latest available inventory snapshot.',
         {'source': 'commerce.inventory', 'time': latest, 'counts': [flagged('out_count', 'stockout_flag', True), flagged('not_over_count', 'overstock_flag', False)]}),
        ('other_source', 'Count all records, non-null order_id values and distinct order_id values from commerce.orders.',
         {'source': 'commerce.orders', 'time': {'mode': 'all'}, 'counts': [{'alias': 'records', 'kind': 'rows'},
             {'alias': 'known_ids', 'kind': 'nonnull', 'field': 'order_id'}, {'alias': 'identities', 'kind': 'distinct', 'field': 'order_id'}]}),
    ]


def signature(count):
    return (count['kind'], count.get('field'), tuple(sorted(json.dumps(f, sort_keys=True) for f in count.get('filters', []))))


async def evaluate(models):
    report = {'scope': 'One attempt per model per each of four fixed requests; bounded runtime repair allowed.', 'trials': []}
    for model in models:
        for name, question, expected in trials():
            provider = GroqProvider(model=model)
            repo = LazyCommerceRepository()
            sql = SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)
            original = provider.generate
            calls = []
            def traced(prompt, **kwargs):
                attempt = {}; calls.append(attempt)
                try:
                    raw = original(prompt, **kwargs)
                    attempt.update(response=raw, usage=provider.last_usage)
                    return raw
                except Exception as error:
                    attempt['error_type'] = type(error).__name__
                    raise
            provider.generate = traced
            started = time.monotonic()
            trial = {'model': model, 'case': name, 'passed': False}
            try:
                reference = reference_plan(expected)
                expected_rows = await repo.execute_approved_query(reference.sql, *reference.parameters)
                request = AgentRequest(question=question, identity=VerifiedIdentity(subject='count-evaluation', permissions={'analytics:read'}))
                doc = await DashboardDocumentAgent(sql).build(request, question)
                trial.update(status=doc.status, tiles=[t.kind for t in doc.tiles])
                if doc.status == 'complete' and len(doc.results) == 1:
                    result = doc.results[0]
                    spec = result.payload.get('metadata', {}).get('count_query', {})
                    actual = {signature(c): c['alias'] for c in spec.get('counts', [])}
                    target = {signature(c): c['alias'] for c in expected['counts']}
                    trial['semantic_contract_ok'] = (set(actual) == set(target) and spec.get('source') == expected['source']
                        and not spec.get('filters') and not spec.get('dimensions') and spec.get('time', {}).get('mode') == expected['time']['mode'])
                    rows = result.payload.get('rows', [])
                    trial['reference_values_match'] = bool(trial['semantic_contract_ok'] and len(rows) == len(expected_rows) == 1 and
                        all(rows[0][actual[key]] == expected_rows[0][target[key]] for key in target))
                    trial['passed'] = trial['reference_values_match'] and trial['tiles'] == ['kpi'] * len(target)
                else:
                    trial['messages'] = [r.message for r in doc.results]
            except Exception as error:
                trial['error_type'] = type(error).__name__
            finally:
                trial.update(seconds=round(time.monotonic()-started, 2), generation_calls=len(calls), calls=calls)
                report['trials'].append(trial)
                print(json.dumps({k: v for k, v in trial.items() if k != 'calls'}), flush=True)
                await sql.close()
    report['summary'] = {model: {'passed': sum(t['passed'] for t in report['trials'] if t['model'] == model),
                                'total': sum(t['model'] == model for t in report['trials'])} for model in models}
    return report


def main():
    from dotenv import load_dotenv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--models', nargs='+', default=['openai/gpt-oss-20b', 'qwen/qwen3.8-27b'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    report = asyncio.run(evaluate(args.models))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['summary']))


if __name__ == '__main__': main()
