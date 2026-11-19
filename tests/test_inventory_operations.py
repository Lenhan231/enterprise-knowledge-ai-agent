import copy
import hashlib
import json
import sys
import unittest
import os
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.reports.inventory_operations import load_contract, parse_request, evaluate_decisions, validate_report
from core.agents.sql.inventory_report import plans
from core.analytics.text_to_sql import validate_commerce_sql
from core.models.agents import AgentRequest, VerifiedIdentity, Evidence
from unittest.mock import AsyncMock, patch


def request(text='Monthly inventory report May 2026', *, documents=False, analytics=True):
    return AgentRequest(question=text, identity=VerifiedIdentity(subject='inventory-owner',
        permissions=({'analytics:read'} if analytics else set()) | ({'documents:read'} if documents else set()),
        document_roles={'operations'} if documents else set()))


class Repository:
    def __init__(self, scope, snapshot=date(2026,5,31), *, missing=0, flags=(1,1,0), fail=None):
        self.calls = []
        self.snapshot = snapshot
        self.missing = missing
        self.flags = flags
        self.fail = fail
        self.queries = {validate_commerce_sql(plan[0]).sql: key for key,plan in plans(scope, snapshot).items() if plan}

    async def execute_approved_query(self, sql, *args):
        self.calls.append((sql,args))
        if 'MAX(i.snapshot_date)' in sql:
            return [{'snapshot_date': self.snapshot}]
        key = self.queries[sql]
        if self.fail == key: raise ConnectionError('source offline')
        stockout, reorder, overstock = self.flags
        return {
            'snapshot':[dict(observed_products=2, source_count=2, stock_on_hand=17,
                stockout_products=stockout, stockout_flag_pct=50 if stockout else 0,
                reorder_products=reorder, overstock_products=overstock, unmatched_count=0)],
            'coverage':[dict(catalog_count=2+self.missing, missing_count=self.missing)],
            'inventory_flag_distribution':[dict(category='A',stockout_products=stockout,overstock_products=overstock,reorder_products=reorder)],
            'stockout_product_table':[dict(product=12,stockout_products=1)] if stockout else [],
            'inventory_snapshots':[dict(snapshot_date=date(2026,5,31),stockout_products=stockout)],
            'returns':[dict(returned_order_count=2,source_count=3)],
            'shipments':[dict(avg_delivery_days=3.5,source_count=2)],
            'reviews':[dict(avg_review_rating=4.5,source_count=2)],
        }[key]


class InventoryContractTest(unittest.TestCase):
    def test_original_contract_is_byte_preserved(self):
        from core.reports.inventory_operations import CONTRACT_PATH
        self.assertEqual(hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
                         'd7840835e91c77fc43a2056c7e273d918d7652206d5393efabe3ea2cc8d1c914')

    def test_calendar_scope(self):
        for month in ('May', 'July'):
            scope = parse_request(f'Monthly inventory report for {month} 2026')
            self.assertEqual(scope['granularity'], 'month')
            self.assertEqual(scope['dimension'], 'all')
        self.assertEqual(parse_request('Annual inventory report for 2026')['granularity'], 'year')
        self.assertEqual(parse_request('Inventory operations report July 2026 for segment "Core"')['dimension'], 'segment')
        with self.assertRaisesRegex(ValueError,'quoted segment filter'):parse_request('Inventory report July 2026 by segment')
        self.assertEqual(parse_request('Latest inventory snapshot report',latest=date(2026,7,31))['granularity'],'snapshot')
        with self.assertRaises(ValueError): parse_request('Inventory report July 2026 by region')
        for text in ('Inventory report May 2026 for region "North"','Inventory report May 2026 for warehouse North',
                     'Inventory report May 2026 for vendor "A"'):
            with self.assertRaises(ValueError):parse_request(text)

    def test_fail_closed_rules(self):
        report = copy.deepcopy(load_contract()['runtime_output_template'])
        evaluate_decisions(report)
        self.assertEqual([d['triggered'] for d in report['decisions']], [None]*4)
        for m in report['metrics']:
            if m['id'] in {'stockout_products', 'reorder_products', 'overstock_products'}:
                m.update(value=0, status='available', evidence=[{'query_id':'fixture'}])
        evaluate_decisions(report)
        self.assertEqual([d['triggered'] for d in report['decisions']], [False,False,False,None])
        report['data_quality'].update(partial_period=False,missing_or_unmatched_count=0)
        evaluate_decisions(report)
        self.assertEqual([d['triggered'] for d in report['decisions']], [False,False,False,True])
        report['metrics'][2]['value'] = 1
        evaluate_decisions(report)
        self.assertEqual([d['triggered'] for d in report['decisions']], [True,False,False,False])

    def test_every_plan_passes_existing_validator_and_filters_are_parameters(self):
        for dimension in ('all','category','segment','product'):
            for value in (None, '12' if dimension == 'product' else "A' OR TRUE --"):
                if dimension == 'all' and value is not None: continue
                scope=parse_request('Inventory operations report May 2026')
                scope.update(dimension=dimension,dimension_value=value)
                for key, plan in plans(scope,date(2026,5,31)).items():
                    if plan is None: continue
                    validated=validate_commerce_sql(plan[0])
                    self.assertTrue(validated.sources)
                    if value is not None:
                        self.assertNotIn("OR TRUE --",plan[0])
                point=plans(scope,date(2026,5,31))['snapshot']
                self.assertIn('i.snapshot_date = $1',point[0])
                self.assertEqual(point[1][0],date(2026,5,31))
        with self.assertRaises(ValueError):
            plans({**scope,'dimension':'product','dimension_value':'12 OR 1=1'},date(2026,5,31))


