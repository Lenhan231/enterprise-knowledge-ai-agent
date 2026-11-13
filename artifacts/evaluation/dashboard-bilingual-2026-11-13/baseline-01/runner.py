"""Run unchanged bilingual questions through Dashboard; checkpoint every first attempt."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from itertools import permutations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
YEAR = "o.order_date >= '2022-01-01' AND o.order_date < '2023-01-01'"
REFERENCES = {
    'B01': 'SELECT COUNT(*) AS product_count FROM commerce.products',
    'B02': 'SELECT category, COUNT(*) AS product_count FROM commerce.products GROUP BY category ORDER BY 2 DESC, 1',
    'B03': f'SELECT COUNT(*) AS order_count FROM commerce.orders o WHERE {YEAR}',
    'B04': "SELECT COUNT(*) AS order_count FROM commerce.orders WHERE order_status='delivered'",
    'B05': "SELECT SUM(revenue) AS revenue FROM commerce.sales WHERE date >= '2022-12-01' AND date < '2023-01-01'",
    'B06': "SELECT DATE_TRUNC('month', date)::date AS month, SUM(revenue) AS revenue FROM commerce.sales WHERE date >= '2022-01-01' AND date < '2023-01-01' GROUP BY 1 ORDER BY 1",
    'B07': "SELECT SUM(revenue) AS revenue, SUM(cogs) AS cogs, SUM(revenue-cogs) AS gross_profit FROM commerce.sales WHERE date >= '2022-01-01' AND date < '2023-01-01'",
    'B08': f'SELECT o.order_status, COUNT(*) AS order_count FROM commerce.orders o WHERE {YEAR} GROUP BY 1 ORDER BY 1',
    'B09': f'SELECT c.city, COUNT(*) AS order_count FROM commerce.orders o JOIN commerce.customers c ON c.customer_id=o.customer_id WHERE {YEAR} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 5',
    'B10': f'SELECT o.payment_method, COUNT(*) AS order_count FROM commerce.orders o WHERE {YEAR} GROUP BY 1 ORDER BY 1',
    'B11': "SELECT category, COUNT(*) AS product_count FROM commerce.inventory WHERE snapshot_date='2022-12-31' AND stockout_flag IS TRUE GROUP BY 1 ORDER BY 1",
    'B12': "SELECT product_id, stock_on_hand FROM commerce.inventory WHERE snapshot_date='2022-12-31' ORDER BY stock_on_hand ASC, product_id ASC LIMIT 10",
    'B13': "SELECT traffic_source, SUM(sessions) AS sessions FROM commerce.web_traffic WHERE date >= '2022-01-01' AND date < '2023-01-01' GROUP BY 1 ORDER BY 1",
    'B14': "SELECT DATE_TRUNC('month', date)::date AS month, SUM(page_views) AS page_views FROM commerce.web_traffic WHERE date >= '2022-01-01' AND date < '2023-01-01' GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1",
    'B15': f'SELECT p.category, SUM(i.quantity) AS quantity FROM commerce.orders o JOIN commerce.order_items i ON i.order_id=o.order_id JOIN commerce.products p ON p.product_id=i.product_id WHERE {YEAR} GROUP BY 1 ORDER BY 2 DESC, 1',
    'B16': f'SELECT i.product_id, SUM(i.quantity*i.unit_price-i.discount_amount) AS net_value FROM commerce.orders o JOIN commerce.order_items i ON i.order_id=o.order_id WHERE {YEAR} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 10',
    'B17': f'SELECT COUNT(*) AS customer_count FROM (SELECT o.customer_id FROM commerce.orders o WHERE {YEAR} GROUP BY 1 HAVING COUNT(DISTINCT o.order_id)>=2) c',
    'B18': "SELECT DATE_TRUNC('month', return_date)::date AS month, SUM(return_quantity) AS return_quantity FROM commerce.returns WHERE return_date >= '2022-01-01' AND return_date < '2023-01-01' GROUP BY 1 ORDER BY 1",
    'B19': "SELECT p.category, AVG(r.rating) AS average_rating, COUNT(r.review_id) AS review_count FROM commerce.reviews r JOIN commerce.products p ON p.product_id=r.product_id WHERE r.review_date >= '2022-01-01' AND r.review_date < '2023-01-01' GROUP BY 1 ORDER BY 1",
    'B20': f'SELECT o.order_status, ROUND(COUNT(*)*100.0/NULLIF((SELECT COUNT(*) FROM commerce.orders o WHERE {YEAR}),0),2) AS percentage FROM commerce.orders o WHERE {YEAR} GROUP BY 1 ORDER BY 1',
    'B21': f'SELECT o.customer_id, SUM(i.quantity*i.unit_price-i.discount_amount) AS net_value FROM commerce.orders o JOIN commerce.order_items i ON i.order_id=o.order_id WHERE {YEAR} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 5',
    'B22': "WITH monthly AS (SELECT DATE_TRUNC('month', date)::date AS month, SUM(revenue) AS revenue FROM commerce.sales WHERE date >= '2022-01-01' AND date < '2023-01-01' GROUP BY 1), previous AS (SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS previous_revenue FROM monthly) SELECT month, (revenue-previous_revenue)*100.0/NULLIF(previous_revenue,0) AS growth_percentage FROM previous ORDER BY month",
    'B23': "SELECT category, COUNT(DISTINCT product_id) AS product_count FROM commerce.inventory WHERE snapshot_date='2022-12-31' AND stockout_flag IS TRUE AND reorder_flag IS TRUE GROUP BY 1 ORDER BY 1",
}
ORDERED = {'B02', 'B06', 'B09', 'B12', 'B14', 'B15', 'B16', 'B18', 'B21', 'B22'}
EXTRA = {'B11': {'snapshot_date'}, 'B12': {'snapshot_date', 'product_name', 'category'},
         'B16': {'product_name'}, 'B23': {'snapshot_date'}}


def encode(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=encode, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def comparable(value, month=False):
    if isinstance(value, (date, datetime)):
        value = value.isoformat()
    if month:
        text = str(value)
        if len(text) >= 7 and text[4] == '-':
            return text[:7]
        if isinstance(value, (int, float, Decimal)) or text.isdigit():
            return f'2022-{int(value):02}'
    return value


def equal(left, right):
    if left is None or right is None or isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    try:
        a, b = Decimal(str(left)), Decimal(str(right))
        return a.is_finite() and b.is_finite() and abs(a-b) <= max(Decimal('.000001'), abs(b)*Decimal('.000000001'))
    except Exception:
        return str(left) == str(right)


def match_rows(actual, expected, case_id):
    """Compare values and row associations; expose alias mapping for semantic review."""
    if len(actual) != len(expected):
        return {'value_match': False, 'reason': 'row_count'}
    if not expected:
        return {'value_match': True, 'column_mapping': {}}
    actual_keys = [key for key in actual[0] if key not in EXTRA.get(case_id, set())]
    gold_keys = list(expected[0])
    if len(actual_keys) != len(gold_keys):
        return {'value_match': False, 'reason': 'column_count'}
    for keys in permutations(actual_keys):
        remaining = list(actual)
        matched = True
        for gold in expected:
            positions = range(min(1, len(remaining))) if case_id in ORDERED else range(len(remaining))
            found = next((i for i in positions if all(equal(
                comparable(remaining[i].get(key), name == 'month'), comparable(gold[name], name == 'month'))
                for key, name in zip(keys, gold_keys))), None)
            if found is None:
                matched = False
                break
            remaining.pop(found)
        if matched:
            return {'value_match': True, 'column_mapping': dict(zip(gold_keys, keys))}
    return {'value_match': False, 'reason': 'values_or_required_order'}


def self_test():
    assert match_rows([{'n': 2, 'label': 'A'}], [{'category': 'A', 'count': 2}], 'B02')['value_match']
    assert not match_rows([{'n': 3, 'label': 'A'}], [{'category': 'A', 'count': 2}], 'B02')['value_match']
    assert not match_rows([{'x': 'A', 'n': 2}, {'x': 'B', 'n': 3}],
                          [{'category': 'A', 'count': 3}, {'category': 'B', 'count': 2}], 'B02')['value_match']
    assert not match_rows([{'x': 'B', 'n': 3}, {'x': 'A', 'n': 2}],
                          [{'category': 'A', 'count': 2}, {'category': 'B', 'count': 3}], 'B02')['value_match']
    assert match_rows([{'d': '2022-01-01', 'v': None}], [{'month': '2022-01', 'growth': None}], 'B22')['value_match']
    assert not equal(None, 0)
    assert not equal(True, 1)
    assert len(REFERENCES) == 23
    print('Benchmark scorer self-check passed')


async def run(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    cases = json.loads(args.input.read_text(encoding='utf-8'))['questions']
    if len(cases) != 25 or len({case['id'] for case in cases}) != 25:
        raise ValueError('Expected 25 unique question pairs')
    out = args.output.resolve()
    if out.exists() and not args.resume:
        raise FileExistsError('Use a fresh output directory or --resume')
    out.mkdir(parents=True, exist_ok=True)
    frozen = out / 'source'
    if not frozen.exists():
        shutil.copytree(ROOT / 'src', frozen / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(ROOT / 'data/semantic', frozen / 'data/semantic')
        shutil.copy2(args.input, out / 'questions.json')
        shutil.copy2(__file__, out / 'runner.py')
    if hashlib.sha256(args.input.read_bytes()).digest() != hashlib.sha256((out / 'questions.json').read_bytes()).digest():
        raise ValueError('Input differs from the frozen question set')
    sys.path.insert(0, str(frozen / 'src'))
    from core.agents.dashboard_agent import DashboardAgent
    from core.agents.router import AgentRouter
    from core.agents.sql_analytics_agent import SQLAnalyticsAgent
    from core.database.commerce_repository import create_repository_from_env
    from core.llm.groq_provider import GroqProvider
    from core.models.agents import AgentRequest, VerifiedIdentity

    provider = GroqProvider()
    calls = []
    class RecordedProvider:
        def generate(self, prompt):
            started = time.perf_counter()
            record = {'prompt': prompt}
            try:
                answer = provider.generate(prompt)
                record.update(response=answer, usage=provider.last_usage)
                return answer
            except Exception as error:
                record['error_type'] = type(error).__name__
                raise
            finally:
                record['elapsed_ms'] = round((time.perf_counter()-started)*1000, 2)
                calls.append(record)
        def close(self):
            provider.close()

    manifest_path = out / 'manifest.json'
    if not manifest_path.exists():
        save(manifest_path, {'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
            'source_sha256': {str(path.relative_to(frozen)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in frozen.rglob('*') if path.is_file()},
            'question_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
            'model': provider.model_name, 'temperature': provider.temperature,
            'reasoning_effort': provider.reasoning_effort, 'output_token_cap': 1000,
            'ambiguity_threshold': SQLAnalyticsAgent.JEV_MIN_CLEAR_CONFIDENCE,
            'inventory_only': os.getenv('SQL_INVENTORY_ONLY', 'false'), 'request_timeout_seconds': 120,
            'pace_seconds': args.pace_seconds, 'languages': ['english', 'vietnamese'],
            'question_rewriting': False, 'attempts_per_prompt': 1, 'application_provider_retries': 'unchanged',
            'oracle_note': 'Handwritten reference SELECTs use the same verified read-only role, without generated-SQL restrictions; no reference data is given to the agent.',
            'scoring_note': 'Alias-insensitive numerical/row equivalence; column mappings and raw SQL retained for semantic review. No LLM judge. Chart coverage is limited by unchanged SQL-oriented prompts.'})
    repository = await create_repository_from_env()
    reference_path = out / 'references.json'
    try:
        if not reference_path.exists():
            references = {}
            for case in cases:
                identifier = case['id']
                if identifier in REFERENCES:
                    sql = REFERENCES[identifier]
                    try:
                        rows = await repository._fetch(sql)
                        references[identifier] = {'sql': sql, 'rows': rows}
                    except Exception as error:
                        references[identifier] = {'sql': sql, 'error_type': type(error).__name__}
                else:
                    references[identifier] = {'expected_behavior': case['expected_behavior']}
                save(reference_path, references)
            profile = await repository._fetch("SELECT MAX(snapshot_date) AS latest_inventory, COUNT(*) AS inventory_rows FROM commerce.inventory")
            discounts = await repository._fetch("SELECT COUNT(*) FILTER (WHERE discount_amount IS NULL) AS null_discount_rows FROM commerce.order_items")
            save(out / 'data-profile.json', {'inventory': profile, 'discounts': discounts})
        sql_agent = SQLAnalyticsAgent(repository, llm=RecordedProvider())
        router = AgentRouter(None, None, None, dashboard_agent=DashboardAgent(sql_agent))
        identity = VerifiedIdentity(subject='dashboard-bilingual-benchmark', permissions={'analytics:read'})
        log_path = out / 'generations.jsonl'
        completed = {json.loads(line)['id'] for line in log_path.read_text(encoding='utf-8').splitlines()} if log_path.exists() else set()
        for case in cases:
            for language in ('english', 'vietnamese'):
                identifier = case['id'] + ('-en' if language == 'english' else '-vi')
                if identifier in completed:
                    continue
                started, call_start = time.perf_counter(), len(calls)
                record = {'id': identifier, 'case_id': case['id'], 'language': language,
                          'difficulty': case['difficulty'], 'question': case[language],
                          'expected_behavior': case['expected_behavior']}
                try:
                    result = await router.run_mode(AgentRequest(question=case[language], identity=identity), 'dashboard')
                    record['result'] = result.model_dump(mode='json')
                except Exception as error:
                    record['error_type'] = type(error).__name__
                record.update(elapsed_ms=round((time.perf_counter()-started)*1000, 2), generation_calls=calls[call_start:])
                with log_path.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(record, ensure_ascii=False, default=encode, allow_nan=False)+'\n')
                    stream.flush()
                meta = record.get('result', {}).get('metadata', {})
                print(json.dumps({'id': identifier, 'sql': record.get('result', {}).get('data', {}).get('query_status'),
                                  'chart': meta.get('chart_status'), 'error': record.get('error_type') or meta.get('error_type'),
                                  'elapsed_ms': record['elapsed_ms']}), flush=True)
                await asyncio.sleep(args.pace_seconds)
        save(out / 'completion.json', {'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'prompts': 50})
    finally:
        await repository.close()
        provider.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--pace-seconds', type=float, default=5)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.input or not args.output or not 0 <= args.pace_seconds <= 60:
        parser.error('--input and --output are required; pacing must be between 0 and 60 seconds')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
