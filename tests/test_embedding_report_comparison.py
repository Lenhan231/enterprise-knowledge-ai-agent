import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from compare_embedding_reports import compare_reports


class EmbeddingReportComparisonTest(unittest.TestCase):
    def _write_reports(self, directory: Path) -> list[Path]:
        models = {
            "bge-m3": "BAAI/bge-m3",
            "qwen3-embedding": "Qwen/Qwen3-Embedding-0.6B",
            "e5-large-v2": "intfloat/e5-large-v2",
        }
        pair = {
            "case_file_sha256": "case-hash",
            "corpus_file_sha256": "corpus-hash",
            "sampled_corpus_sha256": "sample-hash",
            "case_count": 1,
            "corpus_chunks": 10,
            "full_company_corpus_chunks": 10,
            "sampled_chunks_per_document": 1000,
            "configuration": {
                "device": "cuda",
                "batch_size": 4,
                "sample_strategy": "all eligible passages per document (corpus fits per-document cap)",
            },
            "evaluation_level": "document; maximum chunk cosine per document",
        }
        paths = []
        for key, model_id in models.items():
            report = {
                **pair,
                "model_key": key,
                "model_id": model_id,
                "model_revision": "revision",
                "environment": {"gpu_available": True, "gpu_name": "Tesla T4"},
                "aggregate": {"mrr": 1.0},
                "timing_seconds": {"mean_query": 0.01},
                "results": [{
                    "id": "case-1",
                    "role": "analyst",
                    "allowed_roles": ["finance_analyst"],
                    "question": "Question?",
                    "eligible_chunks": 8,
                    "relevant_document_ids": ["DOC-1"],
                    "ranked_document_ids": ["DOC-1"],
                    "metrics": {"mrr": 1.0},
                    "latency_ms": 10,
                }],
            }
            path = directory / f"{key}.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            paths.append(path)
        return paths

    def test_compares_exact_paired_model_set_and_records_source_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self._write_reports(Path(temporary))
            result = compare_reports(paths)

        self.assertTrue(result["all_corpus_chunks_claimed"])
        self.assertTrue(result["provenance_consistent"])
        self.assertEqual(len(result["models"]), 3)
        self.assertEqual(len(result["cases"]), 1)
        self.assertTrue(all(item["sha256"] for item in result["source_reports"].values()))

    def test_flags_full_count_and_sampling_strategy_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self._write_reports(Path(temporary))
            report = json.loads(paths[0].read_text(encoding="utf-8"))
            report["configuration"]["sample_strategy"] = "evenly spaced passages per document"
            paths[0].write_text(json.dumps(report), encoding="utf-8")
            result = compare_reports(paths)

        self.assertFalse(result["provenance_consistent"])
        self.assertTrue(result["source_reports"]["bge-m3"]["provenance_conflict"])

    def test_local_content_hash_resolves_stale_sample_strategy_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            paths = self._write_reports(directory)
            corpus_rows = [
                {"document_id": "DOC-1", "content": "first", "allowed_roles": ["analyst"]},
                {"document_id": "DOC-2", "content": "second", "allowed_roles": ["analyst"]},
            ]
            corpus_path = directory / "corpus.jsonl"
            corpus_bytes = ("\n".join(json.dumps(row, ensure_ascii=False) for row in corpus_rows) + "\n").encode()
            corpus_path.write_bytes(corpus_bytes)
            cases_path = directory / "cases.json"
            cases_bytes = b'{"cases":[{"id":"case-1"}]}\n'
            cases_path.write_bytes(cases_bytes)
            sampled_hash = hashlib.sha256(
                "\n".join(f"{row['document_id']}\0{row['content']}" for row in corpus_rows).encode()
            ).hexdigest()

            for path in paths:
                report = json.loads(path.read_text(encoding="utf-8"))
                report.update({
                    "case_file_sha256": hashlib.sha256(cases_bytes).hexdigest(),
                    "corpus_file_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
                    "sampled_corpus_sha256": sampled_hash,
                    "corpus_chunks": 2,
                    "full_company_corpus_chunks": 2,
                })
                report["configuration"]["sample_strategy"] = "evenly spaced passages per document"
                path.write_text(json.dumps(report), encoding="utf-8")

            result = compare_reports(paths, corpus_path, cases_path)

        self.assertTrue(result["local_source_verification"]["verified"])
        self.assertEqual(result["local_source_verification"]["observed_sample_strategy"],
                         "all eligible passages per document (corpus fits per-document cap)")
        self.assertFalse(result["provenance_consistent"])
        self.assertTrue(result["corpus_coverage_verified_by_hash"])
        self.assertTrue(result["source_reports"]["bge-m3"]["sample_strategy_metadata_mismatch"])
        self.assertTrue(result["source_reports"]["bge-m3"]["provenance_conflict"])

    def test_rejects_different_device_or_batch_configuration(self):
        for field, value in (("device", "cpu"), ("batch_size", 8)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                paths = self._write_reports(Path(temporary))
                report = json.loads(paths[1].read_text(encoding="utf-8"))
                report["configuration"][field] = value
                paths[1].write_text(json.dumps(report), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "differ in configuration"):
                    compare_reports(paths)

    def test_rejects_different_source_case_or_role_inputs(self):
        for field, value in (
            ("corpus_file_sha256", "different-corpus"),
            ("case_file_sha256", "different-cases"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                paths = self._write_reports(Path(temporary))
                report = json.loads(paths[1].read_text(encoding="utf-8"))
                report[field] = value
                paths[1].write_text(json.dumps(report), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Paired reports differ"):
                    compare_reports(paths)

    def test_rejects_case_role_and_eligible_chunk_mismatches(self):
        for field, value in (
            ("role", "employee"),
            ("eligible_chunks", 7),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                paths = self._write_reports(Path(temporary))
                report = json.loads(paths[2].read_text(encoding="utf-8"))
                report["results"][0][field] = value
                paths[2].write_text(json.dumps(report), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Paired case differs"):
                    compare_reports(paths)


if __name__ == "__main__":
    unittest.main()
