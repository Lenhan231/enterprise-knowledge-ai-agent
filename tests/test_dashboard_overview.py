import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dashboards import router
from core.agents.sql.agent import SQLAnalyticsAgent
from core.analytics.text_to_sql import validate_commerce_sql
from core.dashboards.overview import build_overview, OVERVIEW_QUERIES, SNAPSHOT_SQL
from core.dashboards.render import render_dashboard
from core.models.agents import AgentRequest, VerifiedIdentity


class OverviewRepository:
    def __init__(self, *, fail=None, negative=False):
        self.calls=[];self.fail=fail;self.negative=negative
        self.queries={validate_commerce_sql(sql).sql:key for key,sql in OVERVIEW_QUERIES.items()}

    async def execute_approved_query(self, sql, *args):
        self.calls.append((sql,args))
        if sql==validate_commerce_sql(SNAPSHOT_SQL).sql:return [{'snapshot_date':date(2026,11,17)}]
        key=self.queries[sql]
        if key==self.fail:raise ConnectionError('offline')
        return {
            'stock':[{'product_id':1,'product_name':'One','stock_on_hand':Decimal('1234567.5'),'invalid_balances':1 if self.negative else 0},
                     {'product_id':None,'product_name':'Other products','stock_on_hand':10,'invalid_balances':0}],
            'purchases':[{'category':'A','units_purchased':12}],
            'sales':[{'month':date(2026,11,1),'revenue':Decimal('1234567.5')},{'month':date(2026,10,1),'revenue':Decimal('500.25')}],
        }[key]


def identity(allowed=True):
    return AgentRequest(question='Business overview',identity=VerifiedIdentity(subject='overview-test',permissions={'analytics:read'} if allowed else set()))


