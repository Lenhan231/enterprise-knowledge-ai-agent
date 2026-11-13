"""Publish reviewed extractions atomically using the existing writer connection."""

from psycopg.rows import dict_row

from core.analytics.invoices import normalize_invoice
from core.database.connection_limit import connect_database, close_database_connection


class InvoiceRepository:
    def __init__(self, connection=None):
        self.connection = connection if connection is not None else connect_database()
        self._owns_connection = connection is None

    def approve(self, invoice_id):
        """Explicit administrative review action; never called by the SQL agent."""
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('SELECT invoice_id, invoice_data, source_filename, source_sha256, '
                           'schema_version, processing_status FROM public.invoice_extractions '
                           'WHERE invoice_id = %s FOR UPDATE', (invoice_id,))
            extraction = cursor.fetchone()
            if extraction is None:
                raise ValueError('Invoice extraction not found')
            if extraction['schema_version'] != 'invoice.v1':
                raise ValueError('Only invoice.v1 extractions are supported')
            if extraction['processing_status'] not in {'review_required', 'approved'}:
                raise ValueError('Only completed extractions can be approved')
            header, items = normalize_invoice(extraction['invoice_data'])
            cursor.execute("UPDATE public.invoice_extractions SET processing_status = 'approved', "
                           'review_required = false, updated_at = now() WHERE invoice_id = %s', (invoice_id,))
            # The invalidation trigger removes an earlier projection in this same transaction.
            cursor.execute('INSERT INTO commerce.invoices '
                           '(invoice_id, source_filename, source_sha256, invoice_no, invoice_date, '
                           'buyer, seller, subtotal, tax_amount, total_amount, currency) '
                           'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                           (invoice_id, extraction['source_filename'], extraction['source_sha256'],
                            *(header[name] for name in ('invoice_no', 'invoice_date', 'buyer', 'seller',
                                                       'subtotal', 'tax_amount', 'total_amount', 'currency'))))
            if items:
                cursor.executemany('INSERT INTO commerce.invoice_items '
                                   '(invoice_id, line_no, description, unit, quantity, unit_price, amount) '
                                   'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                                   [(invoice_id, *(item[name] for name in
                                     ('line_no', 'description', 'unit', 'quantity', 'unit_price', 'amount')))
                                    for item in items])
        return len(items)

    def close(self):
        if self._owns_connection:
            close_database_connection(self.connection)
