import json, os, time
from pathlib import Path
import httpx
from dotenv import dotenv_values
config=dotenv_values('.env')
out=Path('artifacts/evaluation/inventory-sql-only-2026-11-05')
checks=[]
with httpx.Client(base_url='http://127.0.0.1:19080',timeout=125) as client:
 def check(name,response,status):
  checks.append({'case':name,'status':response.status_code,'passed':response.status_code==status})
  assert response.status_code==status,(name,response.status_code,response.text[:150])
  return response.json()
 check('health',client.get('/health'),200)
 query={'question':'List product_id, product_name from products limit 2','agent_mode':'sql'}
 check('anonymous',client.post('/api/agents/chat',json=query),401)
 for role in ('VIEWER','ANALYST'):
  assert config.get('DEMO_'+role+'_USERNAME') and config.get('DEMO_'+role+'_PASSWORD'), 'Missing configured demo credentials'
  check(role+'_login',client.post('/api/auth/login',json={'username':config['DEMO_'+role+'_USERNAME'],'password':config['DEMO_'+role+'_PASSWORD']}),200)
  if role=='VIEWER':check('viewer_denied',client.post('/api/agents/chat',json=query),403)
 for name,question,mode in [('fields',query['question'],'sql'),('sum','Show total stock_on_hand at snapshot 2022-12-31.','sql'),('comparison','How did stock_on_hand change between 2022-11-30 and 2022-12-31 for product_id=1? Include product_id and product_name.','sql'),('router',query['question'],'auto'),('outside','List order_id from commerce.orders limit 1','sql')]:
  started=time.perf_counter();body=check(name,client.post('/api/agents/chat',json={'question':question,'agent_mode':mode}),200)
  if name=='outside': valid=body.get('metadata',{}).get('metric_error_code')=='outside_inventory_scope'
  elif mode=='auto':valid=any(t.get('agent')=='sql' and t.get('status')=='complete' for t in body.get('metadata',{}).get('task_trace',[]))
  else:valid=body.get('data',{}).get('query_status')=='executed' and body.get('metadata',{}).get('sql_scope')=='inventory'
  checks[-1].update(passed=valid,seconds=round(time.perf_counter()-started,3),error_code=body.get('metadata',{}).get('metric_error_code'))
  print(name,valid,flush=True)
  if not valid: print(body.get('answer','')[:300],flush=True)
 result={'transport':'Docker Compose backend through Nginx on loopback port 19080; real auth, router, provider and read-only Supabase; no mocks','report_generations':0,'checks':checks,'passed':all(x['passed'] for x in checks)}
 (out/'container-http.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print('passed',result['passed'])
