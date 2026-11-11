import hashlib,json,time
from pathlib import Path
import httpx
from dotenv import dotenv_values
out=Path('artifacts/evaluation/inventory-sql-only-2026-11-05')
cohort=Path('C:/Users/Admin/Desktop/FA2026/enterprise-knowledge-ai-agent/artifacts/evaluation/inventory-demo-2026-11-04/final/sql_analytics/generations.jsonl')
ids={'I11','I12','I13','I14','I15'}
cases=[json.loads(s) for s in cohort.read_text(encoding='utf-8').splitlines() if json.loads(s)['id'] in ids]
config=dotenv_values('.env')
# Alias-only changes are acceptable; preserve every row and every cell value.
def canonical(rows):
 return sorted([sorted([str(v) for v in r.values()]) for r in rows])
previous=json.loads((out/'changed-prompts-live.json').read_text(encoding='utf-8')) if (out/'changed-prompts-live.json').exists() else {'cases':[]}
previous={r['id']:r for r in previous['cases']}
results=[]
with httpx.Client(base_url='http://127.0.0.1:19080',timeout=125) as client:
 response=client.post('/api/auth/login',json={'username':config['DEMO_ANALYST_USERNAME'],'password':config['DEMO_ANALYST_PASSWORD']});response.raise_for_status()
 for case in cases:
  prior=previous.get(case['id'])
  if prior and prior['passed']:
   results.append(prior)
   continue
  started=time.perf_counter();response=client.post('/api/agents/chat',json={'agent_mode':'sql','question':case['question']})
  body=response.json();data=body.get('data',{});metadata=body.get('metadata',{});rows=data.get('rows',[])
  checks={'http_200':response.status_code==200,'executed':data.get('query_status')=='executed','inventory_scope':metadata.get('sql_scope')=='inventory','all_cell_values_match_frozen_result':canonical(rows)==canonical(case['result']['data'].get('rows',[]))}
  results.append({'id':case['id'],'question':case['question'],'checks':checks,'elapsed_seconds':round(time.perf_counter()-started,3),'returned_rows':len(rows),'sql':data.get('sql'),'parameters':data.get('parameters'),'error_type':metadata.get('error_type'),'error_code':metadata.get('metric_error_code'),'passed':all(checks.values())})
  if prior: results[-1]['previous_attempts']=[*prior.get('previous_attempts',[]),{k:v for k,v in prior.items() if k!='previous_attempts'}]
  (out/'changed-prompts-live.json').write_text(json.dumps({'revision':'af56d59','method':'Five fresh authenticated SQL requests through container/Nginx; same configured provider and read-only Supabase. All cells compared, ignoring output aliases and unspecified ordering. Not Ragas scoring.','cases':results,'passed':all(r['passed'] for r in results)},indent=2),encoding='utf-8')
  print(case['id'],results[-1]['passed'],metadata.get('error_type'),flush=True)
