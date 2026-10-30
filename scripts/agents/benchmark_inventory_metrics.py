"""Paired inventory-only SQL benchmark; never runs production write probes."""
import argparse
import asyncio
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / 'data/evaluation/inventory_metric_dictionary_cases.json'


async def run(args, source):
    sys.path.insert(0, str(source / 'src'))
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    from core.agents.sql_analytics_agent import SQLAnalyticsAgent
    from core.database.commerce_repository import create_repository_from_env
    from core.llm.groq_provider import GroqProvider
    from core.models.agents import AgentRequest, VerifiedIdentity

    cases = json.loads(CASES.read_text(encoding='utf-8'))
    assert len(cases) == len({case['id'] for case in cases}) == 8
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite benchmark evidence')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    provider = GroqProvider()
    calls = []

    class RecordedProvider:
        def generate(self, prompt):
            started = time.perf_counter()
            record = {'prompt': prompt}
            try:
                raw = provider.generate(prompt)
                record.update(response=raw, usage=provider.last_usage)
                return raw
            except Exception as error:
                record['error_type'] = type(error).__name__
                raise
            finally:
                record['elapsed_ms'] = round((time.perf_counter()-started)*1000, 2)
                calls.append(record)

        def close(self):
            provider.close()

    report = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'source_ref': args.source_ref or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'model': provider.model_name, 'temperature': provider.temperature,
              'reasoning_effort': provider.reasoning_effort, 'max_output_tokens': 1000,
              'case_sha256': hashlib.sha256(CASES.read_bytes()).hexdigest(),
              'pace_seconds': args.pace_seconds, 'write_probes': False,
              'source_sha256': {name: hashlib.sha256((source/name).read_bytes()).hexdigest()
                                for name in ('src/core/analytics/metric_ontology.py', 'src/core/analytics/metric_validation.py',
                                             'src/core/analytics/text_to_sql.py','src/core/agents/sql_analytics_agent.py','src/core/prompts/sql.py')},
              'cases': []}
    try:
        repository = await create_repository_from_env()
    except Exception as error:
        report['blocked_by'] = type(error).__name__
        args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        provider.close()
        raise
    agent = SQLAnalyticsAgent(repository, llm=RecordedProvider())
    identity = VerifiedIdentity(subject='inventory-metric-benchmark', permissions={'analytics:read'})
    try:
        for index, case in enumerate(cases):
            started, first = time.perf_counter(), len(calls)
            result = await agent.run_payload(AgentRequest(question=case['question'], identity=identity))
            report['cases'].append({**case, 'result': result, 'generation_calls': calls[first:],
                                    'elapsed_ms': round((time.perf_counter()-started)*1000, 2)})
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
            print(json.dumps({'id':case['id'],'ok':result.get('ok'), 'code':result.get('metadata',{}).get('metric_error_code'),
                              'rows':len(result.get('rows',[]))}),flush=True)
            if index+1 < len(cases):
                await asyncio.sleep(args.pace_seconds)
    finally:
        await agent.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-ref', help='Run unchanged source from this Git commit in an isolated temporary folder')
    parser.add_argument('--pace-seconds', type=float, default=20)
    args = parser.parse_args()
    if not 0 <= args.pace_seconds <= 60:
        parser.error('pace-seconds must be between 0 and 60')
    with ExitStack() as stack:
        source = ROOT
        if args.source_ref:
            source = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='inventory-metric-baseline-')))
            archive = subprocess.check_output(['git','archive',args.source_ref,'src'],cwd=ROOT)
            with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
                bundle.extractall(source, filter='data')
        asyncio.run(run(args, source))


if __name__ == '__main__':
    main()
