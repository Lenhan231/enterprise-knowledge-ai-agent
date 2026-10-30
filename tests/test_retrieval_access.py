"""Access-filter integration tests against an isolated local PostgreSQL database."""

import os
from pathlib import Path
import sys
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.database.document_chunks_repository import DocumentChunkRepository
from core.retrieval.retrieval import RetrievedChunk

TEST_DSN = os.getenv("RETRIEVAL_TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DSN, "Set RETRIEVAL_TEST_DATABASE_URL to local PostgreSQL")
class RetrievalAccessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        host = conninfo_to_dict(TEST_DSN).get("host", "")
        if host not in {"localhost", "127.0.0.1", "::1", ""} and not host.startswith("/"):
            raise ValueError("Retrieval tests require local PostgreSQL")
        cls.name = "retrieval_access_" + uuid4().hex
        cls.admin = psycopg.connect(TEST_DSN, autocommit=True)
        cls.admin.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0").format(sql.Identifier(cls.name)))
        cls.connection = psycopg.connect(make_conninfo(TEST_DSN, dbname=cls.name), autocommit=True)
        cls.connection.execute("""
            CREATE TABLE documents (
                document_id text PRIMARY KEY, document_type text,
                processing_status text, knowledge_base_active boolean, allowed_roles text[]
            );
            CREATE TABLE document_chunks (
                id bigserial PRIMARY KEY, document_name text, chunk_index integer,
                content text, metadata jsonb
            )
        """)
        cls.repository = DocumentChunkRepository.__new__(DocumentChunkRepository)
        cls.repository.conn = cls.connection

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()
        cls.admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(cls.name)))
        cls.admin.close()

    def setUp(self):
        self.connection.execute("TRUNCATE documents, document_chunks RESTART IDENTITY")

    def seed(self, document_id, *, active=True, status="ready", roles=("employee",), company="Demo"):
        self.connection.execute("INSERT INTO documents VALUES (%s,'policy',%s,%s,%s)",
                                (document_id, status, active, None if roles is None else list(roles)))
        for index in (0, 1):
            self.connection.execute("INSERT INTO document_chunks (document_name,chunk_index,content,metadata) VALUES (%s,%s,%s,%s)",
                                    (document_id + ".pdf", index, "policy evidence " + document_id,
                                     Jsonb({"document_id": document_id, "company": company, "page_number": 1})))

    def search_ids(self, roles, **scope):
        return {chunk.document_id for chunk in self.repository.similarity_search(
            None, 20, roles=roles, query="policy", method="bm25", **scope,
        )}

    def anchor(self, document_id):
        return RetrievedChunk(document_name=document_id + ".pdf", chunk_index=0,
                              content="Previously retrieved evidence",
                              metadata={"document_id": document_id, "page_number": 1}, retrieval_score=1.0)

    def test_only_active_ready_role_visible_documents_reach_candidates_and_context(self):
        self.seed("allowed")
        for document_id, values in {
            "disabled": {"active": False}, "unknown-active": {"active": None},
            "chunked": {"status": "chunked"}, "failed": {"status": "failed"},
            "unknown-status": {"status": None}, "wrong-role": {"roles": ("executive",)},
            "empty-acl": {"roles": ()}, "null-acl": {"roles": None},
        }.items():
            self.seed(document_id, **values)
        self.assertEqual(self.search_ids(["employee"]), {"allowed"})
        ids = [row[0] for row in self.connection.execute("SELECT document_id FROM documents")]
        contexts = self.repository.expand_parent_contexts([self.anchor(i) for i in ids], roles=["employee"])
        self.assertEqual(set(contexts), {("allowed", 0)})
        self.assertEqual(contexts[("allowed", 0)]["chunk_indices"], [0, 1])

    def test_admin_cannot_bypass_empty_acl_or_inactive_or_unready_documents(self):
        self.seed("allowed")
        self.seed("empty", roles=())
        self.seed("disabled", active=False)
        self.seed("chunked", status="chunked")
        self.assertEqual(self.search_ids(["admin"]), {"allowed"})
        contexts = self.repository.expand_parent_contexts(
            [self.anchor(i) for i in ("allowed", "empty", "disabled", "chunked")], roles=["admin"],
        )
        self.assertEqual(set(contexts), {("allowed", 0)})

    def test_empty_user_roles_do_not_grant_document_access(self):
        self.seed("allowed")
        self.assertEqual(self.search_ids([]), set())
        self.assertEqual(self.repository.expand_parent_contexts([self.anchor("allowed")], roles=[]), {})

    def test_company_and_document_scope_remain_effective(self):
        self.seed("allowed")
        self.seed("other-document")
        self.seed("other-company", company="Other")
        self.assertEqual(self.search_ids(["employee"], company="Demo", document_ids=["allowed", "other-company"]), {"allowed"})
        self.assertEqual(self.search_ids(["employee"], document_ids=[]), set())
        contexts = self.repository.expand_parent_contexts(
            [self.anchor("allowed"), self.anchor("other-company")], company="Demo", roles=["employee"],
        )
        self.assertEqual(set(contexts), {("allowed", 0)})

    def test_disabled_or_revoked_anchor_is_not_restored_after_candidate_selection(self):
        for update in ("knowledge_base_active = false", "allowed_roles = '{}'::text[]",
                       "allowed_roles = ARRAY['executive']", "processing_status = 'failed'"):
            with self.subTest(update=update):
                self.setUp()
                self.seed("allowed")
                candidates = self.repository.similarity_search(None, 1, roles=["employee"], query="policy", method="bm25")
                self.assertEqual(len(candidates), 1)
                self.connection.execute("UPDATE documents SET " + update)
                self.assertEqual(self.repository.expand_parent_contexts(candidates, roles=["employee"]), {})
                self.assertEqual(self.search_ids(["employee"]), set())


if __name__ == "__main__":
    unittest.main()
