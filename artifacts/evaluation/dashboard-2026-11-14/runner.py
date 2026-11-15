"""50 local executions of the production dashboard build/persist/render path."""
import asyncio, contextvars, hashlib, importlib.metadata, json, os, subprocess, sys, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from dotenv import load_dotenv

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
SOURCE=ROOT/'artifacts/local/publish-dashboard-20261114'
INPUT=Path('C:/Users/Admin/.codex/attachments/61916b8c-dc39-42b0-8cf1-b9fc472f644a/Pasted text.txt')
load_dotenv(ROOT/'.env',override=False)
os.environ.update(SQL_LLM_PROVIDER='cloudflare',SQL_CLOUDFLARE_MODEL='@cf/meta/llama-3.1-8b-instruct',ANALYTICS_SCHEMAS='commerce',ANALYTICS_DATABASE_URL=json.loads((ROOT/'artifacts/local/dashboard-benchmark-connection.json').read_text())['url'])
sys.path.insert(0,str(SOURCE/'src'))
os.chdir(SOURCE)
execution=contextvars.ContextVar('execution',default='setup')
phase=contextvars.ContextVar('phase',default='setup')
lock=threading.Lock()
def encode(v):
 if hasattr(v,'model_dump'): return v.model_dump(mode='json')
 if isinstance(v,(set,frozenset,tuple)): return list(v)
 return str(v)
def write(path,v):
 path.write_text(json.dumps(v,default=encode,ensure_ascii=False,indent=2),encoding='utf-8')
