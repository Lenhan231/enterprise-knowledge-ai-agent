"""Consolidate raw traces without treating a completed query as semantic correctness."""
import collections,csv,hashlib,json,statistics
from pathlib import Path
OUT=Path(__file__).resolve().parent
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def dump(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 rows=[read(p) for p in sorted((OUT/'executions').glob('*.json'))]
 events=[json.loads(line) for line in (OUT/'events.jsonl').read_text(encoding='utf-8').splitlines()]
 by_id=collections.defaultdict(list)
 for e in events: by_id[e['execution_id']].append(e)
 for row in rows:
  trace=by_id[row['execution_id']]
  plan_events=[e for e in trace if e['event']=='plan']
  row['planner_output_valid']=bool(plan_events and plan_events[-1]['valid'])
  row['planner_attempts']=[{k:e.get(k) for k in ('schema_valid','validation_error','error','provider','model','latency_seconds')} for e in trace if e['event']=='llm' and e['phase']=='planner']
  row['accepted_plan']=next((e['plan'] for e in plan_events if e.get('valid')),None)
  row['sql_agent_call_count']=sum(e['event']=='sql_payload' for e in trace)
  row['executed_dataset_sql_count']=sum(e['event']=='database' and e['phase']=='sql' for e in trace)
  row['inspection_sql_count']=sum(e['event']=='database' and e['phase']=='planner' for e in trace)
  row['llm_call_count']=sum(e['event']=='llm' for e in trace)
  row['actual_provider_models']=sorted({e['provider']+':'+e['model'] for e in trace if e['event']=='llm'})
  row['source_queries']=[e for e in trace if e['event'] in ('sql_payload','database') and e['phase']=='sql']
  row['error_or_clarification']=row.get('error') or '; '.join(q['id']+': '+q['message'] for q in row.get('dashboard',{}).get('results',[]) if q['status']!='complete')
  dump(OUT/'executions'/(row['execution_id']+'.json'),row)
 dump(OUT/'results.json',rows)
 with (OUT/'results.jsonl').open('w',encoding='utf-8') as f:
  for row in rows: f.write(json.dumps(row,ensure_ascii=False)+'\n')
 fields=['execution_id','language','dashboard_status','planner_output_valid','query_count','sql_agent_call_count','executed_dataset_sql_count','inspection_sql_count','tile_count','llm_call_count','total_latency_seconds','error_or_clarification']
 with (OUT/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
 summary={}
 for lang in ('en','vi'):
  selected=[r for r in rows if r['language']==lang]; latencies=sorted(r['total_latency_seconds'] for r in selected)
  summary[lang]=dict(executions=len(selected),statuses=dict(collections.Counter(r['dashboard_status'] for r in selected)),accepted_plans=sum(r['planner_output_valid'] for r in selected),complete_dashboards=sum(r['dashboard_status']=='complete' for r in selected),latency_mean_seconds=statistics.mean(latencies),latency_median_seconds=statistics.median(latencies),latency_p95_seconds=latencies[min(len(latencies)-1,int(len(latencies)*.95))])
 dump(OUT/'summary.json',summary)
 print(json.dumps(summary,indent=2))
 assert len({r['execution_id'] for r in rows})==len(rows)
 assert all(r['code_commit']==rows[0]['code_commit'] and r['dataset_sha256']==rows[0]['dataset_sha256'] for r in rows)
 if len(rows)==50: assert all(summary[lang]['executions']==25 for lang in ('en','vi'))
if __name__=='__main__': main()
