"""Inventory deployment scope must not remove shared legacy contracts."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.analytics.text_to_sql import APPROVED_COLUMNS, validate_commerce_sql
from core.models.agents import AgentRequest, VerifiedIdentity

TABLES = {'commerce.inventory','commerce.products'}


class InventoryScopeCompatibilityTest(unittest.IsolatedAsyncioTestCase):
    def test_shared_validator_keeps_existing_sources(self):
        self.assertIn('commerce.orders',APPROVED_COLUMNS)
        self.assertEqual(validate_commerce_sql('SELECT o.order_id FROM commerce.orders o LIMIT 1').sources,('commerce.orders',))

    def test_scope_is_server_configuration_not_a_shared_global_mutation(self):
        with patch.dict(os.environ,{'SQL_INVENTORY_ONLY':'true'}):
            scoped=SQLAnalyticsAgent(AsyncMock())
        self.assertEqual(set(scoped.table_columns),TABLES)
        legacy=SQLAnalyticsAgent(AsyncMock(),inventory_only=False)
        self.assertIn('commerce.orders',legacy.table_columns)
        with patch.dict(os.environ,{'SQL_INVENTORY_ONLY':'typo'}),self.assertRaises(ValueError):
            SQLAnalyticsAgent(AsyncMock())

    async def test_nested_outside_sources_cannot_reach_scoped_repository(self):
        repo,provider=AsyncMock(),Mock()
        sql='SELECT p.product_id FROM commerce.products p WHERE EXISTS (SELECT 1 FROM commerce.order_items o WHERE o.product_id=p.product_id) LIMIT 1'
        provider.generate.side_effect=[json.dumps({'sql':sql})]*2
        result=await SQLAnalyticsAgent(repo,llm=provider,inventory_only=True).run(AgentRequest(
            question='Find catalog products associated with an order',identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertNotEqual(result.data.get('query_status'),'executed')
        repo.execute_approved_query.assert_not_awaited()

    async def test_explicit_outside_table_is_explained_without_generation(self):
        repo,provider=AsyncMock(),Mock()
        result=await SQLAnalyticsAgent(repo,llm=provider,inventory_only=True).run(AgentRequest(
            question='List order_id from commerce.orders limit 1',identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertEqual(result.metadata.get('metric_error_code'),'outside_inventory_scope')
        provider.generate.assert_not_called()
        repo.execute_approved_query.assert_not_awaited()

    def test_report_prompt_preserves_legacy_contract_and_supports_inventory_scope(self):
        from core.reports.planning import planning_prompt
        legacy=planning_prompt('Inventory summary')
        scoped=planning_prompt('Inventory summary',inventory_only=True)
        extract=lambda p:json.loads(p.split('\nAvailable SQL schema: ')[1].split('\nApproved joins: ')[0])
        self.assertIn('commerce.orders',extract(legacy))
        self.assertEqual(set(extract(scoped)),TABLES)

    async def test_router_planning_receives_runtime_schema(self):
        from core.agents.planning import plan_request
        provider=Mock()
        provider.generate.return_value=json.dumps({'objective':'inventory','tasks':[{'id':'stock','agent':'sql','question':'Show stock at snapshot 2022-12-31'}]})
        columns=SQLAnalyticsAgent(AsyncMock(),inventory_only=True).table_columns
        await plan_request(AgentRequest(question='Show stock at snapshot 2022-12-31'),provider,sql_schema=columns)
        prompt=provider.generate.call_args.args[0]
        self.assertIn('commerce.inventory',prompt)
        self.assertNotIn('commerce.order_items',prompt)

    async def test_repository_revalidates_inventory_scope_before_fetch(self):
        from core.database.commerce_repository import CommerceRepository
        repo=CommerceRepository(AsyncMock(),allowed_sources=TABLES)
        repo._fetch=AsyncMock()
        with self.assertRaises(ValueError):
            await repo.execute_approved_query('SELECT o.order_id FROM commerce.orders o LIMIT 1')
        repo._fetch.assert_not_awaited()

    async def test_inventory_factory_verifies_only_required_read_privileges(self):
        from core.database.commerce_repository import create_repository_from_env
        pool=AsyncMock()
        with patch.dict(os.environ,{'SQL_INVENTORY_ONLY':'true','ANALYTICS_DATABASE_URL':'postgresql://reader:unused@localhost/test'}), \
             patch('core.database.commerce_repository.asyncpg.create_pool',new=AsyncMock(return_value=pool)), \
             patch('core.database.commerce_repository.verify_analytics_role',new=AsyncMock()) as verify:
            repo=await create_repository_from_env()
        self.assertEqual(set(repo.allowed_sources),TABLES)
        self.assertEqual(set(verify.await_args.kwargs['allowed_sources']),TABLES)
