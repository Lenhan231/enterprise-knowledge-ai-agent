"""Opt-in Supabase integration tests; every fixture is rolled back."""

import hashlib
import asyncio
import os
import sys
import unittest
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from psycopg import errors
from psycopg.types.json import Jsonb
from core.database.connection_limit import connect_database, close_database_connection
from core.database.invoice_repository import InvoiceRepository
from core.database.commerce_repository import create_repository_from_env
from core.analytics.text_to_sql import validate_commerce_sql


@unittest.skipUnless(os.getenv('RUN_INVOICE_DB_TESTS') == '1', 'Opt-in database test')
class InvoicePublicationTest(unittest.TestCase):
    def setUp(self):
        self.connection = connect_database(autocommit=True)
        self.addCleanup(close_database_connection, self.connection)
        self.transaction = self.connection.transaction(force_rollback=True)
        self.transaction.__enter__()
        self.addCleanup(self.transaction.__exit__, None, None, None)
        self.repository = InvoiceRepository(self.connection)
        self.invoice_id = 'invoice-test-' + uuid4().hex
        self.data = {'date': '30 tháng 09 năm 2026', 'buyer': 'Test buyer', 'seller': 'Test seller',
                     'total_amount': '100.000', 'currency': 'VND', 'items': [
                         {'description': 'First', 'amount': '60.000'},
                         {'description': 'Second', 'amount': '40.000'}]}
        self.connection.execute('INSERT INTO public.invoice_extractions '
            '(invoice_id, source_filename, source_format, source_sha256, storage_path, uploaded_by, '
            'processing_status, invoice_data) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (self.invoice_id, 'test.pdf', 'PDF', hashlib.sha256(self.invoice_id.encode()).hexdigest(),
             'test/' + self.invoice_id, 'integration-test', 'review_required', Jsonb(self.data)))

    def test_approval_republication_and_reprocessing(self):
        self.assertEqual(self.connection.execute('SELECT count(*) FROM commerce.invoices '
            'WHERE invoice_id = %s', (self.invoice_id,)).fetchone()[0], 0)
        self.assertEqual(self.repository.approve(self.invoice_id), 2)
        self.assertEqual(self.repository.approve(self.invoice_id), 2)
        self.assertEqual(self.connection.execute('SELECT count(*) FROM commerce.invoice_items '
            'WHERE invoice_id = %s', (self.invoice_id,)).fetchone()[0], 2)
        self.connection.execute("UPDATE public.invoice_extractions SET processing_status = 'processing', "
            'review_required = true WHERE invoice_id = %s', (self.invoice_id,))
        self.assertEqual(self.connection.execute('SELECT count(*) FROM commerce.invoices '
            'WHERE invoice_id = %s', (self.invoice_id,)).fetchone()[0], 0)
        self.assertEqual(self.connection.execute('SELECT count(*) FROM commerce.invoice_items '
            'WHERE invoice_id = %s', (self.invoice_id,)).fetchone()[0], 0)
        with self.assertRaisesRegex(ValueError, 'completed'):
            self.repository.approve(self.invoice_id)

    def test_invalid_data_leaves_review_status_unchanged(self):
        self.data['total_amount'] = '12.34'
        self.connection.execute('UPDATE public.invoice_extractions SET invoice_data = %s WHERE invoice_id = %s',
                                (Jsonb(self.data), self.invoice_id))
        with self.assertRaises(ValueError):
            self.repository.approve(self.invoice_id)
        self.assertEqual(self.connection.execute('SELECT processing_status, review_required '
            'FROM public.invoice_extractions WHERE invoice_id = %s', (self.invoice_id,)).fetchone(),
            ('review_required', True))

    def test_reader_policy_allows_all_uploaders_but_cannot_write_or_read_raw(self):
        reader = connect_database(os.environ['ANALYTICS_DATABASE_URL'], autocommit=True)
        self.addCleanup(close_database_connection, reader)
        query = validate_commerce_sql('SELECT inv.invoice_id, inv.total_amount '
            'FROM commerce.invoices AS inv LIMIT 200')
        reader.execute(query.sql).fetchall()
        policies = reader.execute("SELECT qual FROM pg_policies WHERE schemaname = 'commerce' "
            "AND policyname IN ('invoice_reader_temporary_all', 'invoice_item_reader_temporary_all')").fetchall()
        self.assertEqual(policies, [('true',), ('true',)])
        for query in ('SELECT invoice_data FROM public.invoice_extractions LIMIT 1',
                      'DELETE FROM commerce.invoices WHERE false',
                      'SELECT source_sha256 FROM commerce.invoices LIMIT 1'):
            with self.assertRaises((errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction)):
                reader.execute(query)

    def test_configured_repository_verifies_role_and_reads_invoices(self):
        async def check():
            repository = await create_repository_from_env()
            try:
                rows = await repository.execute_approved_query('SELECT COUNT(DISTINCT inv.invoice_id) '
                    'AS invoice_count FROM commerce.invoices AS inv LIMIT 1')
                self.assertIsInstance(rows[0]['invoice_count'], int)
            finally:
                await repository.close()
        asyncio.run(check())

    def test_source_deletion_cascades(self):
        self.repository.approve(self.invoice_id)
        self.connection.execute('DELETE FROM public.invoice_extractions WHERE invoice_id = %s', (self.invoice_id,))
        self.assertEqual(self.connection.execute('SELECT count(*) FROM commerce.invoice_items '
            'WHERE invoice_id = %s', (self.invoice_id,)).fetchone()[0], 0)

    def test_duplicate_file_cannot_be_published_under_another_id(self):
        self.repository.approve(self.invoice_id)
        duplicate_id = self.invoice_id + '-duplicate'
        self.connection.execute('INSERT INTO public.invoice_extractions '
            '(invoice_id, source_filename, source_format, source_sha256, storage_path, uploaded_by, '
            'processing_status, invoice_data) SELECT %s, source_filename, source_format, source_sha256, '
            'storage_path, uploaded_by, %s, invoice_data FROM public.invoice_extractions WHERE invoice_id = %s',
            (duplicate_id, 'review_required', self.invoice_id))
        with self.assertRaises(errors.UniqueViolation):
            self.repository.approve(duplicate_id)
        self.assertEqual(self.connection.execute('SELECT processing_status FROM public.invoice_extractions '
            'WHERE invoice_id = %s', (duplicate_id,)).fetchone()[0], 'review_required')
