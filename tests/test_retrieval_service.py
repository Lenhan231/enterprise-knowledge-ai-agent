import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import ValidationError


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.database.document_chunks_repository import DocumentChunkRepository
from core.retrieval.retrieval import RetrievalRequest, RetrievalResponse, RetrievedChunk
from core.retrieval.retrieval_service import RetrievalService


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
        self.parent_contexts = {}
        self.results = [RetrievedChunk(
            document_name="policy.pdf", chunk_index=7,
            content="Relevant policy text", metadata={"document_id": "APL-CMP-001"},
            retrieval_score=0.81234,
        )]

    def similarity_search(self, embedding: list[float], limit: int, company=None, roles=None, query=None, method="hybrid", **fusion):
        self.search_args = (embedding, limit, company, roles, query, method, fusion)
        return self.results

    def expand_parent_contexts(self, chunks, company=None, roles=None, radius=2):
        self.expand_args = (company, roles, radius)
        return self.parent_contexts

    def close(self):
        self.closed = True


class FakeTranslator:
    llm = None

    def translate(self, query, query_language="auto"):
        raise RuntimeError("translation disabled in this unit test")


class FakeReranker:
    def rerank(self, query, items, k):
        return items[:k], {"reranker_model": "fake", "rerank_latency_ms": 0}


class RetrievalServiceTest(unittest.TestCase):
    def setUp(self):
        self.embeddings = FakeEmbeddingService()
        self.repository = FakeRepository()
        self.service = RetrievalService(
            self.embeddings, self.repository, FakeTranslator(), FakeReranker()
        )

    def test_retrieve_embeds_question_and_maps_repository_results(self):
        result = self.service.retrieve(RetrievalRequest(query="What is required?", top_k=3))

        self.assertEqual(self.embeddings.questions, ["What is required?"])
        self.assertEqual(self.repository.search_args, ([0.1, 0.2], 300, None, None, "What is required?", "dense", {}))
        self.assertIsInstance(result, RetrievalResponse)
        self.assertEqual(result.query, "What is required?")
        self.assertEqual(result.method, "translated_hybrid_rerank")
        chunk = result.results[0]
        self.assertEqual(chunk.source, "policy.pdf")
        self.assertEqual(chunk.score, 0.81234)
        self.assertEqual(chunk.rank, 1)
        self.assertEqual(chunk.document_id, "APL-CMP-001")
        self.assertEqual(chunk.chunk_id, "APL-CMP-001::chunk::7")
        self.assertEqual(chunk.location.chunk_index, 7)
        self.assertIsNone(chunk.location.page_number)
        self.assertIsNone(chunk.location.section_title)
        self.assertEqual(chunk.retrieval_method, "translated_hybrid_rerank")

    def test_full_text_metadata_location_and_tie_order_are_preserved(self):
        first = self.repository.results[0]
        first.content = "  Full text\n" * 3000
        first.metadata.update(page_number=4, section_title="Policy", extra={"tags": ["x"]})
        self.repository.results.extend([
            RetrievedChunk(document_name="a.pdf", chunk_index=0, content="second",
                           metadata={"document_id": "A"}, retrieval_score=first.retrieval_score),
            RetrievedChunk(document_name="negative.pdf", chunk_index=1, content="third",
                           metadata={"document_id": "N"}, retrieval_score=-0.2),
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
        def search(vector, limit, company=None, roles=None, query=None, method="hybrid", **fusion):
            events.append("search")
            return self.repository.results
        from core.retrieval.retrieval import RankedChunk
        def map_chunk(**kwargs):
            events.append("map")
            return RankedChunk(**kwargs)
        with patch("core.retrieval.retrieval_service.perf_counter", side_effect=clock), \
             patch.object(self.embeddings, "embed_query", side_effect=embed), \
             patch.object(self.repository, "similarity_search", side_effect=search), \
             patch("core.retrieval.retrieval_service.RankedChunk", side_effect=map_chunk):
            result = self.service.retrieve(RetrievalRequest(query="question"), method="hybrid")
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
        repository = DocumentChunkRepository.__new__(DocumentChunkRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            ("policy.pdf", 7, "full text", {"document_id": "DOC"}, 0.9)
        ]
        service = RetrievalService(self.embeddings, repository, FakeTranslator(), FakeReranker())
        result = service.retrieve(RetrievalRequest(query="question"))
        self.assertEqual(result.results[0].chunk_id, "DOC::chunk::7")
        self.assertEqual(result.results[0].text, "full text")
        cursor.fetchall.return_value = [("policy.pdf", 7, "text", None, 0.9)]
        with self.assertRaisesRegex(ValidationError, "metadata.document_id"):
            service.retrieve(RetrievalRequest(query="question"))

    def test_close_delegates_to_repository(self):
        self.service.close()

        self.assertTrue(self.repository.closed)

    def test_bm25_mode_is_passed_through_and_reported(self):
        result = self.service.retrieve(RetrievalRequest(query="revenue"), method="bm25")
        self.assertEqual(self.repository.search_args[5], "bm25")
        self.assertEqual(self.repository.search_args[6], {})
        self.assertEqual(self.embeddings.questions, [])
        self.assertEqual(result.method, "bm25")
        self.assertEqual(result.results[0].retrieval_method, "bm25")

    def test_parent_mode_ranks_children_then_returns_acl_scoped_context(self):
        child = self.repository.results[0]
        child.metadata.update(section_title="Revenue", page_number=4)
        self.repository.parent_contexts[(child.document_id, child.chunk_index)] = {
            "text": "Previous section passage\nRelevant policy text\nNext section passage",
            "chunk_indices": [6, 7, 8],
            "parent_chunk_count": 3,
            "parent_context_type": "section_window",
        }

        result = self.service.retrieve(
            RetrievalRequest(query="revenue", top_k=1),
            company="Vinamilk", roles=["finance_analyst"], method="parent",
        )

        self.assertEqual(self.repository.search_args, ([0.1, 0.2], 5, "Vinamilk", ["finance_analyst"], "revenue", "dense", {}))
        self.assertEqual(result.method, "parent")
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0].text, "Previous section passage\nRelevant policy text\nNext section passage")
        self.assertEqual(result.results[0].retrieval_method, "parent")
        self.assertEqual(result.results[0].metadata["parent_chunk_indices"], [6, 7, 8])
        self.assertEqual(result.results[0].location.chunk_index, 7)

    def test_unknown_method_is_rejected_before_embedding(self):
        with self.assertRaisesRegex(ValueError, "method must be"):
            self.service.retrieve(RetrievalRequest(query="revenue"), method="sparse")
        self.assertEqual(self.embeddings.questions, [])

    def test_parent_mode_drops_candidates_rejected_during_context_expansion(self):
        result = self.service.retrieve(
            RetrievalRequest(query="policy", top_k=1), roles=["employee"], method="parent",
        )
        self.assertEqual(result.results, [])


