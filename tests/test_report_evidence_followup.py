import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(os.environ.get('SQL_DETERMINISTIC_ROOT',ROOT))
sys.path[:0]=[str(WORK),str(WORK/'src')]
from core.models.agents import AgentRequest,AgentResult,VerifiedIdentity
from core.agents.analytics_agent import AnalyticsAgent
from core.reports.sources import collect_sources,serialize_context
from core.reports import sources as report_sources


@unittest.skipUnless('SQL_DETERMINISTIC_ROOT' in os.environ,'Isolated Report evidence experiment')
class ReportEvidenceFollowupTest(unittest.IsolatedAsyncioTestCase):
    async def test_report_evidence_does_not_generate_a_redundant_summary(self):
        sql=Mock();sql.run_payload=AsyncMock(return_value=dict(ok=True,rows=[dict(product_id=1)],metadata={}))
        result=await AnalyticsAgent(sql).run_payload(AgentRequest(question='List products',metadata={'_report_evidence_only':True}))
        self.assertEqual(result['rows'],[dict(product_id=1)])
        sql._provider.assert_not_called()

    async def test_oversized_rows_become_attributable_passages_instead_of_all_disappearing(self):
        rows=[dict(product_id=i,description='x'*600) for i in range(200)]
        router=Mock();router.collect_sources=AsyncMock(return_value=AgentResult(answer='Evidence',agent='agentic',
            data={'tasks':{'s1':dict(agent='sql',status='complete',rows=rows)}},metadata={'ok':True,'status':'complete'}))
        request=AgentRequest(question='Report products',identity=VerifiedIdentity(subject='test',
            permissions={'analytics:read','documents:read'},document_roles={'admin'}))
        sections,coverage,limits,_=await collect_sources(request,['Findings'],'orchestrated',None,None,source_router=router)
        self.assertTrue(sections['Findings'])
        self.assertLessEqual(len(serialize_context(sections['Findings'])),report_sources.SQL_CONTEXT_CHARACTERS)
        self.assertGreater(coverage['Findings']['omitted'],0)
        for item in sections['Findings']:
            self.assertIn('row_start',item.metadata)
            self.assertLessEqual(item.metadata['row_end']-item.metadata['row_start']+1,50)
        self.assertTrue(any('omitted' in note.lower() for note in limits))
        from core.agents.report_agent import ReportAgent
        appendix=ReportAgent._appendix('partial',limits,[],coverage,{'scope':'Returned rows','considered_rows':200,'available_rows':200})
        self.assertIn('SQL rows in section context:',appendix)
