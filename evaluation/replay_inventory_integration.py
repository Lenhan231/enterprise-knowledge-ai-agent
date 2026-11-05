"""Replay frozen SQL interpretations through the real repository; never calls an LLM."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time


async def run(args):
    source=args.source.resolve()
    sys.path[:0]=[str(source),str(source/'src')]
    from dotenv import load_dotenv
    load_dotenv(args.env_file)
    os.environ['SQL_INVENTORY_ONLY']='true'
    from core.agents.sql_analytics_agent import SQLAnalyticsAgent
    from core.database.commerce_repository import create_repository_from_env
    from core.models.agents import AgentRequest, VerifiedIdentity
    from datetime import date, datetime
    from decimal import Decimal
    def encode(value):
        if isinstance(value, Decimal): return float(value)
        if isinstance(value, (datetime, date)): return value.isoformat()
        raise TypeError(type(value).__name__)
    def dumps(value):
        return json.dumps(value, ensure_ascii=False, default=encode, allow_nan=False)
    from sqlglot import parse_one
    rows=[json.loads(line) for line in (args.cohort/'sql_analytics/generations.jsonl').read_text(encoding='utf-8').splitlines()]
    digest=lambda value:hashlib.sha256(dumps(value).encode()).hexdigest()
    sql=lambda value:parse_one(value,read='postgres').sql(dialect='postgres') if value else None
    results=[]
    repo=await create_repository_from_env()
    try:
        for row in rows:
            calls=row['llm_calls']
            assert all(c.get('response') and not c.get('error') for c in calls)
            class Replay:
                def __init__(self): self.prompts=[]
                def generate(self,prompt,**kwargs):
                    index=len(self.prompts)
                    self.prompts.append(digest(prompt))
                    assert index<len(calls),'Unexpected additional model call'
                    return calls[index]['response']
            provider=Replay()
            agent=SQLAnalyticsAgent(repo,llm=provider)
            identity=VerifiedIdentity(subject='inventory-integration-replay',permissions={'analytics:read'})
            started=time.perf_counter()
            result=await agent.run(AgentRequest(question=row['question'],identity=identity))
            actual=result.model_dump(mode='json')
            expected=row['result']
            checks={
                'sql':sql(actual['data'].get('sql'))==sql(expected['data'].get('sql')),
                'parameters':actual['data'].get('parameters',[])==expected['data'].get('parameters',[]),
                'rows':actual['data'].get('rows',[])==expected['data'].get('rows',[]),
                'execution_status':actual['metadata'].get('execution_status')==expected['metadata'].get('execution_status'),
                'clarification':actual['metadata'].get('clarification_required',False)==expected['metadata'].get('clarification_required',False),
                'error_code':actual['metadata'].get('metric_error_code')==expected['metadata'].get('metric_error_code'),
                'calls':len(provider.prompts)==len(calls),
            }
            if hasattr(agent,'table_columns'):
                checks['scope']=set(agent.table_columns)=={'commerce.inventory','commerce.products'}
            results.append(dict(id=row['id'],checks=checks,prompt_hashes=provider.prompts,
                row_sha256=digest(actual['data'].get('rows',[])),elapsed_seconds=round(time.perf_counter()-started,3)))
            print(row['id'],all(checks.values()),flush=True)
    finally:
        await repo.close()
    output=dict(method='Frozen response replay with real read-only PostgreSQL. No fresh provider generations or Ragas rescoring; timings measure replay/DB work only.',
        source=str(source),cases=len(results),passed=sum(all(r['checks'].values()) for r in results),results=results)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2),encoding='utf-8')
    assert output['passed']==output['cases'],'Replay regression; inspect output checks'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--cohort',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    asyncio.run(run(parser.parse_args()))
