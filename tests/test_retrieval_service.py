import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import ValidationError


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.retrieval import RetrievalService
from core.database.vector_repository import VectorRepository
from core.models.retrieval import RetrievalRequest, RetrievalResponse, RetrievedChunk


class FakeEmbeddingService:
    def __init__(self):
        self.questions = []

    def embed_query(self, question: str) -> list[float]:
        self.questions.append(question)
        return [0.1, 0.2]


class FakeRepository:
    def __init__(self):
        self.search_args = None
        self.closed = False
        self.results = [RetrievedChunk(
            document_name="policy.pdf", chunk_index=7,
            content="Relevant policy text", metadata={"document_id": "APL-CMP-001"},
            similarity_score=0.81234,
        )]

    def similarity_search(self, embedding: list[float], limit: int):
        self.search_args = (embedding, limit)
        return self.results

    def close(self):
        self.closed = True


class RetrievalServiceTest(unittest.TestCase):
    def setUp(self):
        self.embeddings = FakeEmbeddingService()
        self.repository = FakeRepository()
        self.service = RetrievalService(self.embeddings, self.repository)

    def test_retrieve_embeds_question_and_maps_repository_results(self):
        result = self.service.retrieve(RetrievalRequest(query="What is required?", top_k=3))

        self.assertEqual(self.embeddings.questions, ["What is required?"])
        self.assertEqual(self.repository.search_args, ([0.1, 0.2], 3))
        self.assertIsInstance(result, RetrievalResponse)
        self.assertEqual(result.query, "What is required?")
        self.assertEqual(result.method, "dense")
        chunk = result.results[0]
        self.assertEqual(chunk.source, "policy.pdf")
        self.assertEqual(chunk.score, 0.81234)
        self.assertEqual(chunk.rank, 1)
        self.assertEqual(chunk.document_id, "APL-CMP-001")
        self.assertEqual(chunk.chunk_id, "APL-CMP-001::chunk::7")
        self.assertEqual(chunk.location.chunk_index, 7)
        self.assertIsNone(chunk.location.page_number)
        self.assertIsNone(chunk.location.section_title)
        self.assertEqual(chunk.retrieval_method, "dense")

    def test_full_text_metadata_location_and_tie_order_are_preserved(self):
        first = self.repository.results[0]
        first.content = "  Full text\n" * 3000
        first.metadata.update(page_number=4, section_title="Policy", extra={"tags": ["x"]})
        self.repository.results.extend([
            RetrievedChunk(document_name="a.pdf", chunk_index=0, content="second",
                           metadata={"document_id": "A"}, similarity_score=first.similarity_score),
            RetrievedChunk(document_name="negative.pdf", chunk_index=1, content="third",
                           metadata={"document_id": "N"}, similarity_score=-0.2),
        ])
        result = self.service.retrieve(RetrievalRequest(query="  question\n"))
        self.assertEqual(self.embeddings.questions, ["  question\n"])
        self.assertEqual([item.rank for item in result.results], [1, 2, 3])
        self.assertEqual([item.source for item in result.results], ["policy.pdf", "a.pdf", "negative.pdf"])
        self.assertEqual(result.results[0].text, first.content)
        self.assertEqual(result.results[0].metadata, first.metadata)
        self.assertEqual(result.results[0].location.page_number, 4)
        self.assertEqual(result.results[0].location.section_title, "Policy")
        self.assertEqual(result.results[2].score, -0.2)

    def test_latency_includes_embedding_search_and_mapping(self):
        events = []
        def clock():
            events.append("clock")
            return 10.0 if len(events) == 1 else 10.125
        def embed(query):
            events.append("embed")
            return [0.1, 0.2]
        def search(vector, limit):
            events.append("search")
            return self.repository.results
        from core.models.retrieval import RankedChunk
        def map_chunk(**kwargs):
            events.append("map")
            return RankedChunk(**kwargs)
        with patch("core.retrieval.retrieval_service.perf_counter", side_effect=clock), \
             patch.object(self.embeddings, "embed_query", side_effect=embed), \
             patch.object(self.repository, "similarity_search", side_effect=search), \
             patch("core.retrieval.retrieval_service.RankedChunk", side_effect=map_chunk):
            result = self.service.retrieve(RetrievalRequest(query="question"))
        self.assertEqual(result.latency_ms, 125.0)
        self.assertEqual(events, ["clock", "embed", "search", "map", "clock"])

    def test_empty_results_return_typed_response(self):
        self.repository.results = []
        result = self.service.retrieve(RetrievalRequest(query="question"))
        self.assertEqual(result.results, [])
        self.assertGreaterEqual(result.latency_ms, 0)

    def test_legacy_input_is_rejected_before_embedding(self):
        with self.assertRaisesRegex(TypeError, "RetrievalRequest"):
            self.service.retrieve("question")
        self.assertEqual(self.embeddings.questions, [])
        self.assertIsNone(self.repository.search_args)

    def test_real_repository_boundary_with_fake_cursor(self):
        repository = VectorRepository.__new__(VectorRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            ("policy.pdf", 7, "full text", {"document_id": "DOC"}, 0.9)
        ]
        service = RetrievalService(self.embeddings, repository)
        result = service.retrieve(RetrievalRequest(query="question"))
        self.assertEqual(result.results[0].chunk_id, "DOC::chunk::7")
        self.assertEqual(result.results[0].text, "full text")
        cursor.fetchall.return_value = [("policy.pdf", 7, "text", None, 0.9)]
        with self.assertRaisesRegex(ValidationError, "metadata.document_id"):
            service.retrieve(RetrievalRequest(query="question"))

    def test_close_delegates_to_repository(self):
        self.service.close()

        self.assertTrue(self.repository.closed)


if __name__ == "__main__":
    unittest.main()
