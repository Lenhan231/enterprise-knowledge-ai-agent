import asyncio
from datetime import date
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.models.agents import AgentRequest, Evidence, VerifiedIdentity


class SalesContextTest(unittest.IsolatedAsyncioTestCase):
    async def test_saved_context_rechecks_current_acl_without_mutating_snapshot(self):
        from unittest.mock import patch
        from app.reports import scoped_document
        from core.reports.document import ReportDocument
        from core.reports.sales_context import SalesContext
        from test_saved_reports import sample_report
        document = ReportDocument(report=sample_report(), sales_context=SalesContext(retrieval_status='available', documents=[
            Evidence(citation_id='doc-test',source_type='document',source='Restricted pricing policy',
                     content='Pricing changes require approval for sales promotions.',metadata={'document_id':'policy-id'})]))
        user = {'sub':'same-owner','role':'finance_analyst'}
        with patch('app.reports._accessible_document_ids', return_value={'policy-id'}) as allowed:
            visible = await scoped_document(document,user)
            self.assertEqual(len(visible.insights['documents']),1)
            allowed.assert_called_once_with(['policy-id'],['finance_analyst'])
        for failure in (False, True):
            with patch('app.reports._accessible_document_ids', **({'side_effect':ConnectionError()} if failure else {'return_value':set()})):
                redacted = await scoped_document(document,user)
                self.assertFalse(redacted.sales_context.documents)
                self.assertFalse(redacted.insights['documents'])
                self.assertNotIn('Restricted pricing policy',redacted.model_dump_json())
                self.assertNotIn('Pricing changes require approval',redacted.model_dump_json())
                self.assertTrue(document.sales_context.documents)
                import fitz
                from core.reports.export import export_pdf
                pdf=fitz.open(stream=export_pdf(redacted),filetype='pdf')
                self.assertNotIn('Pricing changes require approval',''.join(page.get_text() for page in pdf))

    async def test_prompt_to_saved_report_retrieves_documents_and_preserves_rules(self):
        from core.agents.report.agent import ReportAgent
        from core.agents.sql.agent import SQLAnalyticsAgent
        from core.reports.document import ReportDocument
        knowledge = SimpleNamespace(retrieve=AsyncMock(return_value=[Evidence(source_type='document',source='Pricing review',
            content='Pricing changes require approval and supporting sales evidence.', metadata={'document_id':'pricing-review'})]))
        request = AgentRequest(question='Sales performance May 2026', identity=VerifiedIdentity(subject='finance',
            permissions={'analytics:read','documents:read'}, document_roles={'finance_analyst'}))
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[]))
        result, raw, _ = await ReportAgent(knowledge, SQLAnalyticsAgent(repo, inventory_only=False)).generate_from_template(request, source_mode='analytics')
        knowledge.retrieve.assert_awaited_once()
        self.assertIn('2026-05-01 to 2026-06-01', knowledge.retrieve.await_args.args[0].question)
        self.assertEqual(result.data['sales_context']['retrieval_status'], 'available')
        self.assertTrue(result.data['insights']['document_context'])
        self.assertTrue(any(e.source_type=='document' for e in result.evidence))
        doc = ReportDocument(report=result.data['report'], monthly_decisions=result.data['monthly_decisions'], sales_context=result.data['sales_context'])
        reopened = ReportDocument.model_validate_json(doc.model_dump_json())
        self.assertEqual(reopened.insights, doc.insights)
        self.assertEqual(doc.report['decisions'], result.data['report']['decisions'])
        self.assertTrue(all(rule['triggered'] is None for rule in doc.report['decisions']))
        import fitz
        from core.reports.export import export_pdf
        pdf = fitz.open(stream=export_pdf(doc),filetype='pdf')
        text = ''.join(page.get_text() for page in pdf)
        self.assertIn('Pricing changes require approval', text)
        self.assertNotIn(doc.sales_context.documents[0].citation_id, text)

    async def test_role_scoped_retrieval_and_safe_excerpts(self):
        from core.reports.sales_context import retrieve_context, document_passages
        knowledge = SimpleNamespace(retrieve=AsyncMock(return_value=[Evidence(source_type='document', source='Pricing policy',
            content='Pricing changes require a documented review. Revenue increased by 99 percent.', metadata={'document_id':'policy-id'})]))
        request = AgentRequest(question='Sales performance May 2026', identity=VerifiedIdentity(subject='finance',
            permissions={'analytics:read','documents:read'}, document_roles={'finance_analyst'}))
        context = await retrieve_context(knowledge, request)
        self.assertEqual(context.retrieval_status, 'available')
        scoped = knowledge.retrieve.await_args.args[0]
        self.assertEqual(scoped.identity, request.identity)
        self.assertIn('Sales performance May 2026', scoped.question)
        passages = document_passages(context)
        self.assertEqual(passages[0]['text'], 'Pricing changes require a documented review.')
        self.assertNotIn('99', str(passages))
        self.assertNotIn('99', context.model_dump_json())
        request.identity = VerifiedIdentity(subject='sql-only', permissions={'analytics:read'})
        knowledge.retrieve.reset_mock()
        self.assertEqual((await retrieve_context(knowledge, request)).retrieval_status, 'access_denied')
        knowledge.retrieve.assert_not_awaited()

    async def test_retrieval_failure_does_not_remove_sql_findings(self):
        from core.reports.sales_context import retrieve_context
        request = AgentRequest(question='Sales report 2026', identity=VerifiedIdentity(subject='finance',
            permissions={'documents:read'}, document_roles={'finance_analyst'}))
        for value, status in (([], 'no_evidence'), (ConnectionError(), 'unavailable'), (PermissionError(), 'access_denied')):
            knowledge = SimpleNamespace(retrieve=AsyncMock(**({'side_effect':value} if isinstance(value, Exception) else {'return_value':value})))
            self.assertEqual((await retrieve_context(knowledge, request)).retrieval_status, status)
        doc = Evidence(source_type='document',source='Pricing review',content='Pricing changes require approval for sales promotions.',metadata={'document_id':'policy-id'})
        knowledge = SimpleNamespace(retrieve=AsyncMock(side_effect=[TimeoutError(), [doc, doc]]))
        context = await retrieve_context(knowledge,request)
        self.assertEqual(context.retrieval_status,'available')
        self.assertEqual(len(context.documents),1)
        self.assertEqual(knowledge.retrieve.await_args.args[0].metadata['retrieval_method'],'bm25')
        self.assertEqual(knowledge.retrieve.await_args.args[0].identity,request.identity)
        knowledge = SimpleNamespace(retrieve=AsyncMock(return_value=[doc.model_copy(update={'source':'commerce_schema_metric_contract_v1.md'})]))
        context = await retrieve_context(knowledge,request)
        self.assertEqual(context.retrieval_status,'no_evidence')
        self.assertFalse(context.documents)

    def test_exact_missing_dates_and_future_dates_are_distinct(self):
        from core.reports.sales_context import SalesContext, data_needs
        scope = {'period':{'start':'2026-11-01','end_exclusive':'2027-01-01'},'dimension':'all'}
        context = SalesContext(coverage_status='available', as_of=date(2026,11,18),
                               observed_dates=[date(2026,10,day) for day in range(1,32)]+[date(2026,11,day) for day in range(1,14)])
        needs = data_needs(scope, context)
        text = ' '.join(needs)
        self.assertIn('2026-11-14 to 2026-11-17', text)
        self.assertIn('2026-11-18 to 2026-12-31', text)
        self.assertIn('date, revenue, cogs', text)
        self.assertIn('not yet complete', text)
        self.assertNotIn('insert zero', text)


if __name__ == '__main__': unittest.main()
