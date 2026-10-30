import copy
import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.analytics.metric_ontology import get_metric_definition, resolve_metric_names
from core.analytics.metric_validation import MetricDefinitionError, validate_metric_definitions
from core.analytics.text_to_sql import APPROVED_COLUMNS, validate_commerce_sql


class InventoryCatalogTest(unittest.TestCase):
    def test_inventory_definitions_have_independent_governance(self):
        definition = get_metric_definition('fill_rate')
        self.assertEqual(definition['version'], '1.0.0')
        self.assertEqual(definition['provenance'], 'team_defined')
        self.assertEqual(definition['approval_status'], 'team_accepted')
        self.assertEqual(definition['business_approval_status'], 'not_recorded')
        self.assertIn('unweighted', definition['description'])

    def test_plural_and_vietnamese_aliases_do_not_add_stock_on_hand(self):
        for question in ('average fill rates in inventory', 'tỷ lệ đáp ứng trung bình trong tồn kho'):
            self.assertEqual(resolve_metric_names(question), {'fill_rate'})
        self.assertEqual(resolve_metric_names('Which products have the lowest fill rates in the latest inventory snapshot?'), {'stored_fill_rate'})
        self.assertEqual(resolve_metric_names('số lượng hàng nhập kho'), {'units_received'})

    def test_catalog_scope_and_schema(self):
        from core.analytics.metric_ontology import load_inventory_catalog
        from core.analytics.text_to_sql import APPROVED_COLUMNS
        catalog = load_inventory_catalog()
        self.assertGreaterEqual(len(catalog), 12)
        for name, definition in catalog.items():
            self.assertEqual(definition['domain'], 'inventory_management')
            for table, columns in definition['source_columns'].items():
                self.assertTrue(set(columns) <= APPROVED_COLUMNS[table], name)
            self.assertTrue(definition['aliases_by_language']['en'])
            self.assertTrue(definition['aliases_by_language']['vi'])
        self.assertNotIn('revenue', catalog)

    def test_prompt_contains_only_relevant_inventory_metric_and_tables(self):
        from core.analytics.text_to_sql import build_sql_prompt
        before = copy.deepcopy(APPROVED_COLUMNS)
        prompt = build_sql_prompt('Which products have lowest fill rates at latest snapshot?')
        self.assertEqual(APPROVED_COLUMNS, before)
        self.assertIn('stored_fill_rate',prompt)
        self.assertNotIn('commerce.payments',prompt)
        self.assertNotIn('reorder_quantity',prompt)
        self.assertNotIn('"average_order_value"',prompt)

    def test_invalid_catalog_duplicate_ids_and_unresolved_formula_are_rejected(self):
        import tempfile
        import yaml
        from core.analytics.metric_ontology import CATALOG_PATH, load_inventory_catalog
        original = yaml.safe_load(CATALOG_PATH.read_text(encoding='utf-8'))
        variants = []
        duplicate = copy.deepcopy(original)
        duplicate['metrics'].append(copy.deepcopy(duplicate['metrics'][0]))
        variants.append(duplicate)
        bad = copy.deepcopy(original)
        bad['metrics'][0]['provenance'] = 'official_because_it_runs'
        variants.append(bad)
        bad = copy.deepcopy(original)
        bad['metrics'][-1]['formula'] = 'SUM(stock_on_hand)'
        variants.append(bad)
        for payload in variants:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bad.yaml'
                path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_inventory_catalog(path)


