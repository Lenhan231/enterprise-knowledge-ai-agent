import hashlib
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.chunking.evaluate_chunking_retrieval import _as_vector, _sha256_file, transfer_passage_labels


class ChunkingRetrievalEvaluationTest(unittest.TestCase):
    def test_source_hash_is_streamed_from_exact_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pdf"
            source.write_bytes(b"source bytes\x00\xff")

            self.assertEqual(
                _sha256_file(source),
                hashlib.sha256(b"source bytes\x00\xff").hexdigest(),
            )

    def test_pgvector_adapter_converts_vector_to_numpy(self):
        from pgvector import Vector

        vector = _as_vector(Vector([0.25, 0.5]))
        self.assertEqual(vector.tolist(), [0.25, 0.5])

    def test_transfers_reference_label_to_same_page_candidate_by_trigram_coverage(self):
        references = [{
            "chunk_id": "report::chunk::3",
            "page_number": 7,
            "content": "Consolidated net revenue reached 61.8 billion VND and net profit reached 9.4 billion VND.",
        }]
        candidates = [
            {
                "chunk_id": "report::chunk::20",
                "page_number": 7,
                "content": "Consolidated net revenue reached 61.8 billion VND and net profit reached 9.4 billion VND. Growth continued.",
            },
            {
                "chunk_id": "report::chunk::21",
                "page_number": 8,
                "content": references[0]["content"],
            },
        ]

        labels, mapping = transfer_passage_labels(references, candidates, 0.5)

        self.assertEqual(labels, {"report::chunk::20"})
        self.assertEqual(mapping["report::chunk::3"][0][0], "report::chunk::20")

    def test_does_not_transfer_when_same_page_overlap_is_below_threshold(self):
        references = [{"chunk_id": "report::chunk::1", "page_number": 2, "content": "Revenue profit assets liquidity cash flow."}]
        candidates = [{"chunk_id": "report::chunk::8", "page_number": 2, "content": "Production capacity increased this year."}]

        labels, mapping = transfer_passage_labels(references, candidates, 0.5)

        self.assertEqual(labels, set())
        self.assertEqual(mapping["report::chunk::1"], [])


if __name__ == "__main__":
    unittest.main()