class OverviewTest(unittest.IsolatedAsyncioTestCase):
    async def test_browser_overview_lifecycle(self):
        import subprocess
        from pathlib import Path
        result=subprocess.run(['node','--test','tests/test_dashboard_overview.cjs','tests/test_workspace_home.cjs'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)

    async def test_fixed_sql_and_three_chart_layout_without_a_model(self):
        repository=OverviewRepository()
        provider=Mock(side_effect=AssertionError('Overview must not use a model'))
        agent=SQLAnalyticsAgent(repository,inventory_only=False,llm=provider)
        document,charts=await build_overview(agent,identity())
        self.assertEqual([(t.kind,t.span) for t in document.tiles],[('donut',1),('bar',1),('line',2)])
        self.assertEqual(document.status,'complete')
        self.assertEqual(len(charts),3)
        self.assertEqual(len(repository.calls),4)
        self.assertEqual(repository.calls[1][1],(date(2026,11,17),))
        provider.assert_not_called()
        provider.generate.assert_not_called()
        html=render_dashboard(document,charts=charts,saved=False)
        self.assertEqual(html.count('<svg '),3)
        self.assertIn('Other products',html)
        self.assertIn('11/2026',html)
        self.assertIn('1.234.568',html)
        self.assertNotIn('₫',html)
        self.assertNotIn('Saved ',html)
        self.assertIn('grid-template-columns:1fr',html)
        self.assertEqual(document.results[2].payload['rows'][1]['revenue'],1234567.5)

    async def test_authorization_fails_before_query_and_sources_fail_independently(self):
        repository=OverviewRepository(fail='sales')
        agent=SQLAnalyticsAgent(repository,inventory_only=False)
        with self.assertRaises(PermissionError):await build_overview(agent,identity(False))
        self.assertEqual(repository.calls,[])
        document,charts=await build_overview(agent,identity())
        self.assertEqual(document.status,'partial')
        self.assertEqual(len(charts),2)
        self.assertEqual(document.results[2].status,'failed')

    async def test_invalid_stock_never_becomes_a_misleading_composition(self):
        document,charts=await build_overview(SQLAnalyticsAgent(OverviewRepository(negative=True),inventory_only=False),identity())
        self.assertNotIn(document.tiles[0].id,charts)
        self.assertEqual(document.status,'partial')

    async def test_deployment_source_allowlist_remains_in_force(self):
        repository=OverviewRepository()
        document,charts=await build_overview(SQLAnalyticsAgent(repository,inventory_only=True),identity())
        self.assertEqual(set(charts),{'stock'})
        self.assertEqual(len(repository.calls),2)
        self.assertEqual(document.status,'partial')


class OverviewApiTest(unittest.TestCase):
    def test_endpoint_authorizes_and_never_saves_an_overview(self):
        import jwt,os
        from unittest.mock import patch
        secret='overview-test-signing-key-longer-than-32-characters'
        repository=OverviewRepository()
        app=FastAPI();app.include_router(router)
        app.state.agent_router=SimpleNamespace(analytics_agent=SQLAnalyticsAgent(repository,inventory_only=False))
        with patch.dict(os.environ,{'AUTH_SECRET_KEY':secret}),TestClient(app) as client:
            self.assertEqual(client.get('/api/dashboards/overview').status_code,401)
            def token(role):return {'Authorization':'Bearer '+jwt.encode({'sub':'test','role':role,'exp':4102444800},secret,algorithm='HS256')}
            self.assertEqual(client.get('/api/dashboards/overview',headers=token('employee')).status_code,403)
            self.assertEqual(repository.calls,[])
            response=client.get('/api/dashboards/overview',headers=token('operations'))
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(len(response.json()['dashboard']['tiles']),3)
            self.assertNotIn('html_url',response.json())


@unittest.skipUnless(os.getenv('DASHBOARD_OVERVIEW_TEST_URL'),'Opt-in read-only PostgreSQL fixture connection required')
class OverviewSQLTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg
        self.connection=await asyncpg.connect(os.environ['DASHBOARD_OVERVIEW_TEST_URL'],timeout=15)
        self.lock=asyncio.Lock();self.invalid=False

    async def asyncTearDown(self):
        await self.connection.close()

    async def execute_approved_query(self,sql,*args):
        from core.reports.calendar_scope import month_start
        inventory=','.join(f"(DATE '2026-11-17',{i},{'NULL::numeric' if self.invalid and i==1 else str(i)+'::numeric'})" for i in range(1,9))
        inventory+=",(DATE '2025-11-17',1,10000::numeric)"
        sales=','.join(f"(DATE '{month_start(2025,11+i)}',100::numeric)" for i in range(13))
        sales+=",(DATE '2026-11-20',1100::numeric)"
        fixtures={
            'inventory':('snapshot_date,product_id,stock_on_hand',inventory),
            'products':('product_id,product_name,category',','.join(f"({i},'Product {i}','{'A' if i<5 else 'B'}')" for i in range(1,9))),
            'orders':('order_id,order_status',"(1,'delivered'),(2,'pending')"),
            'order_items':('order_id,product_id,quantity','(1,1,3),(1,2,2),(1,5,7),(2,1,1000)'),
            'sales':('date,revenue',sales),
        }
        validate_commerce_sql(sql)
        definitions=[]
        for name,(columns,values) in fixtures.items():
            if 'commerce.'+name not in sql:continue
            definitions.append(f'fixture_{name} ({columns}) AS (VALUES {values})')
            sql=sql.replace('commerce.'+name,'fixture_'+name)
        if sql.lstrip().upper().startswith('WITH '):
            sql='WITH '+','.join(definitions)+','+sql.lstrip()[5:]
        else:sql='WITH '+','.join(definitions)+' '+sql
        async with self.lock,self.connection.transaction(readonly=True):
            return [dict(row) for row in await self.connection.fetch(sql,*args)]

    async def test_top_five_other_delivered_quantities_and_latest_twelve_months(self):
        document,charts=await build_overview(SQLAnalyticsAgent(self,inventory_only=False),identity())
        self.assertEqual(document.status,'complete')
        stock=document.results[0].payload['rows']
        self.assertEqual(len(stock),6)
        self.assertEqual(sum(row['stock_on_hand'] for row in stock),36)
        self.assertEqual(next(row['stock_on_hand'] for row in stock if row['product_id'] is None),6)
        self.assertEqual({row['category']:row['units_purchased'] for row in document.results[1].payload['rows']},{'A':5,'B':7})
        months=document.results[2].payload['rows']
        self.assertEqual(len(months),12)
        self.assertEqual((months[0]['month'],months[-1]['month']),('2025-12-01','2026-11-01'))
        self.assertEqual(months[-1]['revenue'],1200)

    async def test_missing_balances_never_disappear_inside_other(self):
        self.invalid=True
        document,charts=await build_overview(SQLAnalyticsAgent(self,inventory_only=False),identity())
        self.assertEqual(document.status,'partial')
        self.assertNotIn('stock',charts)
        self.assertEqual(len(charts),2)