class InventoryEnforcementTest(unittest.TestCase):
    def check(self, sql, names, question=None):
        validate_commerce_sql(sql)
        return validate_metric_definitions(sql, names, (), APPROVED_COLUMNS, question=question)

    def test_lowest_stored_fill_values_on_latest_snapshot(self):
        sql = ('SELECT i.snapshot_date, p.product_name, i.fill_rate FROM commerce.inventory AS i '
               'JOIN commerce.products AS p ON i.product_id = p.product_id '
               'WHERE i.snapshot_date = (SELECT MAX(j.snapshot_date) FROM commerce.inventory AS j) '
               'ORDER BY 3, 2 LIMIT 10')
        definitions = self.check(sql, {'stored_fill_rate'}, 'Lowest product fill rates at the latest snapshot')
        self.assertEqual(definitions['stored_fill_rate']['aggregation'], 'value')

    def test_every_executable_catalog_formula_passes_both_validators(self):
        from sqlglot import parse_one, exp
        from core.analytics.metric_ontology import load_inventory_catalog
        for name, definition in load_inventory_catalog().items():
            if definition['definition_status'] != 'executable':
                continue
            expression = parse_one(definition['formula'].split(' within ')[0],read='postgres')
            expression = expression.transform(lambda node: exp.column(node.name,table='i') if isinstance(node,exp.Column) else node)
            sql = (f'SELECT i.snapshot_date, {expression.sql(dialect="postgres")} AS {name} '
                   "FROM commerce.inventory AS i WHERE i.snapshot_date='2022-12-31' ")
            if definition['aggregation'] != 'value':
                sql += 'GROUP BY i.snapshot_date '
            with self.subTest(metric=name):
                self.assertIn(name,self.check(sql+'LIMIT 200',{name},'Snapshot on 2022-12-31'))

    def test_category_flag_ratio_preserves_inventory_grain(self):
        sql = ("SELECT i.snapshot_date,p.category,COUNT(i.product_id) FILTER (WHERE i.stockout_flag IS TRUE)::numeric / "
               "NULLIF(COUNT(i.product_id),0) AS stockout_rate FROM commerce.inventory AS i "
               "JOIN commerce.products AS p ON i.product_id=p.product_id "
               "WHERE i.snapshot_date=(SELECT MAX(j.snapshot_date) FROM commerce.inventory AS j) "
               "GROUP BY i.snapshot_date,p.category LIMIT 200")
        self.check(sql,{'stockout_rate'},'Stockout rate by category at latest snapshot')

    def test_flag_rate_zero_denominator_and_missing_product_fixture(self):
        with sqlite3.connect(':memory:') as db:
            db.execute("ATTACH DATABASE ':memory:' AS commerce")
            db.execute('CREATE TABLE commerce.inventory(snapshot_date TEXT, product_id INTEGER, stock_on_hand INTEGER, stockout_flag BOOLEAN)')
            db.executemany('INSERT INTO commerce.inventory VALUES(?,?,?,?)',[('2022-12-31',1,20,True),('2022-12-31',2,40,False)])
            sql = ("SELECT COUNT(i.product_id) FILTER (WHERE i.stockout_flag IS TRUE)::numeric / NULLIF(COUNT(i.product_id),0) AS stockout_rate "
                   "FROM commerce.inventory AS i WHERE i.snapshot_date='2022-12-31' LIMIT 1")
            self.check(sql,{'stockout_rate'})
            # SQLite needs real division; production PostgreSQL uses the validated numeric cast.
            executable = sql.replace('::numeric','*1.0')
            self.assertEqual(db.execute(executable).fetchone(),(0.5,))
            self.assertEqual(db.execute(executable.replace("2022-12-31","2021-12-31")).fetchone(),(None,))
            missing = ("SELECT i.snapshot_date,SUM(i.stock_on_hand) AS stock_on_hand FROM commerce.inventory AS i "
                       "WHERE i.snapshot_date='2022-12-31' AND i.product_id=3 GROUP BY i.snapshot_date LIMIT 1")
            self.check(missing,{'stock_on_hand'},'Stock on hand on 2022-12-31')
            self.assertEqual(db.execute(missing).fetchall(),[])

    def test_unapproved_definitions_and_mislabeled_unresolved_metrics_are_rejected(self):
        from unittest.mock import patch
        from core.analytics.metric_ontology import METRIC_ONTOLOGY
        sql = "SELECT i.snapshot_date,SUM(i.stock_on_hand) FROM commerce.inventory AS i WHERE i.snapshot_date='2022-12-31' GROUP BY i.snapshot_date LIMIT 1"
        with patch.dict(METRIC_ONTOLOGY,{'stock_on_hand':{**get_metric_definition('stock_on_hand'),'approval_status':'unreviewed'}}):
            with self.assertRaises(MetricDefinitionError) as error:
                self.check(sql,{'stock_on_hand'})
            self.assertEqual(error.exception.code,'metric_unapproved')
        wrong = "SELECT i.snapshot_date,AVG(i.fill_rate) AS demand_weighted_fill_rate FROM commerce.inventory AS i WHERE i.snapshot_date='2022-12-31' GROUP BY i.snapshot_date LIMIT 1"
        with self.assertRaises(MetricDefinitionError):
            self.check(wrong,{'fill_rate'})

    def test_inventory_aggregates_calculate_fixture_values_without_cross_date_sum(self):
        with sqlite3.connect(':memory:') as db:
            db.execute("ATTACH DATABASE ':memory:' AS commerce")
            db.execute('CREATE TABLE commerce.inventory(snapshot_date TEXT, product_id INTEGER, stock_on_hand INTEGER, fill_rate NUMERIC)')
            db.executemany('INSERT INTO commerce.inventory VALUES(?,?,?,?)',
                           [('2022-11-30',1,100,0.1),('2022-12-31',1,20,0.2),('2022-12-31',2,40,0.8)])
            sql = ('SELECT i.snapshot_date, SUM(i.stock_on_hand) AS stock_on_hand, AVG(i.fill_rate) AS fill_rate '
                   'FROM commerce.inventory AS i WHERE i.snapshot_date = '
                   '(SELECT MAX(j.snapshot_date) FROM commerce.inventory AS j) GROUP BY i.snapshot_date LIMIT 1')
            self.check(sql, {'stock_on_hand','fill_rate'}, 'Stock on hand and average fill rate at latest snapshot')
            self.assertEqual(db.execute(sql).fetchall(), [('2022-12-31',60,0.5)])
        with self.assertRaises(MetricDefinitionError):
            validate_metric_definitions('SELECT SUM(i.stock_on_hand) FROM commerce.inventory AS i LIMIT 1',
                                        {'stock_on_hand'}, (), APPROVED_COLUMNS)

    def test_unsafe_or_unrelated_snapshot_proof_and_wrong_date_are_rejected(self):
        queries = [
            "SELECT SUM(i.stock_on_hand) FROM commerce.inventory AS i WHERE i.snapshot_date='2022-12-31' OR i.category='Outdoor' LIMIT 1",
            "SELECT i.snapshot_date, SUM(i.stock_on_hand) FROM commerce.inventory AS i WHERE i.snapshot_date=(SELECT MAX(s.date) FROM commerce.sales AS s) GROUP BY i.snapshot_date LIMIT 1",
        ]
        for sql in queries:
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                self.check(sql, {'stock_on_hand'}, 'Stock on hand at the latest snapshot')
        sql = "SELECT i.snapshot_date, SUM(i.stock_on_hand) FROM commerce.inventory AS i WHERE i.snapshot_date='2021-12-31' GROUP BY 1 LIMIT 1"
        with self.assertRaises(MetricDefinitionError) as error:
            self.check(sql, {'stock_on_hand'}, 'Stock on hand on 2022-12-31')
        self.assertEqual(error.exception.code, 'invalid_date_scope')
        valid_year = ("SELECT i.snapshot_date,SUM(i.stock_on_hand) FROM commerce.inventory AS i "
                      "WHERE EXTRACT(YEAR FROM i.snapshot_date)=2022 GROUP BY i.snapshot_date LIMIT 200")
        self.check(valid_year,{'stock_on_hand'},'Stock on hand by snapshot for 2022')
        for predicate in ("i.snapshot_date='2022-12-31'",
                          "i.snapshot_date>='2022-06-01' AND i.snapshot_date<'2023-01-01'"):
            with self.assertRaises(MetricDefinitionError):
                self.check(f'SELECT i.snapshot_date,SUM(i.stock_on_hand) FROM commerce.inventory AS i WHERE {predicate} GROUP BY i.snapshot_date LIMIT 200',
                           {'stock_on_hand'},'Stock on hand by snapshot for 2022')
        self.check("SELECT i.snapshot_date,SUM(i.stock_on_hand) FROM commerce.inventory AS i "
                   "WHERE '2022-01-01'<=i.snapshot_date AND '2022-12-31'>=i.snapshot_date GROUP BY i.snapshot_date LIMIT 200",
                   {'stock_on_hand'},'Stock on hand by snapshot for 2022')

    def test_stored_and_aggregate_grains_cannot_be_mixed(self):
        sql = "SELECT i.snapshot_date, i.fill_rate, SUM(i.stock_on_hand) FROM commerce.inventory AS i WHERE i.snapshot_date='2022-12-31' GROUP BY i.snapshot_date,i.fill_rate LIMIT 10"
        with self.assertRaises(MetricDefinitionError) as error:
            self.check(sql, {'stored_fill_rate','stock_on_hand'})
        self.assertEqual(error.exception.code, 'incompatible_grain')

    def test_dimension_and_unknown_inventory_aggregate_rejection(self):
        for sql, names in [
            ("SELECT i.stock_on_hand, AVG(i.fill_rate) FROM commerce.inventory AS i WHERE i.snapshot_date='2022-12-31' GROUP BY i.stock_on_hand LIMIT 10", {'fill_rate'}),
            ("SELECT SUM(i.stock_on_hand)*2 AS invented FROM commerce.inventory AS i WHERE i.snapshot_date='2022-12-31' LIMIT 1", set()),
        ]:
            with self.subTest(sql=sql), self.assertRaises(MetricDefinitionError):
                self.check(sql, names)


