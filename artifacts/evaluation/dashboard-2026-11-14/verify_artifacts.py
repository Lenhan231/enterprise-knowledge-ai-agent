import asyncio,hashlib,io,json,os
from pathlib import Path
import asyncpg
from dotenv import dotenv_values
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
def read(p): return json.loads(p.read_text(encoding='utf-8'))
async def main():
 cases=read(OUT/'questions.json'); results=read(OUT/'results.json'); config=read(OUT/'config.json')
 assert len(results)==50
 assert {r['execution_id'] for r in results}=={c['id']+'-'+lang for c in cases for lang in ('en','vi')}
 assert all(r['question']==next(c for c in cases if c['id']==r['case_id'])[r['language']] for r in results)
 assert all(r['code_commit']==config['commit'] and r['dataset_sha256']==config['dataset_manifest_sha256'] for r in results)
 assert all({'dashboard_status','planner_output_valid','query_count','tile_count','tile_status','total_latency_seconds','source_queries','planner_attempts'} <= r.keys() for r in results)
 manifest=read(OUT/'dataset/manifest.json')
 conn=await asyncpg.connect(read(ROOT/'artifacts/local/dashboard-benchmark-connection.json')['url'])
 hashes={}
 for t in manifest['tables']:
  buffer=io.BytesIO()
  columns=','.join('"'+c['name'].replace('"','""')+'"' for c in t['columns'])
  await conn.copy_from_query('SELECT '+columns+' FROM commerce."'+t['table']+'"',output=buffer,format='binary')
  hashes[t['table']]=hashlib.sha256(buffer.getvalue()).hexdigest()==t['sha256']
  assert hashes[t['table']],t['table']
 readonly=await conn.fetchval('SHOW default_transaction_read_only')
 assert readonly=='on'; await conn.close()
 secrets=[v for k,v in dotenv_values(ROOT/'.env').items() if v and len(v)>12 and any(word in k.upper() for word in ('KEY','TOKEN','PASSWORD','SECRET','DATABASE_URL'))]
 leaks=[]
 for file in OUT.rglob('*'):
  if file.is_file() and file.suffix in ('.json','.jsonl','.md','.csv','.py','.html'):
   content=file.read_text(encoding='utf-8-sig')
   if any(value in content for value in secrets): leaks.append(str(file.relative_to(OUT)))
 assert not leaks,'Secret text found in artifacts: '+str(leaks)
 result=dict(executions=50,english=25,vietnamese=25,exact_questions=True,fixed_code_config_snapshot=True,post_run_table_hashes_match=hashes,default_transaction_read_only=readonly,secret_scan='passed',schema_parity=read(OUT/'dataset/schema_parity.json'))
 (OUT/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print('Verified 50 executions, snapshot hashes, exact inputs, and secret scan')
if __name__=='__main__': asyncio.run(main())
