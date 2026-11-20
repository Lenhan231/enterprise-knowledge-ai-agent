"""The upstream SQL runtime needs no Jev service or OpenRouter credential."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.agents.sql.agent import SQLAnalyticsAgent
from core.agents.dashboard.agent import DashboardDocumentAgent
from core.models.agents import AgentRequest, VerifiedIdentity


class UpstreamSQLRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_chart_contract_survives_sql_validation_and_execution(self):
        from core.agents.dashboard.models import ClarificationTurn
        from core.agents.dashboard.render import render_dashboard
        contract = {'columns': ['month', 'sessions', 'page_views'], 'dimensions': ['month'], 'chart_type': None,
            'charts': [{'type': 'line', 'dimension': 'month', 'measures': ['sessions']},
                       {'type': 'bar', 'dimension': 'month', 'measures': ['page_views']}]}
        provider = SimpleNamespace(generate=Mock(return_value=json.dumps({
            'sql': "SELECT DATE_TRUNC('month', w.date) AS month, SUM(w.sessions) AS sessions, SUM(w.page_views) AS page_views FROM commerce.web_traffic w WHERE w.date >= $1 AND w.date < $2 GROUP BY 1 ORDER BY 1 LIMIT 200",
            'parameters': ['2026-01-01', '2026-06-01'], 'request_contract': contract,
            'outputs': [{'kind': 'line', 'query': 0, 'dimension': 'month', 'measures': ['sessions']},
                        {'kind': 'bar', 'query': 0, 'dimension': 'month', 'measures': ['page_views']}]})))
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[
            {'month': '2026-01-01', 'sessions': 10, 'page_views': 20},
            {'month': '2026-02-01', 'sessions': 15, 'page_views': 40}]))
        request = AgentRequest(question='Dashboard', identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))
        doc = await DashboardDocumentAgent(SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)).build(
            request, 'A line chart of sessions and a bar chart of page views', clarifications=[
                ClarificationTurn(question='What grain and period?', reply='Monthly, January through May 2026')])
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['line', 'bar'], [t.kind for t in doc.tiles])
        self.assertEqual(contract, doc.results[0].payload['metadata']['request_contract'])
        self.assertNotIn('Chart unavailable', render_dashboard(doc))
        self.assertEqual(1, render_dashboard(doc).count('<table>'))
        provider.generate.assert_called_once()
        repo.execute_approved_query.assert_awaited_once()

    async def test_dashboard_uses_upstream_runtime_without_jev_for_different_sources(self):
        from core.agents.sql.agent import SQLAnalyticsAgent as legacy
        from core.agents.sql.agent import SQLAnalyticsAgent as oldest
        self.assertIs(SQLAnalyticsAgent, legacy)
        self.assertIs(SQLAnalyticsAgent, oldest)
        self.assertFalse(hasattr(SQLAnalyticsAgent, '_check_ambiguity'))
        cases = [
            ('Monthly revenue from commerce.sales', '2026-01-01 through 2026-05-31',
             "SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue FROM commerce.sales s "
             'WHERE s.date >= $1 AND s.date < $2 GROUP BY 1 ORDER BY 1 LIMIT 200',
             ['2026-01-01', '2026-06-01'], [{'month': '2026-01-01', 'revenue': 10}, {'month': '2026-02-01', 'revenue': 20}], 'line'),
            ('Session counts by traffic source', '',
             'SELECT w.traffic_source, SUM(w.sessions) AS sessions FROM commerce.web_traffic w GROUP BY 1 LIMIT 200',
             [], [{'traffic_source': 'direct', 'sessions': 3}, {'traffic_source': 'search', 'sessions': 7}], 'bar'),
        ]
        for description, scope, sql, parameters, rows, kind in cases:
            with self.subTest(description=description), patch.dict(os.environ, {'OPENROUTER_API_KEY': ''}):
                provider = SimpleNamespace(generate=Mock(return_value=json.dumps({'sql': sql, 'parameters': parameters,
                    'outputs': [{'kind': kind, 'query': 0, 'dimension': list(rows[0])[0], 'measures': [list(rows[0])[1]]}]})))
                repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=rows))
                request = AgentRequest(question=description,
                    identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))
                document = await DashboardDocumentAgent(SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)).build(request, description, scope)
                self.assertEqual('complete', document.status, document.results[0].message)
                self.assertEqual(kind, document.tiles[0].kind)
                self.assertEqual(rows, document.results[0].payload['rows'])
                self.assertNotIn('jev', document.results[0].payload['metadata'])
                provider.generate.assert_called_once()
                self.assertIn('Dashboard data request', provider.generate.call_args.args[0])
                self.assertIn('descriptive summaries', provider.generate.call_args.args[0])
                repo.execute_approved_query.assert_awaited_once()
                if scope:
                    self.assertIn(scope, provider.generate.call_args.args[0])

    async def test_disallowed_sql_is_rejected_without_jev(self):
        provider = SimpleNamespace(generate=Mock(return_value=json.dumps({'sql': 'DELETE FROM commerce.sales'})))
        repo = SimpleNamespace(execute_approved_query=AsyncMock())
        request = AgentRequest(question='Revenue', identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': ''}):
            result = await SQLAnalyticsAgent(repo, llm=provider, inventory_only=False).run_payload(request)
        self.assertFalse(result['ok'])
        repo.execute_approved_query.assert_not_called()