class InventoryRequestTest(unittest.IsolatedAsyncioTestCase):
    async def test_report_sources_receive_inventory_semantics_in_both_modes(self):
        from unittest.mock import AsyncMock, Mock
        from core.models.agents import AgentRequest, AgentResult, Evidence, VerifiedIdentity
        from core.models.agent_plan import AgentPlan, AgentTask
        from core.agents.execution import Execution, TaskOutcome
        from core.reports.sources import collect_sources, serialize_context
        request = AgentRequest(question='Inventory snapshot report', identity=VerifiedIdentity(
            subject='test',permissions={'analytics:read','documents:read'},document_roles={'admin'}))
        definition = get_metric_definition('fill_rate')
        result = AgentResult(answer='done',agent='sql',data={'rows':[{'snapshot_date':'2022-12-31','fill_rate':0.5}]},
                             evidence=[Evidence(source_type='database',source='commerce.inventory')],
                             metadata={'ok':True,'metrics':{'fill_rate':definition},'limitations':['Historical observations only.']})
        task = AgentTask(id='s',agent='sql',question=request.question)
        execution = Execution(request,{})
        execution.outcomes['s'] = TaskOutcome(task,'complete',result)
        collected = execution.collected_sources(AgentPlan(objective='inventory',tasks=[task]))
        router = Mock()
        router.collect_sources = AsyncMock(return_value=collected)
        analytics, knowledge = Mock(), Mock()
        analytics.run = AsyncMock(return_value=result)
        for mode in ('analytics','orchestrated'):
            contexts, _, _, _ = await collect_sources(request,['Summary'],mode,knowledge,analytics,source_router=router)
            supplied = json.loads(serialize_context(contexts['Summary']))[0]
            self.assertEqual(supplied['metric_definitions']['fill_rate']['approval_status'],'team_accepted')
            self.assertEqual(supplied['metric_definitions']['fill_rate']['business_approval_status'],'not_recorded')
            self.assertIn('Historical observations only.',supplied['limitations'])

    async def test_unresolved_and_missing_snapshot_clarify_before_generation(self):
        from unittest.mock import AsyncMock, Mock
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        from core.models.agents import AgentRequest, VerifiedIdentity
        for question, code in [('What is the weighted fill rate on 2022-12-31?', 'metric_unresolved'),
                               ('What is stock on hand?', 'snapshot_required'),
                               ('What quantity should we reorder?', 'metric_unresolved')]:
            provider, repository = Mock(), AsyncMock()
            request = AgentRequest(question=question, identity=VerifiedIdentity(subject='test',permissions={'analytics:read'}))
            result = await SQLAnalyticsAgent(repository,llm=provider).run(request)
            self.assertTrue(result.metadata['clarification_required'], question)
            self.assertEqual(result.metadata['metric_error_code'], code)
            provider.generate.assert_not_called()
            repository.execute_approved_query.assert_not_awaited()

    async def test_rbac_still_precedes_catalog_and_provider(self):
        from unittest.mock import AsyncMock, Mock
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent, AnalyticsPermissionDenied
        from core.models.agents import AgentRequest
        provider, repository = Mock(), AsyncMock()
        with self.assertRaises(AnalyticsPermissionDenied):
            await SQLAnalyticsAgent(repository,llm=provider).run(AgentRequest(question='Stock on hand latest snapshot'))
        provider.generate.assert_not_called()
        repository.execute_approved_query.assert_not_awaited()


