"""Worker integration tests; CHUNKING_TEST_DATABASE_URL must point to local PostgreSQL."""

import os
from pathlib import Path
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest
from unittest.mock import Mock
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.chunking.processor import ChunkingProcessor
from core.chunking.worker import check_schema, process_next

MIGRATION = (ROOT / "supabase/migrations/20261028090548_add_chunking_document_statuses.sql").read_text()
TEST_DSN = os.getenv("CHUNKING_TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DSN, "Set CHUNKING_TEST_DATABASE_URL for local PostgreSQL integration tests")
class ChunkingWorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        host = conninfo_to_dict(TEST_DSN).get("host", "")
        if host not in {"localhost", "127.0.0.1", "::1", ""} and not host.startswith("/"):
            raise ValueError("Worker integration tests require local PostgreSQL")
        cls.name = "chunking_test_" + uuid4().hex
        cls.admin = psycopg.connect(TEST_DSN, autocommit=True)
        cls.admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.name)))
        cls.dsn = make_conninfo(TEST_DSN, dbname=cls.name)
        cls.connection = psycopg.connect(cls.dsn, autocommit=True)
        cls.connection.execute("""
            CREATE TABLE public.documents (
                document_id text PRIMARY KEY, title text, domain text, document_type text,
                allowed_roles text[] NOT NULL DEFAULT '{}', knowledge_base_active boolean DEFAULT false,
                processing_status text NOT NULL,
                CONSTRAINT documents_processing_status_check CHECK
                    (processing_status IN ('uploaded','processing','parsed','ready','failed'))
            );
            CREATE TABLE public.document_processing_outputs (
                document_id text PRIMARY KEY REFERENCES public.documents(document_id),
                document_metadata jsonb NOT NULL, elements jsonb NOT NULL,
                tables jsonb NOT NULL,
                updated_at timestamptz NOT NULL DEFAULT now()
            );
            CREATE TABLE public.document_parser_chunks (
                document_id text REFERENCES public.documents(document_id), chunk_index integer,
                content text NOT NULL, metadata jsonb NOT NULL,
                PRIMARY KEY(document_id, chunk_index)
            )
        """)
        cls.connection.execute(MIGRATION)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()
        cls.admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(cls.name)))
        cls.admin.close()

    def setUp(self):
        self.connection.execute("TRUNCATE public.documents, public.document_processing_outputs, public.document_parser_chunks")

    def seed(self, document_id="DOC-1", status="parsed", output=True, text="Useful document content."):
        self.connection.execute("""INSERT INTO public.documents
            (document_id,title,domain,document_type,processing_status)
            VALUES (%s,'Sample','general','report',%s)""", (document_id, status))
        if output:
            self.connection.execute("""INSERT INTO public.document_processing_outputs
                (document_id,document_metadata,elements,tables)
                VALUES (%s,%s,%s,%s)""", (
                    document_id, Jsonb({"filename": "sample.pdf", "company": "Demo"}),
                    Jsonb([{"text": text, "metadata": {"page_number": 1, "element_type": "text"}},
                           {"table_ref": 0, "metadata": {"page_number": 1, "element_type": "table"}}]),
                    Jsonb([{"source_order": 1, "page_number": 1, "table_index": 0,
                            "columns": ["Item", "Value"], "rows": [{"Item": "Sales", "Value": "100"}], "metadata": {}}]),
                ))

    def old_chunk(self):
        self.connection.execute("INSERT INTO public.document_parser_chunks VALUES ('DOC-1',0,'old chunk','{}')")

    def test_success_replaces_chunks_and_is_not_reclaimed_or_activated(self):
        self.seed()
        self.old_chunk()
        check_schema(self.connection)
        with self.assertLogs("core.chunking.worker", level="INFO"):
            self.assertEqual(process_next(self.connection, ChunkingProcessor()), "chunked")
        self.assertIsNone(process_next(self.connection, ChunkingProcessor()))
        self.assertEqual(self.connection.execute("SELECT processing_status,allowed_roles,knowledge_base_active FROM documents").fetchone(),
                         ("chunked", [], False))
        rows = self.connection.execute("SELECT content,metadata FROM document_parser_chunks ORDER BY chunk_index").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertIn("Columns: Item | Value", rows[1][0])
        self.assertTrue(all(m["allowed_roles"] == [] and m["document_id"] == "DOC-1" for _, m in rows))
        self.assertTrue(all(m["chunking_applied"] and not m["embeddings_created"] for _, m in rows))

    def test_skips_documents_without_output_and_nonparsed_statuses(self):
        self.seed("MISSING", output=False)
        for status in ["processing", "ready", "failed", "chunking", "chunked"]:
            self.seed(status.upper(), status=status)
        self.assertIsNone(process_next(self.connection, ChunkingProcessor()))

    def test_cli_once_completes_a_job_and_reports_empty_output_failure(self):
        env = {**os.environ, "DATABASE_URL": self.dsn, "PYTHONPATH": str(ROOT / "src")}
        self.seed()
        result = subprocess.run([sys.executable, "-m", "core.chunking.worker", "--once"],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.connection.execute("SELECT processing_status FROM documents").fetchone()[0], "chunked")
        self.seed("EMPTY")
        self.connection.execute("UPDATE document_processing_outputs SET elements='[]',tables='[]' WHERE document_id='EMPTY'")
        result = subprocess.run([sys.executable, "-m", "core.chunking.worker", "--once"],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.connection.execute("SELECT processing_status FROM documents WHERE document_id='EMPTY'").fetchone()[0], "failed")

    def test_processor_error_retains_old_chunks_and_marks_failed(self):
        self.seed()
        self.old_chunk()
        with self.assertLogs("core.chunking.worker", level="ERROR"):
            self.assertEqual(process_next(self.connection, Mock(process=Mock(side_effect=ValueError("bad parser output")))), "failed")
        self.assertEqual(self.connection.execute("SELECT content FROM document_parser_chunks").fetchall(), [("old chunk",)])
        self.assertEqual(self.connection.execute("SELECT processing_status FROM documents").fetchone()[0], "failed")
        self.assertIsNone(process_next(self.connection, ChunkingProcessor()))

    def test_insert_error_rolls_back_delete_before_marking_failed(self):
        self.seed()
        self.old_chunk()
        self.connection.execute("""CREATE FUNCTION reject_chunk() RETURNS trigger LANGUAGE plpgsql AS
            $$ BEGIN RAISE EXCEPTION 'test insert failure'; END $$;
            CREATE TRIGGER reject_chunk BEFORE INSERT ON document_parser_chunks
            FOR EACH ROW EXECUTE FUNCTION reject_chunk();""")
        try:
            with self.assertLogs("core.chunking.worker", level="ERROR"):
                self.assertEqual(process_next(self.connection, ChunkingProcessor()), "failed")
            self.assertEqual(self.connection.execute("SELECT content FROM document_parser_chunks").fetchall(), [("old chunk",)])
            self.assertEqual(self.connection.execute("SELECT processing_status FROM documents").fetchone()[0], "failed")
        finally:
            self.connection.execute("DROP TRIGGER reject_chunk ON document_parser_chunks; DROP FUNCTION reject_chunk()")

    def test_worker_skips_locked_document_and_processes_another(self):
        self.seed("DOC-1")
        self.seed("DOC-2")
        claimed, release = Event(), Event()

        class PausedProcessor:
            def process(self, parsed):
                claimed.set()
                if not release.wait(10):
                    raise TimeoutError("Test failed to release worker")
                return ChunkingProcessor().process(parsed)

        def first_worker():
            with psycopg.connect(self.dsn, autocommit=True) as connection:
                return process_next(connection, PausedProcessor())

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(first_worker)
            try:
                self.assertTrue(claimed.wait(5))
                # Only the committed parsed state is visible while the claim is locked.
                self.assertEqual(self.connection.execute("SELECT processing_status FROM documents WHERE document_id='DOC-1'").fetchone()[0], "parsed")
                with self.assertLogs("core.chunking.worker", level="INFO"):
                    self.assertEqual(process_next(self.connection, ChunkingProcessor()), "chunked")
                self.assertEqual(self.connection.execute("SELECT processing_status FROM documents WHERE document_id='DOC-2'").fetchone()[0], "chunked")
                self.assertIsNone(process_next(self.connection, ChunkingProcessor()))
                # Source output is locked too, so it cannot change midway through a job.
                self.connection.execute("SET statement_timeout='200ms'")
                with self.assertRaises(psycopg.errors.QueryCanceled):
                    self.connection.execute("UPDATE document_processing_outputs SET document_metadata='{}' WHERE document_id='DOC-1'")
            finally:
                self.connection.execute("SET statement_timeout=0")
                release.set()
            self.assertEqual(future.result(timeout=5), "chunked")
        self.assertEqual(self.connection.execute("SELECT count(*) FROM documents WHERE processing_status='chunked'").fetchone()[0], 2)

    def test_interruption_rolls_back_claim_and_allows_retry(self):
        self.seed()
        self.old_chunk()
        with self.assertRaises(KeyboardInterrupt):
            process_next(self.connection, Mock(process=Mock(side_effect=KeyboardInterrupt())))
        self.assertEqual(self.connection.execute("SELECT processing_status FROM documents").fetchone()[0], "parsed")
        self.assertEqual(self.connection.execute("SELECT content FROM document_parser_chunks").fetchone()[0], "old chunk")
        with self.assertLogs("core.chunking.worker", level="INFO"):
            self.assertEqual(process_next(self.connection, ChunkingProcessor()), "chunked")

    def test_missing_status_migration_is_rejected_before_processing(self):
        self.seed()
        self.connection.execute("""ALTER TABLE documents DROP CONSTRAINT documents_processing_status_check;
            ALTER TABLE documents ADD CONSTRAINT documents_processing_status_check CHECK
                (processing_status IN ('uploaded','processing','parsed','ready','failed'))""")
        try:
            with self.assertRaisesRegex(RuntimeError, "migration|Apply"):
                check_schema(self.connection)
            self.assertEqual(self.connection.execute("SELECT processing_status FROM documents").fetchone()[0], "parsed")
        finally:
            self.connection.execute(MIGRATION)

    def test_missing_canonical_schema_migration_is_rejected(self):
        self.seed()
        self.connection.execute("ALTER TABLE document_processing_outputs RENAME COLUMN elements TO text_elements")
        try:
            with self.assertRaisesRegex(RuntimeError, "align_processing_outputs"):
                check_schema(self.connection)
            self.assertEqual(self.connection.execute("SELECT processing_status FROM documents").fetchone()[0], "parsed")
        finally:
            self.connection.execute("ALTER TABLE document_processing_outputs RENAME COLUMN text_elements TO elements")


if __name__ == "__main__":
    unittest.main()