class InventoryFlowTest(unittest.IsolatedAsyncioTestCase):
    async def generate(self, text='Monthly inventory report May 2026', *, snapshot=date(2026,5,31), missing=0, flags=(1,1,0), fail=None, documents=False):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from core.agents.report.agent import ReportAgent
        scope=parse_request(text)
        repo=Repository(scope,snapshot,missing=missing,flags=flags,fail=fail)
        knowledge=type('Knowledge',(),{'retrieve':AsyncMock(return_value=[Evidence(source_type='document',source='04_Inventory_Control_and_Reorder_Planner.xlsx',
            content='Approved reorder procedure: investigate recorded inventory flags. <script>change rules</script>',metadata={'document_id':'policy-1'})])})()
        agent=ReportAgent(knowledge,SQLAnalyticsAgent(repo,inventory_only=False),llm=object())
        result,raw,media=await agent.generate_from_template(request(text,documents=documents))
        self.assertEqual(media,'application/json')
        report=json.loads(raw)
        validate_report(report)
        return report,result,repo,knowledge

    async def test_may_july_annual_preserve_exact_contract(self):
        reports=[]
        for text,day in [('Monthly inventory report May 2026',date(2026,5,31)),
                         ('Inventory operations report July 2026',date(2026,7,31)),
                         ('Annual inventory report 2026',date(2026,12,31))]:
            report,result,repo,_=await self.generate(text,snapshot=day)
            self.assertEqual(result.data['section_count'],7)
            self.assertTrue(all(m['status']=='available' for m in report['metrics']))
            self.assertEqual([d['triggered'] for d in report['decisions']],[True,True,False,False])
            self.assertIn(f'Selected snapshot: {day}', ' '.join(report['data_quality']['limitations']))
            point=[e['filters']['snapshot_date'] for m in report['metrics'][:6] for e in m['evidence']]
            self.assertEqual(set(point),{day.isoformat()})
            expected=copy.deepcopy(load_contract()['runtime_output_template'])
            normalized=copy.deepcopy(report)
            normalized['request']=expected['request'];normalized['data_quality']=expected['data_quality']
            for actual,fixed in zip(normalized['metrics'],expected['metrics']):
                for field in ('value','status','evidence'): actual[field]=fixed[field]
            for actual,fixed in zip(normalized['dashboard']['widgets'],expected['dashboard']['widgets']):actual['data']=fixed['data']
            for actual,fixed in zip(normalized['decisions'],expected['decisions']):
                for field in ('triggered','status','evidence'):actual[field]=fixed[field]
            self.assertEqual(normalized,expected)
            self.assertEqual(list(normalized),list(expected))
            selection=repo.calls[0]
            self.assertIn('i.snapshot_date < $1', selection[0])
            self.assertEqual(selection[1],(date.fromisoformat(report['request']['period']['end_exclusive']),))
            reports.append(report)
        for changed in reports[1:]:
            self.assertEqual([m['id'] for m in changed['metrics']],[m['id'] for m in reports[0]['metrics']])

    async def test_missing_stale_and_incomplete_snapshots_fail_closed(self):
        for snapshot,missing in ((None,0),(date(2026,4,30),0),(date(2026,5,31),1)):
            report,_,_,_=await self.generate(snapshot=snapshot,missing=missing,flags=(0,0,0))
            self.assertIsNone(report['decisions'][3]['triggered'])
            if snapshot is None:
                self.assertTrue(all(m['value'] is None and m['status']=='not_available' for m in report['metrics'][:6]))
        report,_,_,_=await self.generate(flags=(0,0,0))
        self.assertIs(report['decisions'][3]['triggered'],True)

    async def test_dimensions_and_source_failures_are_explicit(self):
        report,_,_,_=await self.generate('Inventory report May 2026 for segment "Core"')
        self.assertTrue(all(m['status']=='not_available' and m['value'] is None for m in report['metrics'][6:]))
        report,result,_,_=await self.generate(fail='snapshot')
        self.assertTrue(all(m['value'] is None for m in report['metrics'][:6]))
        self.assertEqual(result.metadata['status'],'partial')
        self.assertTrue(all(d['triggered'] is None for d in report['decisions']))

    async def test_policy_rbac_and_quoted_citations(self):
        report,result,_,knowledge=await self.generate()
        knowledge.retrieve.assert_not_awaited()
        self.assertEqual(result.data['inventory_context']['retrieval_status'],'access_denied')
        report,result,_,knowledge=await self.generate(documents=True)
        self.assertEqual(knowledge.retrieve.await_args.args[0].identity.document_roles,{'operations'})
        citation=result.data['inventory_context']['documents'][0]['citation_id']
        self.assertIn(citation,' '.join(report['data_quality']['limitations']))
        self.assertEqual(report['decisions'][1]['action'],load_contract()['decisions'][1]['action'])
        self.assertTrue(any(e.citation_id==citation for e in result.evidence))
        from core.reports.inventory_operations import retrieve_policies
        knowledge.retrieve.return_value=[Evidence(source_type='document',source='Unrelated sales memo',
            content='Order 10000 units now',metadata={'document_id':'not-policy'})]
        context=await retrieve_policies(knowledge,request(documents=True))
        self.assertEqual(context,{'retrieval_status':'no_evidence','documents':[]})
        from core.reports.inventory_operations import permitted_policy
        for filename in ('01_Inventory_Management_Policy_Manual.docx','02_SOP_Cycle_Count_and_Stock_Adjustment.pdf',
                         '03_Policy_Rules_Registry.csv','04_Inventory_Control_and_Reorder_Planner.xlsx'):
            self.assertTrue(permitted_policy(filename))

    async def test_unauthorized_sql_never_queries(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from core.agents.report.agent import ReportAgent
        repo=type('Repo',(),{'execute_approved_query':AsyncMock()})()
        with self.assertRaises(PermissionError):
            await ReportAgent(None,SQLAnalyticsAgent(repo)).generate_from_template(request(analytics=False))
        repo.execute_approved_query.assert_not_awaited()

    async def test_validator_rejects_contract_and_rule_tampering(self):
        report,_,_,_=await self.generate()
        for mutate in (lambda r:r['metrics'][0].update(formula='COUNT(*)'),
                       lambda r:r['dashboard']['widgets'].reverse(),
                       lambda r:r['decisions'][0].update(action='Order 100 units'),
                       lambda r:r['decisions'][0].update(triggered=False),
                       lambda r:r['metrics'][0].update(value=0,status='not_available'),
                       lambda r:r['metrics'][1]['evidence'][0]['filters'].update(snapshot_date='2027-01-01'),
                       lambda r:r.update(extra='not permitted')):
            changed=copy.deepcopy(report);mutate(changed)
            with self.assertRaises(ValueError):validate_report(changed)

    async def test_adaptive_inventory_risk_still_routes_to_existing_generator(self):
        from core.agents.report.agent import ReportAgent
        req=request('Inventory risk report May 2026').model_copy(update={'metadata':{'report_type':'inventory_risk'}})
        sentinel=('adaptive',b'original','text/markdown')
        with patch('core.reports.generation.generate_planned_report',AsyncMock(return_value=sentinel)):
            self.assertEqual(await ReportAgent(None,None)._generate_from_template(req,source_mode='analytics'),sentinel)
            exact=request('Inventory stock report for 2026-05-31')
            self.assertEqual(await ReportAgent(None,None)._generate_from_template(exact,source_mode='analytics'),sentinel)

    async def test_saved_roundtrip_export_and_policy_reauthorization(self):
        import tempfile
        import fitz
        from core.reports.document import ReportDocument
        from core.reports.store import ReportStore
        from core.reports.export import export_pdf
        from app.reports import scoped_document
        report,result,_,_=await self.generate(documents=True)
        document=ReportDocument(report=report,inventory_context=result.data['inventory_context'])
        with tempfile.TemporaryDirectory() as directory:
            store=ReportStore(directory);saved=store.create('alice',document)
            self.assertEqual(store.get('alice',saved.id).report,report)
            self.assertIsNone(store.get('bob',saved.id))
            with patch('app.reports._accessible_document_ids',return_value=set()):
                scoped=await scoped_document(saved,{'sub':'alice','role':'operations'})
            self.assertEqual(scoped.inventory_context.documents,[])
            self.assertNotIn('change rules',' '.join(scoped.report['data_quality']['limitations']))
            self.assertEqual(scoped.status,'partial')
            pdf=fitz.open(stream=export_pdf(saved),filetype='pdf')
            import unicodedata
            text=unicodedata.normalize('NFKC',' '.join(' '.join(p.get_text() for p in pdf).split()))
            from core.reports.inventory_operations import SECTION_TITLES
            self.assertTrue(all(title in text for title in SECTION_TITLES.values()),text)
            self.assertIn('policy-1',text)
            self.assertNotIn('VND',text)
            edited=saved.model_dump();edited['presentation']['chart_types']={'inventory_snapshots':'bar'}
            with self.assertRaises(ValueError):ReportDocument.model_validate(edited)

    async def test_single_prompt_saved_api_and_both_delivery_apis(self):
        import jwt
        import tempfile
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.reports import router, get_store
        from core.reports.store import ReportStore
        from core.agents.sql.agent import SQLAnalyticsAgent
        from core.agents.report.agent import ReportAgent
        secret='inventory-test-secret-at-least-32-characters'
        headers={'Authorization':'Bearer '+jwt.encode({'sub':'owner','role':'operations','exp':4102444800},secret,algorithm='HS256')}
        repo=type('Repo',(),{'execute_approved_query':AsyncMock(return_value=[])})()
        agent=ReportAgent(None,SQLAnalyticsAgent(repo,inventory_only=False))
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'AUTH_SECRET_KEY':secret}):
            app=FastAPI();app.include_router(router)
            app.dependency_overrides[get_store]=lambda:ReportStore(directory)
            app.state.agent_router=SimpleNamespace(report_agent=agent)
            with TestClient(app) as client:
                response=client.post('/api/reports',json={'question':'Monthly inventory report May 2026'},headers=headers)
                self.assertEqual(response.status_code,201,response.text)
                doc=response.json()['document'];path='/api/reports/'+doc['id']
                self.assertEqual(doc['report']['report_type'],'inventory_operations')
                self.assertEqual(len(doc['presentation']['section_order']),7)
                self.assertEqual(client.get(path,headers=headers).json()['document']['report'],doc['report'])
                self.assertEqual(client.get(path+'/pdf',headers=headers).status_code,200)
                edit=dict(revision=1,title='Inventory May',presentation=doc['presentation'])
                from core.reports.document import ReportPresentation
                self.assertEqual(client.put(path,json={**edit,'presentation':ReportPresentation().model_dump()},headers=headers).status_code,422)
                self.assertEqual(client.put(path,json=edit,headers=headers).status_code,200)
                edit['revision']=2;edit['presentation']['section_order'].reverse()
                self.assertEqual(client.put(path,json=edit,headers=headers).status_code,422)
            from app.agents import router as agent_router
            app=FastAPI();app.include_router(agent_router);app.state.agent_router=SimpleNamespace(report_agent=agent)
            with patch('app.agents._record_agent_run'),TestClient(app) as client:
                response=client.post('/api/agents/report',data={'question':'Inventory report July 2026','report_type':'inventory_operations'},headers=headers)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['report_type'],'inventory_operations')
            from core.agents.main import create_app
            app=create_app(chat_agent=object(),report_agent=agent,identity_resolver=lambda _:request().identity)
            with TestClient(app) as client:
                response=client.post('/api/report',data={'question':'Annual inventory report 2026','report_type':'inventory_operations'})
                self.assertEqual(response.status_code,200,response.text)

    async def test_fixed_inventory_renderer_has_seven_sections_and_five_widgets(self):
        import subprocess
        report,_,_,_=await self.generate(documents=True)
        script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attributes={};}
 append(...children){this.children.push(...children);} replaceChildren(...children){this.children=children;}
 setAttribute(k,v){this.attributes[k]=v;}
}
const document={createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)};
const api=vm.runInNewContext(fs.readFileSync('src/app/static/sales-report.js','utf8')+';SalesPerformanceReport',{document,Intl});
const report=JSON.parse(fs.readFileSync(0,'utf8')), before=JSON.stringify(report),root=new Element('div');
api.render(root,report);
const descendants=n=>[n,...n.children.flatMap(descendants)],nodes=descendants(root);
assert.equal(nodes.filter(n=>n.dataset.sectionId).length,7);
assert.deepEqual(nodes.filter(n=>n.dataset.widgetId).map(n=>[n.dataset.widgetId,n.dataset.chartType]),report.dashboard.widgets.map(w=>[w.id,w.type]));
assert(nodes.some(n=>n.textContent?.includes('<script>change rules</script>')));
assert(!nodes.some(n=>n.tag==='script'));
assert(nodes.filter(n=>n.tag==='a').every(a=>nodes.some(n=>n.id===a.href.slice(1))));
assert.equal(JSON.stringify(report),before);
assert(!nodes.some(n=>n.textContent?.includes('VND')));
'''
        result=subprocess.run(['node','-e',script],input=json.dumps(report),capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode,0,result.stderr)


@unittest.skipUnless(os.getenv('INVENTORY_REPORT_TEST_URL'), 'Opt-in read-only PostgreSQL fixture connection required')
class InventorySQLAccuracyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg
        from core.agents.sql.agent import SQLAnalyticsAgent
        from core.agents.report.agent import ReportAgent
        self.connection=await asyncpg.connect(os.environ['INVENTORY_REPORT_TEST_URL'],timeout=15)
        self.null_flag=False
        self.extra_product=False
        self.empty=False
        self.zero_flags=False
        self.agent=ReportAgent(None,SQLAnalyticsAgent(self,inventory_only=False))

    async def asyncTearDown(self):
        await self.connection.close()

    async def execute_approved_query(self, sql, *args):
        validate_commerce_sql(sql)
        flag='NULL::boolean' if self.null_flag else 'FALSE' if self.zero_flags else 'TRUE'
        fixtures={
            'inventory': ('snapshot_date,product_id,stock_on_hand,stockout_flag,overstock_flag,reorder_flag',
                "(DATE '2026-04-30',1,1000,FALSE,FALSE,FALSE),"
                f"(DATE '2026-05-31',1,0,FALSE,FALSE,FALSE),(DATE '2026-05-31',2,17,{flag},FALSE,{flag}),"
                "(DATE '2026-06-01',1,999,FALSE,FALSE,FALSE),(DATE '2026-07-31',1,20,FALSE,FALSE,FALSE),"
                "(DATE '2027-01-01',1,2000,FALSE,FALSE,FALSE)"),
            'products': ('product_id,product_name,category,segment', "(1,'One','A','Core'),(2,'Two','B','Core')" + (",(3,'Three','C','New')" if self.extra_product else '')),
            'returns': ('return_id,order_id,product_id,return_date', "(1,1,1,DATE '2026-05-01'),(2,1,2,DATE '2026-05-30'),(3,2,1,DATE '2026-06-01')"),
            'shipments': ('order_id,ship_date,delivery_date', "(1,DATE '2026-05-31',DATE '2026-06-05'),(2,DATE '2026-05-20',NULL::date),(3,DATE '2026-06-01',DATE '2026-06-02')"),
            'orders': ('order_id,order_date', "(1,DATE '2026-05-01'),(2,DATE '2026-05-02'),(3,DATE '2026-05-03')"),
            'reviews': ('review_id,product_id,review_date,rating', "(1,1,DATE '2026-05-01',4::numeric),(2,2,DATE '2026-05-31',NULL::numeric),(3,1,DATE '2026-06-01',1::numeric)")}
        definitions=[]
        for table,(columns,values) in fixtures.items():
            if 'commerce.'+table not in sql:continue
            fixture='fixture_'+table
            definitions.append(f'{fixture} ({columns}) AS (SELECT * FROM (VALUES {values}) AS v WHERE {"FALSE" if self.empty else "TRUE"})')
            sql=sql.replace('commerce.'+table,fixture)
        async with self.connection.transaction(readonly=True):
            return [dict(row) for row in await self.connection.fetch('WITH '+','.join(definitions)+' '+sql,*args)]

    async def report(self,text='Monthly inventory report May 2026'):
        _,raw,_=await self.agent.generate_from_template(request(text))
        return json.loads(raw)

    async def test_all_nine_formulas_and_snapshot_cutoffs(self):
        report=await self.report()
        self.assertEqual({m['id']:m['value'] for m in report['metrics']},dict(
            observed_products=2,stock_on_hand=17,stockout_products=1,stockout_flag_pct=50,
            overstock_products=0,reorder_products=1,returned_order_count=1,avg_delivery_days=5,avg_review_rating=4))
        self.assertEqual(report['data_quality']['coverage_end'],'2026-05-31')
        self.assertEqual([d['triggered'] for d in report['decisions']],[True,True,False,False])
        annual=await self.report('Annual inventory report 2026')
        self.assertEqual(annual['data_quality']['coverage_end'],'2026-07-31')
        self.assertEqual(annual['metrics'][1]['value'],20)
        july=await self.report('Inventory operations report July 2026')
        self.assertEqual(july['metrics'][1]['value'],20)
        history=next(w for w in annual['dashboard']['widgets'] if w['id']=='inventory_snapshots')['data']
        self.assertEqual([r['snapshot_date'] for r in history],['2026-04-30','2026-05-31','2026-06-01','2026-07-31'])

    async def test_null_flags_empty_sources_and_missing_catalog_rows(self):
        self.null_flag=True
        report=await self.report()
        metrics={m['id']:m for m in report['metrics']}
        self.assertIsNone(metrics['stockout_products']['value'])
        self.assertIsNone(metrics['stockout_flag_pct']['value'])
        self.assertIsNone(report['decisions'][3]['triggered'])
        self.null_flag=False;self.extra_product=True;self.zero_flags=True
        report=await self.report()
        self.assertEqual(report['data_quality']['missing_or_unmatched_count'],1)
        self.assertIsNone(report['decisions'][3]['triggered'])
        self.empty=True
        report=await self.report()
        self.assertTrue(all(m['value'] is None for m in report['metrics']))
        self.assertTrue(all(d['triggered'] is None for d in report['decisions']))

    async def test_dimension_filters_preserve_observed_flags_and_supported_metrics(self):
        report=await self.report('Inventory report May 2026 for product "1"')
        metrics={m['id']:m for m in report['metrics']}
        self.assertEqual(metrics['stock_on_hand']['value'],0)
        self.assertEqual(metrics['stockout_products']['value'],0)
        self.assertEqual(metrics['avg_review_rating']['value'],4)
        self.assertEqual(metrics['returned_order_count']['status'],'not_available')
        self.assertIs(report['decisions'][3]['triggered'],True)
