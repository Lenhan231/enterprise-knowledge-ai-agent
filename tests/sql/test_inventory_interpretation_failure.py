import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from core.agents.sql.agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest, VerifiedIdentity


class InventoryInterpretationFailureTest(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_inventory_mapping_cannot_execute_sql(self):
        provider, repository = Mock(), AsyncMock()
        provider.generate.return_value = json.dumps({'metrics':['observed_product_count'], 'unknown_slot':True})
        repository.execute_approved_query.return_value = [{'snapshot_date':'2026-05-31','observed_product_count':3}]
        agent=SQLAnalyticsAgent(repository,llm=provider)
        result=await agent.run_payload(AgentRequest(question='Count observed inventory products at 2026-05-31',
            identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertFalse(result['ok'],result)
        self.assertEqual(result['metadata']['metric_error_code'], 'interpretation_invalid')
        provider.generate.assert_called_once()
        repository.execute_approved_query.assert_not_called()
