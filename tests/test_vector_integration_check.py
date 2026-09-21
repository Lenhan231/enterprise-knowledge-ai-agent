import io
import os
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import check_vector_repository_integration as check


class IntegrationCheckTest(unittest.TestCase):
    def connection(self, missing_ids=0, metadata=None, empty=False):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        rows = [("doc.pdf", 0, " full text\n" * 3000,
                 {"document_id": "DOC"} if metadata is None else metadata, 1.0)]
        cur.fetchall.side_effect = [
            [("embedding", "vector", 384, True, None),
             ("metadata", "jsonb", -1, True, "'{}'::jsonb")],
            [("btree", True, 2, "document_name", "chunk_index", "text_ops"),
             ("hnsw", False, 1, "embedding", None, "vector_cosine_ops")],
            rows, rows,
        ]
        vector = "[" + ",".join(["1.0"] + ["0.0"] * 383) + "]"
        cur.fetchone.side_effect = [(0 if empty else 360, 0, missing_ids, 0),
                                   None if empty else (vector,)]
        return conn

    @patch.object(check, "register_vector")
    def test_real_repository_mapping_on_mocked_read_only_connection(self, register):
        conn = self.connection()
        report = check.check_connection(conn)
        self.assertTrue(check.passed(report))
        first_sql = conn.cursor.return_value.__enter__.return_value.execute.call_args_list[0].args[0]
        self.assertIn("REPEATABLE READ, READ ONLY", first_sql)
        conn.commit.assert_not_called()

    @patch.object(check, "register_vector")
    def test_legacy_rows_block_pass_even_when_sample_succeeds(self, register):
        report = check.check_connection(self.connection(missing_ids=25))
        self.assertEqual(report["retrieval"], "pass")
        self.assertFalse(check.passed(report))

    @patch.object(check, "register_vector")
    def test_invalid_sample_and_empty_corpus_do_not_pass(self, register):
        invalid = check.check_connection(self.connection(missing_ids=1, metadata={}))
        self.assertEqual(invalid["retrieval"], "validation_failed")
        self.assertFalse(check.passed(invalid))
        empty = check.check_connection(self.connection(empty=True))
        self.assertEqual(empty["retrieval"], "not_checked_no_nonzero_vector")
        self.assertFalse(check.passed(empty))

    @patch.object(check, "load_dotenv")
    @patch.dict(os.environ, {"DATABASE_URL": "test-only-secret"})
    def test_errors_are_redacted_and_connection_is_cleaned_up(self, dotenv):
        conn = MagicMock()
        output = io.StringIO()
        with patch.object(check.psycopg, "connect", return_value=conn) as connect, \
             patch.object(check, "check_connection", side_effect=RuntimeError("test-only-secret")), \
             redirect_stdout(output), redirect_stderr(output):
            self.assertEqual(check.main(), 2)
        self.assertNotIn("test-only-secret", output.getvalue())
        self.assertIn("default_transaction_read_only=on", connect.call_args.kwargs["options"])
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()
        conn.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
