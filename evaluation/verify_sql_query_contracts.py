"""Read-only contract conformance fixtures; NOT LLM benchmark generations."""
import asyncio
import json
import subprocess
from sqlglot import exp, parse_one

from evaluation import run_inventory_agents_benchmark as benchmark
from evaluation.inventory_benchmark_metrics import compare_rows
from core.analytics.metric_mapping import compile_inventory_query, decode_metric_mapping
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.metric_validation import validate_metric_definitions
from core.analytics.text_to_sql import APPROVED_COLUMNS, validate_commerce_sql
from core.database.commerce_repository import create_repository_from_env

OUTPUT = benchmark.ROOT/'artifacts/evaluation/sql-semantic-contracts-2026-11-03'


async def main():
    refs = json.loads((benchmark.OUT/'sql_analytics/references.json').read_text(encoding='utf-8'))
    questions = {r['id']:r['question'] for r in benchmark.load_cases('sql_analytics')}
    fixtures = {}
    for key, metrics, dimensions, representation, time, ranking in [
        ('S04',['stock_on_hand'],['category'],'aggregate',{'mode':'snapshot','start':'2022-12-31'},
            {'metric':'stock_on_hand','direction':'desc','limit':200}),
        ('S10',['fill_rate'],['category'],'aggregate',{'mode':'range','start':'2022-12-01','end':'2022-12-31'},None),
        ('S11',['stockout_days'],['product_id','product_name'],'product',
            {'mode':'range','start':'2022-12-01','end':'2022-12-31'}, {'metric':'stockout_days','direction':'desc','limit':200}),
    ]:
        mapping = decode_metric_mapping(json.dumps(dict(metrics=metrics,dimensions=dimensions,
            representation=representation,time=time,ranking=ranking)),questions[key])
        fixtures[key] = compile_inventory_query(mapping)
    for key in ('S20','S23','S26','S27','S28'):
        tree = parse_one(benchmark.bounded_reference_sql(refs[key]['reference']['sql']),read='postgres')
        if key=='S20':
            for node in list(tree.find_all(exp.Coalesce)):
                if isinstance(node.this,exp.Column) and node.this.name=='discount_amount':
                    node.replace(node.this.copy())
        if key=='S23':
            for node in list(tree.args['order'].find_all(exp.Column)):
                if node.name=='returned_to_ordered_ratio':
                    node.replace(exp.Literal.number(4))
        if key in {'S26','S27'}:
            for node in list(tree.find_all(exp.EQ)):
                if isinstance(node.this,exp.Column) and node.this.table=='i' and node.this.name=='snapshot_date':
                    node.replace(parse_one("i.snapshot_date >= DATE '2022-12-01' AND i.snapshot_date < DATE '2023-01-01'",read='postgres'))
        if key=='S26':
            tree.set('expressions',[exp.column('snapshot_date',table='i'),*tree.selects])
            for exists in tree.find_all(exp.Exists):
                for column in exists.find_all(exp.Column):
                    if column.table=='i' and column.name=='product_id':
                        column.set('table',exp.to_identifier('p'))
        if key=='S27':
            tree.selects[0].replace(parse_one('COALESCE(inv.category,ord.category) AS category',read='postgres'))
        if key=='S28':
            for table in tree.find_all(exp.Table):
                table.set('alias',exp.TableAlias(this=exp.to_identifier('i')))
            for column in tree.find_all(exp.Column):
                if not column.table:
                    column.set('table',exp.to_identifier('d' if column.name=='n' else 'i'))
        fixtures[key] = (tree.sql(dialect='postgres'),())
    repo = await create_repository_from_env()
    results = []
    try:
        for key, (sql,params) in fixtures.items():
            validate_commerce_sql(sql)
            validate_metric_definitions(sql,resolve_metric_names(questions[key]),params,APPROVED_COLUMNS,question=questions[key])
            rows = json.loads(benchmark.dumps(await repo.execute_approved_query(sql,*params)))
            gold = refs[key]['reference']['rows']
            keys = set(gold[0]) if gold else set()
            aligned = [{name:r.get(name) for name in keys} for r in rows]
            matches = compare_rows(aligned,gold)
            results.append({'id':key,'rows':len(rows),'reference_matches':matches,'sql':sql,
                            'parameters':list(params)})
            print(key,'contract fixture',matches,flush=True)
        # Replay the earlier valid S14 planner output against the current validator/database.
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest, VerifiedIdentity
        prior = next(r for r in benchmark.read_jsonl(OUTPUT/'final/sql_analytics/generations.jsonl') if r['id']=='S14')
        responses = iter(c['response'] for c in prior['llm_calls'] if c.get('response'))
        class ReplayProvider:
            def generate(self,prompt):
                return next(responses)
        result = await SQLAnalyticsAgent(repo,llm=ReplayProvider()).run(AgentRequest(question=questions['S14'],
            identity=VerifiedIdentity(subject='contract-verification',permissions={'analytics:read'})))
        results.append({'id':'S14','replayed_provider_output':True,'execution_status':result.metadata['execution_status'],
                        'reference_matches':compare_rows(result.data['rows'],refs['S14']['reference']['rows'])})
    finally:
        await repo.close()
    benchmark.save(OUTPUT/'contract-verification.json', {'revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'method':'Constructed/replayed contract fixtures executed through SQL validation and the read-only repository; not new LLM generations or benchmark accuracy.',
        'results':results,'all_match':all(r['reference_matches'] for r in results)})
    assert all(r['reference_matches'] for r in results), 'Inspect conformance mismatches; never overwrite frozen gold.'


if __name__=='__main__':
    asyncio.run(main())
