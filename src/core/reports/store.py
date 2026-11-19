"""Reports reuse the private artifact store's ownership and revision controls."""
import os

from core.dashboards.models import now
from core.dashboards.store import DashboardStore, StoreUnavailable
from core.dashboards.postgres_store import PostgresDashboardStore
from core.reports.document import ReportDocument


class ReportStore(DashboardStore):
    artifact_label = 'Report'
    def __init__(self, directory=None):
        super().__init__(directory or os.getenv('REPORT_STORAGE_DIR', 'artifacts/local/reports'))

    @staticmethod
    def decode(encoded):
        return ReportDocument.model_validate_json(encoded)

    @staticmethod
    def prepare(document, expected_revision):
        doc = ReportDocument.model_validate(document.model_dump())
        doc.revision = 1 if expected_revision is None else expected_revision + 1
        doc.updated_at = now()
        encoded = doc.model_dump_json()
        if len(encoded.encode()) > 2_000_000:
            raise ValueError('Report exceeds the 2 MB saved artifact limit')
        return doc, encoded, ''


class PostgresReportStore(PostgresDashboardStore):
    table = 'dashboard_private.reports'
    artifact_label = 'Report'
    decode = staticmethod(ReportStore.decode)
    prepare = staticmethod(ReportStore.prepare)


def create_report_store():
    backend = os.getenv('REPORT_STORAGE_BACKEND', os.getenv('DASHBOARD_STORAGE_BACKEND', 'postgres' if os.getenv('DATABASE_URL') else 'sqlite'))
    if backend == 'sqlite':
        return ReportStore()
    if backend != 'postgres' or not os.getenv('DATABASE_URL'):
        raise StoreUnavailable('Report database is not configured')
    return PostgresReportStore()