class InventoryBenchmarkTest(unittest.TestCase):
    def test_numeric_match_is_insufficient_without_formula_and_date_proof(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from scripts.agents.compare_inventory_metrics import score_case
        sql = "SELECT SUM(i.stock_on_hand)*2 AS value FROM commerce.inventory AS i WHERE i.snapshot_date='2022-12-31' LIMIT 1"
        case = {'id':'stock','question':'Stock on hand on 2022-12-31','field':'stock_on_hand','dimensions':[],
                'elapsed_ms':1,'generation_calls':[{'response':json.dumps({'sql':sql})}],
                'result':{'ok':True,'query_status':'executed','sql':sql,'rows':[{'value':60}]}}
        score = score_case(case,{'stock':[{'snapshot_date':'2022-12-31','value':60}]})
        self.assertTrue(score['calculation'])
        self.assertFalse(score['current_semantics'])
        self.assertFalse(score['metric_correct'])

    def test_comparison_requires_same_model_and_cases(self):
        from scripts.agents.compare_inventory_metrics import compare
        before = dict(model='same',temperature=0,reasoning_effort='none',max_output_tokens=1000,
                      case_sha256='same',pace_seconds=20,cases=[])
        with self.assertRaises(ValueError):
            compare(before,{**before,'model':'changed'},{'cases':{}})
