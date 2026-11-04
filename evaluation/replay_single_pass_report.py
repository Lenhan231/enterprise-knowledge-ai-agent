"""Read-only Report compatibility replay; no new model calls or Report quality scores."""
import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys

from dotenv import load_dotenv


async def main():
    root=Path(__file__).resolve().parents[1]
    output=root/'artifacts/evaluation/sql-single-pass-2026-11-04'
    work=root/'artifacts/local/sql-single-pass-candidate'
    manifest=json.loads((output/'single-pass-v2/manifest.json').read_text(encoding='utf-8'))
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=work,text=True).strip()==manifest['application_revision']
    assert subprocess.run(['git','diff','--quiet','HEAD','--','src'],cwd=work).returncode==0
    load_dotenv(root/'.env')
    os.chdir(work)
    sys.path[:0]=[str(work),str(work/'src')]
    from core.agents.report_agent import ReportAgent
    from core.agents.sql_analytics_agent import SQLAnalyticsAgent
    from core.database.commerce_repository import create_repository_from_env
    from core.models.agents import AgentRequest,VerifiedIdentity
    from evaluation.run_inventory_agents_benchmark import read_jsonl,save
    from docx import Document
    row=next(r for r in read_jsonl(output/'single-pass-v2/sql_analytics/generations.jsonl') if r['id']=='S09')
    assert row['result']['data'].get('query_status')=='executed','Selected S09 did not execute; do not substitute a passing case'
    class Replay:
        def generate(self,prompt):
            return next(c['response'] for c in reversed(row['llm_calls']) if c.get('response'))
    class Writer:
        async def generate(self,prompt):
            if prompt.startswith('Plan a data-grounded'):
                return json.dumps(dict(purpose='SQL interface integration',tasks=[dict(id='stock',question=row['question'])],
                    sections=[dict(heading='Inventory',tasks=['stock'],table_columns=['snapshot_date','product_id','stock_on_hand'])]))
            fact=json.loads(prompt.split('\nFacts: ')[1].splitlines()[0])[0]
            return json.dumps(dict(sections={'Inventory':f"[{fact['id']}] [{fact['evidence_id']}]"},claims=[fact]))
    repo=await create_repository_from_env()
    results=[]
    try:
        agent=ReportAgent(None,SQLAnalyticsAgent(repo,llm=Replay()),llm=Writer())
        request=AgentRequest(question='Report: '+row['question'],identity=VerifiedIdentity(
            subject='report-compatibility',permissions={'analytics:read','documents:read'},document_roles={'admin'}))
        for format in ['markdown','docx']:
            result,payload,media=await agent.generate_from_template(request,source_mode='analytics',output_format=format)
            assert result.metadata.get('status')=='complete' and payload,result.answer
            assert result.metadata.get('facts'),'No validated facts'
            if format=='docx':
                assert Document(BytesIO(payload)).tables,'No DOCX fact table'
            else:
                (output/'report-compatibility.md').write_bytes(payload)
            results.append(dict(format=format,status=result.metadata['status'],bytes=len(payload),media_type=media,
                                facts=len(result.metadata['facts']),coverage=result.metadata['coverage']))
    finally:
        await repo.close()
    save(output/'report-compatibility.json',dict(application_revision=manifest['application_revision'],case='S09',
        method='Captured single-pass SQL response replayed through the unchanged Report shared-SQL evidence path and real read-only repository; deterministic fact-reference writer.',
        new_model_api_calls=0,quality_benchmark=False,results=results))
    print(json.dumps(results,indent=2))


if __name__=='__main__':
    asyncio.run(main())