def event(kind,**fields):
 row=dict(execution_id=execution.get(),phase=phase.get(),event=kind,time=datetime.now(timezone.utc).isoformat(),**fields)
 with lock:
  with (OUT/'events.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(row,default=encode,ensure_ascii=False)+'\n')

from core.llm.Cloudflare_provider import CloudflareProvider
from core.llm.groq_provider import GroqProvider
from core.dashboards.agent import DashboardDocumentAgent
from core.dashboards.models import DashboardPlan
from core.analytics.text_to_sql import parse_json_response
from app import dashboards
from app.main import app
from app.agents import _get_runtime
from core.dashboards.store import DashboardStore
from core.dashboards.render import render_dashboard

def record_provider(cls):
 original=cls.generate
 def generate(self,prompt,*a,**kw):
  started=time.perf_counter(); row=dict(provider=cls.__name__,model=self.model_name,temperature=self.temperature,max_tokens=getattr(self,'max_tokens',kw.get('max_output_tokens',1000)),prompt=prompt)
  try:
   raw=original(self,prompt,*a,**kw); row['response']=raw
   if phase.get()=='planner':
    try: DashboardPlan.model_validate(parse_json_response(raw)); row['schema_valid']=True
    except Exception as error: row.update(schema_valid=False,validation_error=str(error))
   return raw
  except Exception as error: row.update(error=str(error),error_type=type(error).__name__); raise
  finally: event('llm',**row,latency_seconds=time.perf_counter()-started)
 cls.generate=generate
record_provider(CloudflareProvider); record_provider(GroqProvider)

class RecordedAgent(DashboardDocumentAgent):
 async def plan(self,description,scope):
  token=phase.set('planner'); started=time.perf_counter()
  try:
   plan=await super().plan(description,scope)
   event('plan',valid=True,plan=plan); return plan
  except BaseException as error: event('plan',valid=False,error=str(error)); raise
  finally: event('planner_timing',latency_seconds=time.perf_counter()-started); phase.reset(token)
dashboards.DashboardDocumentAgent=RecordedAgent

def self_check(cases):
 assert len(cases)==25 and len({c['id'] for c in cases})==25
 assert all(c['en'] and c['vi'] and c['expect'] for c in cases)
 assert len({c['id']+'-'+lang for c in cases for lang in ('en','vi')})==50
 assert 'ộ' in ''.join(c['vi'] for c in cases)
 assert json.loads(json.dumps({'date':datetime.now(timezone.utc)},default=encode))['date']

async def main():
 cases=json.loads(INPUT.read_text(encoding='utf-8-sig')); self_check(cases)
 if not (OUT/'questions.json').exists(): (OUT/'questions.json').write_bytes(INPUT.read_bytes())
 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
 assert commit=='bac3d96dedef3187fde3755a5ce0eaf74609a106'
 if not (OUT/'source.tar.gz').exists(): subprocess.run(['git','archive','--format=tar.gz','-o',str(OUT/'source.tar.gz'),'HEAD','src','data','pyproject.toml','uv.lock'],cwd=SOURCE,check=True)
 snapshot_hash=hashlib.sha256((OUT/'dataset/manifest.json').read_bytes()).hexdigest()
 config=dict(commit=commit,requested_model=os.environ['SQL_CLOUDFLARE_MODEL'],effective_model=CloudflareProvider().model_name,provider='cloudflare',temperature=0,max_tokens=1000,chat_template_kwargs={'enable_thinking':False},sql_fallback=dict(provider='groq',model=os.getenv('GROQ_MODEL','qwen/qwen3.8-27b'),credential_count=sum(bool(v) for k,v in os.environ.items() if k=='GROQ_API_KEY' or k.startswith('GROQ_API_KEY_'))),dataset_manifest_sha256=snapshot_hash,input_sha256=hashlib.sha256(INPUT.read_bytes()).hexdigest(),execution_order='case order; en then vi; sequential dashboards; production concurrency=2 datasets',identity='finance_analyst: analytics:read',local_execution='app.dashboards.build + persist + render; no HTTP authentication or browser timing',started_at=datetime.now(timezone.utc).isoformat(),dependencies={d.metadata['Name']:d.version for d in importlib.metadata.distributions()},external_metric_retrieval='Production retriever retained; any invoked responses captured in events. External knowledge is not snapshot isolated.')
 write(OUT/'config.json',config)
 runtime=await _get_runtime(app); sql=runtime.analytics_agent.sql_agent
 await sql.repository.get_schema()
 repo=sql.repository.repository; original_fetch=repo._fetch
 async def fetch(query,*args):
  started=time.perf_counter(); fields=dict(sql=query,parameters=args,parameter_types=[type(v).__name__ for v in args])
  try:
   rows=await original_fetch(query,*args); event('database',**fields,observations=rows,latency_seconds=time.perf_counter()-started); return rows
  except BaseException as error: event('database',**fields,error=str(error),latency_seconds=time.perf_counter()-started); raise
 repo._fetch=fetch
 original_payload=sql.run_payload
 async def payload(request):
  token=phase.set('sql'); started=time.perf_counter()
  try:
   result=await original_payload(request); event('sql_payload',question=request.question,payload=result,latency_seconds=time.perf_counter()-started); return result
  except BaseException as error: event('sql_payload',question=request.question,error=str(error)); raise
  finally: phase.reset(token)
 sql.run_payload=payload
 original_retrieve=sql.metric_retriever
 async def retrieve(*a,**kw):
  try:
   value=await original_retrieve(*a,**kw); event('metric_retrieval',result=value); return value
  except BaseException as error: event('metric_retrieval',error=str(error)); raise
 sql.metric_retriever=retrieve
 write(OUT/'dataset/discovered_schema.json',await sql.repository.get_schema())
 store=DashboardStore(OUT/'saved_dashboards'); user={'sub':'dashboard-benchmark','role':'finance_analyst'}
 (OUT/'executions').mkdir(exist_ok=True)
 try:
  for case in cases:
   for lang in ('en','vi'):
    identifier=case['id']+'-'+lang; file=OUT/'executions'/(identifier+'.json')
    if file.exists(): continue
    execution.set(identifier); phase.set('build'); started=time.perf_counter()
    result=dict(execution_id=identifier,case_id=case['id'],language=lang,question=case[lang],expect=case['expect'],code_commit=commit,dataset_sha256=snapshot_hash,started_at=datetime.now(timezone.utc).isoformat())
    try:
     doc=await dashboards.build(SimpleNamespace(app=app),user,description=case[lang],scope='')
     doc=dashboards.persist(store,user,doc)
     html=render_dashboard(doc); (OUT/'executions'/(identifier+'.html')).write_text(html,encoding='utf-8')
     result.update(dashboard_status=doc.status,planner_output_valid=True,query_count=len(doc.queries),tile_count=len(doc.tiles),tile_status=doc.tile_status,dashboard=doc.model_dump(mode='json'))
    except Exception as error:
     result.update(dashboard_status='failed',planner_output_valid=False,query_count=0,tile_count=0,tile_status={},error=str(getattr(error,'detail',error)),error_type=type(error).__name__,traceback=traceback.format_exc())
    result['total_latency_seconds']=time.perf_counter()-started
    write(file,result)
    with (OUT/'results.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(result,default=encode,ensure_ascii=False)+'\n')
    print(identifier,result['dashboard_status'],round(result['total_latency_seconds'],2),flush=True)
 finally: await sql.close()
 config['finished_at']=datetime.now(timezone.utc).isoformat(); write(OUT/'config.json',config)
 print('DONE',flush=True)

if __name__=='__main__': asyncio.run(main())
