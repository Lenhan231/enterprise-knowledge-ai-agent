"""Evaluate an isolated raw-field hybrid; reuse frozen scorers and replay unchanged paths."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/evaluation/sql-hybrid-2026-11-04'
BASELINE=ROOT/'artifacts/evaluation/sql-single-pass-2026-11-04/production'
CASES=[
    ('F01','inventory_metadata',"List recorded snapshot_date, product_id, year and month from commerce.inventory where snapshot_date='2022-12-31' order by product_id asc limit 10.",
     "SELECT i.snapshot_date,i.product_id,i.year,i.month FROM commerce.inventory i WHERE i.snapshot_date=DATE '2022-12-31' ORDER BY i.product_id,i.snapshot_date LIMIT 10"),
    ('F02','inventory_metadata',"List snapshot_date, product_id from commerce.inventory where snapshot_date>='2022-11-01' and snapshot_date<'2023-01-01' and product_id in (1,3) order by snapshot_date asc, product_id asc limit 20.",
     "SELECT i.snapshot_date,i.product_id FROM commerce.inventory i WHERE i.snapshot_date>=DATE '2022-11-01' AND i.snapshot_date<DATE '2023-01-01' AND i.product_id IN (1,3) ORDER BY i.snapshot_date,i.product_id LIMIT 20"),
    ('F03','product_numeric',"List product_id, product_name, color, price from commerce.products where color='blue' order by price desc, product_id asc limit 5.",
     "SELECT p.product_id,p.product_name,p.color,p.price FROM commerce.products p WHERE p.color='blue' ORDER BY p.price DESC,p.product_id LIMIT 5"),
    ('F04','product_numeric',"List product_id, category, size, price from commerce.products where product_id in (1,3) and price>=0 order by price asc, product_id asc limit 10.",
     "SELECT p.product_id,p.category,p.size,p.price FROM commerce.products p WHERE p.product_id IN (1,3) AND p.price>=0 ORDER BY p.price,p.product_id LIMIT 10"),
    ('F05','product_numeric',"List product_id, cogs, price from commerce.products where product_id in (1,3) order by product_id asc limit 10.",
     "SELECT p.product_id,p.cogs,p.price FROM commerce.products p WHERE p.product_id IN (1,3) ORDER BY p.product_id LIMIT 10"),
    ('F06','product_attributes',"List product_id, category, segment from commerce.products where category='Streetwear' order by product_id desc limit 5.",
     "SELECT p.product_id,p.category,p.segment FROM commerce.products p WHERE p.category='Streetwear' ORDER BY p.product_id DESC LIMIT 5"),
]
CATEGORIES={
    'canonical_inventory':['S03','S04','S05','S06','S07','S08','S09','S10','S11','S12','S13','S15','S16'],
    'inventory_diagnostics':['S01','S02','S14','S28'],
    'commerce_analytics':['S17','S18','S19','S20','S21','S22','S24','S25'],
    'cross_domain':['S23','S26','S27'],'unsupported':['S29','S30'],
}


async def freeze(benchmark):
    from core.database.commerce_repository import create_repository_from_env
    from core.analytics.text_to_sql import validate_commerce_sql
    from evaluation.hybrid_field_contract import field_contract
    directory=OUT/'direct-fields';directory.mkdir(parents=True,exist_ok=True)
    assert not (directory/'oracles.json').exists(),'Frozen field oracles already exist; do not overwrite'
    repo=await create_repository_from_env();references={}
    try:
        for key,category,question,sql in CASES:
            assert field_contract(question) is not None
            validate_commerce_sql(sql)
            rows=json.loads(benchmark.dumps(await repo.execute_approved_query(sql)))
            assert rows,'Positive field fixture unexpectedly empty: '+key
            references[key]=dict(supported=True,expected_behavior='Retrieve exactly the explicit raw fields and source population; no calculations or currency inference.',
                reference=dict(sql=sql,rows=rows,returned_rows=len(rows),detail_ceiling=None))
    finally:
        await repo.close()
    for key,category,question,sql in CASES:
        benchmark.append(directory/'cases.jsonl',dict(id=key,category=category,question=question))
    benchmark.save(directory/'oracles.json',references)
    benchmark.save(directory/'manifest.json',dict(production_base='ac0d8a2',categories=CATEGORIES,
        oracle_status='Separately authored schema-field fixtures; not changes to original frozen references or externally certified gold.',
        sha256={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ['cases.jsonl','oracles.json']}))


async def replay(benchmark):
    from core.agents.sql_analytics_agent import SQLAnalyticsAgent
    from core.models.agents import AgentRequest,VerifiedIdentity
    from core.database.commerce_repository import create_repository_from_env
    from evaluation.hybrid_field_contract import field_contract
    from evaluation.inventory_benchmark_metrics import compare_rows
    rows=list({r['id']:r for r in benchmark.read_jsonl(BASELINE/'sql_analytics/generations.jsonl')}.values())
    assert len(rows)==30
    repo=await create_repository_from_env();results=[]
    try:
        for old in rows:
            assert field_contract(old['question']) is None,'A frozen case entered the new route'
            responses=[c['response'] for c in old['llm_calls'] if c.get('response')]
            class Replay:
                calls=0
                def generate(self,prompt):
                    if self.calls>=len(responses):raise AssertionError('Unexpected extra generation')
                    value=responses[self.calls];self.calls+=1;return value
            provider=Replay();started=time.perf_counter()
            result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question=old['question'],identity=VerifiedIdentity(
                subject='hybrid-replay',permissions={'analytics:read','documents:read'},document_roles={'admin'})))
            new=result.model_dump(mode='json');before=old['result'];a=new['data'];b=before['data']
            same=(new['metadata'].get('execution_status')==before['metadata'].get('execution_status')
                and a.get('sql')==b.get('sql') and a.get('parameters')==b.get('parameters')
                and compare_rows(a.get('rows',[]),b.get('rows',[])) and provider.calls==len(responses)
                and new['answer']==before['answer'])
            results.append(dict(id=old['id'],matches=same,cached_responses=provider.calls,
                status=new['metadata'].get('execution_status'),elapsed_seconds=time.perf_counter()-started))
            print('replay',old['id'],same,flush=True)
    finally:
        await repo.close()
    benchmark.save(OUT/'frozen-replay.json',dict(application_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        method='Captured production responses replayed through hybrid and real read-only repository; no fresh LLM judgments, generation or end-to-end latency claim.',
        new_model_api_calls=0,all_match=all(r['matches'] for r in results),results=results))
    assert all(r['matches'] for r in results),'Do not reuse baseline metrics when replay differs'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['production','hybrid'],default='production')
    parser.add_argument('--stage',choices=['freeze','replay','generate','score'],required=True)
    parser.add_argument('--ids',nargs='+')
    args=parser.parse_args()
    load_dotenv(ROOT/'.env')
    work=ROOT if args.mode=='production' else ROOT/'artifacts/local/sql-hybrid-variant'
    os.chdir(work);sys.path[:0]=[str(work),str(work/'src')]
    from evaluation import run_sql_contract_benchmark as runner
    benchmark=runner.benchmark
    if args.mode=='production':
        assert subprocess.run(['git','diff','--quiet','ac0d8a2','--','src'],cwd=ROOT).returncode==0
    else:
        assert subprocess.check_output(['git','diff','ac0d8a2','--','src'],cwd=work)==(ROOT/'evaluation/sql_hybrid.patch').read_bytes()
        assert (work/'evaluation/hybrid_field_contract.py').read_bytes()==(ROOT/'evaluation/hybrid_field_contract.py').read_bytes()
    if args.stage=='freeze':
        asyncio.run(freeze(benchmark));return
    if args.stage=='replay':
        assert args.mode=='hybrid';asyncio.run(replay(benchmark));return
    output=OUT/args.mode
    def prepare(**kwargs):
        fixtures=OUT/'direct-fields';frozen=json.loads((fixtures/'manifest.json').read_text(encoding='utf-8'))
        for name,digest in frozen['sha256'].items():
            assert hashlib.sha256((fixtures/name).read_bytes()).hexdigest()==digest,'Field fixture changed'
        for group in ['sql_analytics','report']:(output/group).mkdir(parents=True,exist_ok=True)
        for source,target in [(fixtures/'cases.jsonl',output/'sql_analytics/questions.jsonl'),(fixtures/'oracles.json',output/'sql_analytics/references.json'),
            (ROOT/'artifacts/evaluation/agent-benchmarks-2026-11-02/report/references.json',output/'report/references.json'),
            (ROOT/'artifacts/evaluation/agent-benchmarks-2026-11-02/sql_analytics/identity-counts.json',output/'sql_analytics/identity-counts.json')]:
            if target.exists():assert target.read_bytes()==source.read_bytes(),'Frozen working copy changed'
            else:shutil.copyfile(source,target)
        hashes={str(f.relative_to(work)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((work/'src').rglob('*.py'))}
        evaluation_hashes={name:hashlib.sha256((ROOT/'evaluation'/name).read_bytes()).hexdigest() for name in ['hybrid_field_contract.py','sql_hybrid.patch','run_sql_hybrid_evaluation.py']}
        path=output/'manifest.json'
        if path.exists():
            old=json.loads(path.read_text(encoding='utf-8'));assert old['application_source_sha256']==hashes and old['evaluation_source_sha256']==evaluation_hashes,'Use a new output directory for changed code'
        else:
            original=json.loads((BASELINE/'manifest.json').read_text(encoding='utf-8'))
            benchmark.save(path,dict(application_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                application_source_sha256=hashes,evaluation_source_sha256=evaluation_hashes,judge=original['judge'],
                source_sha256=frozen['sha256']['cases.jsonl'],reference_sha256={'sql_analytics':frozen['sha256']['oracles.json']},
                sql_ids=[r[0] for r in CASES],report_ids=[],variant=args.mode,production_base='ac0d8a2'))
        benchmark.OUT=output
    runner.prepare=prepare
    runner.summary=lambda:None
    sys.argv=['hybrid-evaluation','--stage',args.stage,'--group','sql_analytics','--output',str(output),'--retry-provider-errors']
    if args.ids:sys.argv.extend(['--ids',*args.ids])
    asyncio.run(runner.main())


if __name__=='__main__':main()