class NeighbourExpansionTest(unittest.TestCase):
    def chunk(self, index):
        return RetrievedChunk(document_name="policy.pdf", chunk_index=index, content=f"c{index}",
                              metadata={"document_id": "DOC", "page_number": 3}, retrieval_score=1.0 / (index + 1))

    def window(self, indices):
        return {"text": "\n".join(f"c{i}" for i in indices), "texts": [f"c{i}" for i in indices],
                "chunk_indices": indices, "parent_chunk_count": len(indices), "parent_context_type": "page_window"}

    def retrieve(self, radius, chunks):
        repository = FakeRepository()
        repository.results = chunks
        repository.parent_contexts = {("DOC", 5): self.window([4, 5, 6]), ("DOC", 6): self.window([5, 6, 7]),
                                      ("DOC", 9): self.window([8, 9, 10])}
        reranker = MagicMock()
        reranker.rerank.side_effect = lambda query, items, k: (items[:k], {"reranker_model": "fake"})
        translator = MagicMock()
        translator.translate.return_value = {"vn": "mua khẩn", "en": "emergency purchase"}
        service = RetrievalService(FakeEmbeddingService(), repository, translator, reranker)
        with patch.dict("os.environ", {"KNOWLEDGE_CONTEXT_RADIUS": radius}):
            result = service.retrieve(RetrievalRequest(query="mua khan", top_k=3), roles=["employee"])
        return result, repository, reranker

    def test_off_by_default_and_reranks_with_normalized_query(self):
        result, repository, reranker = self.retrieve("0", [self.chunk(5), self.chunk(6), self.chunk(9)])
        self.assertEqual([r.text for r in result.results], ["c5", "c6", "c9"])
        self.assertEqual(reranker.rerank.call_args.args[0], "mua khẩn")
        self.assertFalse(hasattr(repository, "expand_args"))

    def test_windows_are_acl_scoped_and_never_repeat_a_chunk(self):
        result, repository, _ = self.retrieve("1", [self.chunk(5), self.chunk(6), self.chunk(9), self.chunk(4)])
        self.assertEqual(repository.expand_args, (None, ["employee"], 1))
        # 6 sits inside 5's window, so it is dropped; 9 keeps its own window (4 is cut by top_k).
        self.assertEqual([r.location.chunk_index for r in result.results], [5, 9])
        self.assertEqual([r.text for r in result.results], ["c4\nc5\nc6", "c8\nc9\nc10"])
        self.assertEqual(result.results[1].metadata["parent_chunk_indices"], [8, 9, 10])
        self.assertEqual(result.retrieval_details["context_radius"], 1)

    def test_overlapping_window_keeps_only_new_neighbours(self):
        repository_chunks = [self.chunk(5), self.chunk(7)]
        result, _, _ = self.retrieve("1", repository_chunks)
        # 7 has no window of its own in the fake, so it stays as is.
        self.assertEqual([r.text for r in result.results], ["c4\nc5\nc6", "c7"])


if __name__ == "__main__":
    unittest.main()
