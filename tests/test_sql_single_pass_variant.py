import json
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(os.environ.get('SQL_VARIANT_ROOT',ROOT))
sys.path[:0]=[str(SOURCE),str(SOURCE/'src')]

from core.agents.sql_analytics_agent import SQLAnalyticsAgent, AnalyticsPermissionDenied
from core.analytics.metric_validation import MetricDefinitionError
from core.analytics.text_to_sql import decode_query_plan
from core.models.agents import AgentRequest, VerifiedIdentity
from evaluation.sql_single_pass_contract import validate_single_pass_plan
from evaluation.sql_single_pass_contract import requested_metrics

SINGLE=os.environ.get('SQL_VARIANT_MODE')=='single-pass'
OBSERVATIONS=[]
IDENTITY=VerifiedIdentity(subject='evaluation',permissions={'analytics:read','documents:read'})
SQL=("SELECT i.snapshot_date,i.product_id,i.stock_on_hand FROM commerce.inventory i "
     "JOIN commerce.products p ON i.product_id=p.product_id WHERE i.snapshot_date=$1 AND p.color=$2 "
     "ORDER BY 3 DESC NULLS LAST,i.product_id LIMIT 2")
QUESTION="Top 2 products by highest stock_on_hand on 2022-12-31, only color='blue'."
MAPPING=dict(metrics=['stock_on_hand'],dimensions=['product_id'],representation='product',
             time={'mode':'snapshot','start':'2022-12-31'},
             filters=[dict(field='color',operator='eq',value='blue')],
             ranking=dict(metric='stock_on_hand',direction='desc',limit=2))


class ContractTest(unittest.TestCase):
    def test_schema_not_null_values_do_not_require_an_irrelevant_null_order(self):
        plan=decode_query_plan(json.dumps(dict(sql=SQL.replace('DESC NULLS LAST','DESC'),parameters=['2022-12-31','blue'])))
        validate_single_pass_plan(plan,QUESTION,{'stock_on_hand'})

    def test_latest_diagnostic_and_snapshot_subquery_are_not_metric_subqueries(self):
        for sql,question,metrics in [
            ('SELECT MAX(i.snapshot_date) AS latest_snapshot FROM commerce.inventory i','What is the latest available inventory snapshot?',set()),
            (SQL.replace('i.snapshot_date=$1','i.snapshot_date=(SELECT MAX(j.snapshot_date) FROM commerce.inventory j)').replace(' AND p.color=$2','').replace('LIMIT 2','LIMIT 200'),
             'Which products have the highest stock_on_hand at latest snapshot?',{'stock_on_hand'})]:
            validate_single_pass_plan(decode_query_plan(json.dumps(dict(sql=sql,parameters=[]))),question,metrics)

    def test_flag_filter_does_not_become_an_extra_requested_measure(self):
        self.assertEqual(requested_metrics('List products with stockout_flag=true on 2022-12-31 including stockout_days.'),{'stockout_days'})

    def test_unmapped_raw_measure_cannot_substitute_zero_for_null(self):
        sql="SELECT i.snapshot_date,COALESCE(i.days_of_supply,0) AS raw_value FROM commerce.inventory i WHERE i.snapshot_date=$1 LIMIT 200"
        with self.assertRaises(MetricDefinitionError):
            validate_single_pass_plan(decode_query_plan(json.dumps(dict(sql=sql,parameters=['2022-12-31']))),
                'List raw inventory observations on 2022-12-31.',set())

    def test_unmapped_raw_measure_cannot_invent_arithmetic(self):
        sql="SELECT i.snapshot_date,i.stock_on_hand*2 AS raw_value FROM commerce.inventory i WHERE i.snapshot_date=$1 LIMIT 200"
        with self.assertRaises(MetricDefinitionError):
            validate_single_pass_plan(decode_query_plan(json.dumps(dict(sql=sql,parameters=['2022-12-31']))),
                'List raw inventory observations on 2022-12-31.',set())

    def test_explicit_non_null_population(self):
        sql=SQL.replace('stock_on_hand','days_of_supply')
        plan=decode_query_plan(json.dumps(dict(sql=sql,parameters=['2022-12-31','blue'])))
        with self.assertRaises(MetricDefinitionError):
            validate_single_pass_plan(plan,QUESTION.replace('stock_on_hand','non-null days_of_supply'),{'days_of_supply'})

    def test_both_sqlglot_non_null_representations_are_accepted(self):
        for predicate in ['i.days_of_supply IS NOT NULL','NOT i.days_of_supply IS NULL']:
            sql=SQL.replace('stock_on_hand','days_of_supply').replace(' AND p.color=$2',' AND p.color=$2 AND '+predicate)
            validate_single_pass_plan(decode_query_plan(json.dumps(dict(sql=sql,parameters=['2022-12-31','blue']))),
                QUESTION.replace('stock_on_hand','non-null days_of_supply'),{'days_of_supply'})

    def test_dropped_predicate_and_invented_top_n(self):
        for sql,params in [(SQL.replace(' AND p.color=$2',''),['2022-12-31']),
                           (SQL.replace('LIMIT 2','LIMIT 1'),['2022-12-31','blue'])]:
            with self.subTest(sql=sql),self.assertRaises(MetricDefinitionError):
                validate_single_pass_plan(decode_query_plan(json.dumps(dict(sql=sql,parameters=params))),QUESTION,{'stock_on_hand'})


