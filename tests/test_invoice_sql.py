import json
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.analytics.invoices import normalize_invoice
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.text_to_sql import build_sql_prompt, validate_commerce_sql, SQLValidationError
from core.agents.intent_classifier import IntentClassifier
from core.agents.sql_analytics_agent import SQLAnalyticsAgent, AnalyticsPermissionDenied
from core.models.agents import AgentRequest, VerifiedIdentity


class InvoiceNormalizationTest(unittest.TestCase):
    def test_normalizes_dates_amounts_and_missing_items(self):
        header, items = normalize_invoice({
            'date': '30 tháng 09 năm 2026', 'subtotal': '118.000.000',
            'total_amount': '127.440.000,50', 'items': [
                {'description': 'Work', 'amount': '118.000.000', 'quantity': None}]})
        self.assertEqual(header['invoice_date'], date(2026, 9, 30))
        self.assertEqual(header['subtotal'], Decimal('118000000'))
        self.assertEqual(header['total_amount'], Decimal('127440000.50'))
        self.assertIsNone(header['currency'])
        self.assertIsNone(items[0]['quantity'])
        self.assertEqual(items[0]['line_no'], 1)

    def test_accepts_json_numbers_and_explicit_dates(self):
        for value in ('2026-09-30', '30/09/2026'):
            header, _ = normalize_invoice({'date': value, 'subtotal': 1.25})
            self.assertEqual(header['invoice_date'], date(2026, 9, 30))
            self.assertEqual(header['subtotal'], Decimal('1.25'))

    def test_rejects_invalid_or_ambiguous_data(self):
        for data in ({'subtotal': '1,234.56'}, {'subtotal': '12.34'},
                     {'subtotal': True}, {'subtotal': 'NaN'}, {'subtotal': -1},
                     {'date': '31/02/2026'}, {'items': {}}, {'items': [None]},
                     {'buyer': {'name': 'X'}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                normalize_invoice(data)


class InvoiceSQLTest(unittest.TestCase):
    def test_routes_invoice_lookup_and_limits_schema(self):
        for question in ('Find invoice ABC', 'Tìm hóa đơn ABC', 'Invoice item quantity by buyer'):
            self.assertTrue(IntentClassifier.fallback(question).needs_sql)
            prompt = build_sql_prompt(question)
            self.assertIn('commerce.invoices:', prompt)
            self.assertIn('commerce.invoice_items:', prompt)
            self.assertNotIn('commerce.order_items:', prompt)
            self.assertNotIn('commerce.inventory:', prompt)

    def test_invoice_metric_does_not_resolve_to_sales_revenue(self):
        self.assertEqual(resolve_metric_names('total invoice amount'), {'invoice_total'})
        self.assertEqual(resolve_metric_names('tổng tiền hóa đơn'), {'invoice_total'})

    def test_allows_detail_join_but_rejects_inflated_header_totals(self):
        source = ('FROM commerce.invoices AS inv JOIN commerce.invoice_items AS li '
                  'ON inv.invoice_id = li.invoice_id GROUP BY inv.currency LIMIT 200')
        validate_commerce_sql('SELECT inv.currency, SUM(li.amount) AS item_amount ' + source)
        with self.assertRaisesRegex(SQLValidationError, 'duplicat'):
            validate_commerce_sql('SELECT SUM(inv.total_amount) AS total ' + source)
        with self.assertRaises(SQLValidationError):
            validate_commerce_sql('SELECT e.invoice_data FROM public.invoice_extractions AS e LIMIT 1')

    def test_rejects_invoice_money_without_currency_group(self):
        with self.assertRaisesRegex(SQLValidationError, 'currency'):
            validate_commerce_sql('SELECT SUM(inv.total_amount) AS total FROM commerce.invoices AS inv LIMIT 1')

    def test_outer_rollup_cannot_drop_currency(self):
        cte = ('WITH totals AS (SELECT inv.currency, SUM(inv.total_amount) AS amount '
               'FROM commerce.invoices AS inv GROUP BY inv.currency) ')
        with self.assertRaisesRegex(SQLValidationError, 'currency'):
            validate_commerce_sql(cte + 'SELECT SUM(t.amount) AS total FROM totals AS t LIMIT 1')
        validate_commerce_sql(cte + 'SELECT t.currency, SUM(t.amount) AS total '
                             'FROM totals AS t GROUP BY t.currency LIMIT 200')


class InvoiceAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_invoice_metric_executes_and_marks_temporary_access(self):
        sql = ('SELECT inv.currency, SUM(inv.total_amount) AS invoice_total '
               'FROM commerce.invoices AS inv GROUP BY inv.currency LIMIT 200')
        class Provider:
            def generate(self, prompt):
                return json.dumps({'sql': sql})
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{'invoice_total': Decimal('100')}]
        agent = SQLAnalyticsAgent(repository, llm=Provider())
        result = await agent.run(AgentRequest(question='total invoice amount', identity=
            VerifiedIdentity(subject='any-analyst', permissions={'analytics:read'})))
        self.assertTrue(result.metadata['ok'], result.answer)
        self.assertEqual(result.metadata['invoice_access_control'], 'temporary_all_analytics_readers')
        repository.execute_approved_query.assert_awaited_once_with(sql)
        with self.assertRaises(AnalyticsPermissionDenied):
            await agent.run(AgentRequest(question='total invoice amount'))
