from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from core.agents.dashboard.agent import DashboardDocumentAgent
from core.agents.dashboard.models import DashboardDocument, QueryResult, QuerySpec, TileSpec
from core.agents.dashboard.presentation import presentation_clarification, reconcile
from core.models.agents import AgentRequest, VerifiedIdentity


def document(units=('sessions', 'units'), measures=('sessions', 'page_views')):
    payload = {'sql': "SELECT DATE_TRUNC('month', w.date) AS month, SUM(w.sessions) AS sessions, SUM(w.page_views) AS page_views FROM commerce.web_traffic w GROUP BY 1 LIMIT 200",
               'rows': [{'month': '2026-01-01', measures[0]: 10, measures[1]: 20},
                        {'month': '2026-02-01', measures[0]: 15, measures[1]: 25}],
               'metadata': {'columns': [{'name': name, 'unit': unit} for name, unit in zip(measures, units)]}}
    if measures != ('sessions', 'page_views'):
        payload['sql'] = "SELECT s.date AS month, s.revenue AS amount, s.cogs AS duration FROM commerce.sales s LIMIT 200"
    return DashboardDocument(title='Monthly observations', description='Monthly observations',
        queries=[QuerySpec(id='q0', question='Monthly observations')],
        results=[QueryResult(id='q0', question='Monthly observations', status='complete', payload=payload)],
        tiles=[TileSpec(id='chart', title='Monthly observations', query_id='q0', kind='line', dimension='month', measures=list(measures))])


class ChartPartitionTest(unittest.TestCase):
    def test_incompatible_measures_split_using_same_observations_and_units(self):
        for units, measures in [(('sessions', 'units'), ('sessions', 'page_views')),
                                (('currency', 'seconds'), ('amount', 'duration'))]:
            with self.subTest(units=units):
                doc = document(units, measures)
                original = deepcopy(doc.results[0].payload)
                reconcile(doc)
                self.assertEqual('complete', doc.status)
                self.assertEqual([[measures[0]], [measures[1]]], [t.measures for t in doc.tiles])
                self.assertEqual(['line', 'line'], [t.kind for t in doc.tiles])
                self.assertEqual(2, len({t.id for t in doc.tiles}))
                self.assertEqual(original, doc.results[0].payload)
                self.assertIsNone(presentation_clarification(doc))
                before = doc.model_dump()
                self.assertEqual(before, reconcile(doc).model_dump())

    def test_compatible_measures_stay_together_and_singletons_still_must_render(self):
        doc = reconcile(document(('count', 'count')))
        self.assertEqual(1, len(doc.tiles))
        broken = document()
        broken.results[0].payload['rows'][1]['month'] = '2026-01-01'
        reconcile(broken)
        self.assertEqual(1, len(broken.tiles))
        self.assertEqual('failed', broken.status)

    def test_limits_preserve_existing_charts_and_offer_valid_separate_alternatives(self):
        for extra in (1, 7):
            doc = document()
            for i in range(extra):
                doc.tiles.append(TileSpec(id=f'existing{i}', title='Existing', query_id='q0',
                    kind='bar' if extra == 1 else 'table', dimension='month', measures=['sessions']))
            reconcile(doc)
            self.assertEqual(extra + 1, len(doc.tiles))
            self.assertIn('separate line charts', presentation_clarification(doc)[1].lower())

    def test_partition_groups_compatible_measures_and_keeps_explicit_single_chart_requests(self):
        doc = document()
        payload = doc.results[0].payload
        payload['sql'] = payload['sql'].replace(' FROM', ', SUM(w.unique_visitors) AS visitors FROM')
        payload['metadata']['columns'].append({'name': 'visitors', 'unit': 'sessions'})
        for row in payload['rows']:
            row['visitors'] = 5
        doc.tiles[0].measures.append('visitors')
        reconcile(doc)
        self.assertEqual([['sessions', 'visitors'], ['page_views']], [t.measures for t in doc.tiles])
        single = document()
        single.description = 'Show both measures in one line chart'
        reconcile(single)
        self.assertEqual(1, len(single.tiles))
        self.assertIsNotNone(presentation_clarification(single))


class ChartPartitionBuildTest(unittest.IsolatedAsyncioTestCase):
    async def test_redundant_automatic_styles_are_consolidated_but_explicit_styles_are_preserved(self):
        for explicit in (False, True):
            payload = document().results[0].payload
            payload.update(ok=True, query_status='executed')
            payload['metadata']['dashboard_outputs'] = [
                {'id': 'output0', 'kind': 'line', 'dimension': 'month', 'measures': ['sessions', 'page_views']},
                {'id': 'output1', 'kind': 'bar', 'dimension': 'month', 'measures': ['sessions', 'page_views']}]
            sql = SimpleNamespace(run_payload=AsyncMock(return_value=payload))
            description = 'Monthly traffic sessions and page views' + (' in a line chart and bar chart' if explicit else '')
            request = AgentRequest(question=description, identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))
            built = await DashboardDocumentAgent(sql).build(request, description)
            if explicit:
                self.assertEqual(['line', 'bar'], [t.kind for t in built.tiles])
            else:
                self.assertEqual('complete', built.status)
                self.assertEqual([['sessions'], ['page_views']], [t.measures for t in built.tiles])
            sql.run_payload.assert_awaited_once()

    async def test_declared_and_automatic_charts_use_one_sql_call(self):
        for declared in (False, True):
            doc = document()
            payload = doc.results[0].payload
            payload.update(ok=True, query_status='executed')
            if declared:
                payload['metadata']['dashboard_outputs'] = [{'id': 'output0', 'kind': 'line', 'dimension': 'month',
                    'measures': ['sessions', 'page_views']}]
            sql = SimpleNamespace(run_payload=AsyncMock(return_value=payload))
            request = AgentRequest(question='Monthly traffic', identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))
            built = await DashboardDocumentAgent(sql).build(request, 'Monthly traffic sessions and page views')
            self.assertEqual('complete', built.status)
            self.assertEqual(2, len(built.tiles))
            self.assertEqual(['q0', 'q0'], [t.query_id for t in built.tiles])
            sql.run_payload.assert_awaited_once()