class AgentTest(unittest.IsolatedAsyncioTestCase):
    async def execute(self,sql=SQL,question=QUESTION,parameters=None,identity=IDENTITY,expected_allowed=True):
        provider,repo=Mock(),AsyncMock()
        provider.generate.return_value=json.dumps(dict(sql=sql,parameters=parameters if parameters is not None else ['2022-12-31','blue'])) if SINGLE else json.dumps(MAPPING)
        repo.execute_approved_query.return_value=[dict(snapshot_date='2022-12-31',product_id=1,stock_on_hand=5)]
        agent=SQLAnalyticsAgent(repo,llm=provider)
        with patch('core.agents.sql_analytics_agent.compile_inventory_query',create=True,return_value=(sql,tuple(parameters if parameters is not None else ['2022-12-31','blue']))):
            result=await agent.run(AgentRequest(question=question,identity=identity))
        OBSERVATIONS.append(dict(question=question,sql=sql,expected_allowed=expected_allowed,
            allowed=result.data.get('query_status')=='executed',llm_calls=provider.generate.call_count,
            repository_calls=repo.execute_approved_query.await_count))
        return result,provider,repo

    async def test_rbac_precedes_every_provider_and_repository_call(self):
        provider,repo=Mock(),AsyncMock()
        with self.assertRaises(AnalyticsPermissionDenied):
            await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question=QUESTION,identity=VerifiedIdentity(subject='denied')))
        provider.generate.assert_not_called()
        repo.execute_approved_query.assert_not_awaited()

    async def test_valid_inventory_contract(self):
        result,provider,repo=await self.execute()
        self.assertEqual(result.data.get('query_status'),'executed',result.answer)
        self.assertEqual(provider.generate.call_count,1)
        repo.execute_approved_query.assert_awaited_once()

    async def test_invalid_sql_never_reaches_repository(self):
        cases=[(SQL.replace('stock_on_hand','stock_on_hand*2'),None),
               (SQL,['2021-12-31','blue']),
               (SQL.replace(' AND p.color=$2',''),['2022-12-31']),
               (SQL.replace('DESC NULLS LAST','ASC'),None),
               ('DELETE FROM commerce.inventory',[]),
               ('SELECT s.secret FROM private.secrets s LIMIT 2',[]),
               (SQL.replace('JOIN commerce.products p ON i.product_id=p.product_id',
                    'JOIN commerce.products p ON i.product_id=p.product_id JOIN commerce.returns r ON r.product_id=p.product_id'),None)]
        for sql,params in cases:
            with self.subTest(sql=sql):
                result,provider,repo=await self.execute(sql,parameters=params,expected_allowed=False)
                self.assertNotEqual(result.data.get('query_status'),'executed')
                repo.execute_approved_query.assert_not_awaited()
                self.assertLessEqual(provider.generate.call_count,1)

    async def test_ordinary_inventory_fields_do_not_require_metric_mapping(self):
        sql='SELECT i.snapshot_date,i.product_id,i.year,i.month FROM commerce.inventory i ORDER BY 1,2 LIMIT 200'
        provider,repo=Mock(),AsyncMock()
        if SINGLE:
            provider.generate.return_value=json.dumps(dict(sql=sql,parameters=[]))
        else:
            provider.generate.side_effect=[json.dumps(dict(domain='other')),*[json.dumps(dict(sql=sql,parameters=[]))]*2]
        repo.execute_approved_query.return_value=[]
        result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(
            question='List recorded snapshot_date, product_id, year and month from inventory.',identity=IDENTITY))
        allowed=result.data.get('query_status')=='executed'
        OBSERVATIONS.append(dict(question='ordinary inventory year/month fields',expected_allowed=True,allowed=allowed,
            llm_calls=provider.generate.call_count,repository_calls=repo.execute_approved_query.await_count))
        self.assertEqual(allowed,SINGLE or bool(os.environ.get('SQL_DETERMINISTIC_ROOT')),result.answer)
        if os.environ.get('SQL_DETERMINISTIC_ROOT'):
            provider.generate.assert_not_called()

    async def test_ordinary_product_query(self):
        sql='SELECT p.product_id,p.product_name,p.category FROM commerce.products p ORDER BY 1 LIMIT 200'
        provider,repo=Mock(),AsyncMock()
        provider.generate.return_value=json.dumps(dict(sql=sql,parameters=[]))
        repo.execute_approved_query.return_value=[]
        result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question='List product IDs, names and categories.',identity=IDENTITY))
        self.assertEqual(result.data.get('query_status'),'executed',result.answer)
        self.assertEqual(provider.generate.call_count,1)

    async def test_free_text_filter_loss_is_measured_on_synthetic_rows(self):
        from sqlglot import parse_one
        question='Top 2 blue products by highest stock_on_hand on 2022-12-31.'
        wrong=SQL.replace(' AND p.color=$2','')
        provider,repo=Mock(),AsyncMock()
        provider.generate.return_value=json.dumps(dict(sql=wrong,parameters=['2022-12-31'])) if SINGLE else json.dumps(MAPPING)
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.execute("ATTACH DATABASE ':memory:' AS commerce")
            db.executescript('CREATE TABLE commerce.inventory(snapshot_date TEXT,product_id INT,stock_on_hand INT);'
                'CREATE TABLE commerce.products(product_id INT PRIMARY KEY,color TEXT);'
                "INSERT INTO commerce.inventory VALUES('2022-12-31',1,5),('2022-12-31',2,100);"
                "INSERT INTO commerce.products VALUES(1,'blue'),(2,'red');")
            async def query(sql,*params):
                return [dict(r) for r in db.execute(parse_one(sql,read='postgres').sql(dialect='sqlite'),tuple(str(p) for p in params))]
            repo.execute_approved_query.side_effect=query
            with patch('core.agents.sql_analytics_agent.compile_inventory_query',create=True,return_value=(wrong,('2022-12-31',))):
                result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question=question,identity=IDENTITY))
        ids=[r['product_id'] for r in result.data.get('rows',[])]
        gap=result.data.get('query_status')=='executed' and ids!=[1]
        OBSERVATIONS.append(dict(question=question,expected_ids=[1],returned_ids=ids,
            expected_allowed=False,allowed=result.data.get('query_status')=='executed',semantic_regression=gap,
            llm_calls=provider.generate.call_count,repository_calls=repo.execute_approved_query.await_count))
        self.assertEqual(gap,SINGLE,'Record this tradeoff honestly; do not count it as a security pass.')

    async def test_report_uses_the_agent_as_sql_evidence_in_both_formats(self):
        from core.agents.report_agent import ReportAgent
        from docx import Document
        from io import BytesIO
        sql_provider,repo=Mock(),AsyncMock()
        sql_provider.generate.return_value=json.dumps(dict(sql=SQL,parameters=['2022-12-31','blue'])) if SINGLE else json.dumps(MAPPING)
        repo.execute_approved_query.return_value=[dict(snapshot_date='2022-12-31',product_id=1,stock_on_hand=5)]
        class Writer:
            async def generate(self,prompt):
                if prompt.startswith('Plan a data-grounded'):
                    return json.dumps(dict(purpose='Inventory evaluation',tasks=[dict(id='stock',question=QUESTION)],
                        sections=[dict(heading='Inventory',tasks=['stock'],table_columns=['snapshot_date','product_id','stock_on_hand'])]))
                fact=json.loads(prompt.split('\nFacts: ')[1].splitlines()[0])[0]
                return json.dumps(dict(sections={'Inventory':f"[{fact['id']}] [{fact['evidence_id']}]"},claims=[fact]))
        sql_agent=SQLAnalyticsAgent(repo,llm=sql_provider)
        for format in ['markdown','docx']:
            with patch('core.agents.sql_analytics_agent.compile_inventory_query',create=True,return_value=(SQL,('2022-12-31','blue'))):
                result,payload,_=await ReportAgent(AsyncMock(),sql_agent,llm=Writer()).generate_from_template(
                    AgentRequest(question='Report: '+QUESTION,identity=IDENTITY),source_mode='analytics',output_format=format)
            self.assertTrue(payload,result.answer)
            self.assertTrue(result.metadata.get('facts'))
            self.assertEqual(result.metadata['status'],'complete',result.metadata)
            OBSERVATIONS.append(dict(report_format=format,status=result.metadata['status'],facts=len(result.metadata['facts'])))
            if format=='docx':
                self.assertTrue(Document(BytesIO(payload)).tables)
        self.assertEqual(sql_provider.generate.call_count,2)
