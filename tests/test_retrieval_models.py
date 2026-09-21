import json
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.models.retrieval import (
    RankedChunk,
    RetrievalRequest,
    RetrievalResponse,
    RetrievedChunk,
    SourceLocation,
    make_chunk_id,
)


FIXTURE = Path(__file__).parent / "fixtures" / "ranked_dense_retrieval.json"


class RetrievalModelsTest(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.chunk = self.payload["results"][0]

    def test_query_rejects_empty_and_whitespace(self):
        for query in ("", " ", "\t\n"):
            with self.subTest(query=query):
                with self.assertRaisesRegex(ValidationError, "query"):
                    RetrievalRequest(query=query)

    def test_request_rejects_misspelled_top_k(self):
        with self.assertRaises(ValidationError) as caught:
            RetrievalRequest(query="question", topk=10)
        self.assertEqual(caught.exception.errors()[0]["type"], "extra_forbidden")
        self.assertEqual(caught.exception.errors()[0]["loc"], ("topk",))

    def test_all_result_models_reject_unknown_fields(self):
        internal = dict(document_name="demo.pdf", chunk_index=0, content="text",
                        metadata={"document_id": "DOC"}, similarity_score=0.5)
        for model, payload in ((SourceLocation, {"chunk_index": 0}),
                               (RetrievedChunk, internal),
                               (RankedChunk, self.chunk),
                               (RetrievalResponse, self.payload)):
            with self.subTest(model=model.__name__):
                with self.assertRaisesRegex(ValidationError, "extra_forbidden"):
                    model(**payload, unexpected="typo")

    def test_top_k_defaults_bounds_and_integer_type(self):
        self.assertEqual(RetrievalRequest(query="question").top_k, 5)
        for top_k in (1, 100):
            self.assertEqual(RetrievalRequest(query="question", top_k=top_k).top_k, top_k)
        for top_k in (-1, 0, 101, True, 1.5):
            with self.subTest(top_k=top_k):
                with self.assertRaisesRegex(ValidationError, "top_k"):
                    RetrievalRequest(query="question", top_k=top_k)

    def test_request_preserves_query_and_round_trips(self):
        request = RetrievalRequest(query="  Supplier obligations?\n", top_k=10)
        self.assertEqual(request.query, "  Supplier obligations?\n")
        self.assertEqual(RetrievalRequest.model_validate_json(request.model_dump_json()), request)

    def test_fixture_round_trip_preserves_all_fields(self):
        response = RetrievalResponse.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(response.model_dump(mode="json"), self.payload)
        self.assertEqual(RetrievalResponse.model_validate_json(response.model_dump_json()), response)

    def test_optional_location_fields_may_be_omitted_or_null(self):
        omitted = SourceLocation(chunk_index=0)
        explicit = SourceLocation(chunk_index=0, page_number=None, section_title=None)
        self.assertEqual(omitted, explicit)
        self.assertIsNone(omitted.page_number)
        self.assertIsNone(omitted.section_title)

    def test_chunk_id_is_deterministic_and_identity_sensitive(self):
        self.assertEqual(make_chunk_id("DOC-1", 7), "DOC-1::chunk::7")
        self.assertEqual(make_chunk_id("DOC-1", 7), make_chunk_id("DOC-1", 7))
        self.assertNotEqual(make_chunk_id("DOC-1", 7), make_chunk_id("DOC-1", 8))
        self.assertNotEqual(make_chunk_id("DOC-1", 7), make_chunk_id("DOC-2", 7))
        self.assertEqual(RankedChunk(**self.chunk).chunk_id, make_chunk_id("DEMO-SUP-001", 0))

    def test_invalid_chunk_identity_is_rejected(self):
        for document_id, index in (("", 0), (" ", 0), ("DOC", -1), ("DOC", True)):
            with self.subTest(document_id=document_id, index=index):
                with self.assertRaises(ValueError):
                    make_chunk_id(document_id, index)
        self.chunk["chunk_id"] = "unrelated-id"
        with self.assertRaisesRegex(ValidationError, "chunk_id must match"):
            RankedChunk(**self.chunk)

    def test_extra_metadata_and_full_text_are_preserved(self):
        self.chunk["metadata"]["custom"] = {"tags": ["legal", "supplier"], "reviewed": False}
        self.chunk["text"] = "  Full text\n" * 3000
        result = RankedChunk(**self.chunk)
        restored = RankedChunk.model_validate_json(result.model_dump_json())
        self.assertEqual(restored.metadata, self.chunk["metadata"])
        self.assertEqual(restored.text, self.chunk["text"])

    def test_public_document_id_is_required(self):
        del self.chunk["document_id"]
        with self.assertRaises(ValidationError) as caught:
            RankedChunk(**self.chunk)
        self.assertIn(("document_id",), [error["loc"] for error in caught.exception.errors()])

    def test_metadata_document_id_is_required_without_filename_fallback(self):
        for metadata in ({}, {"document_id": ""}, {"document_id": " "}, {"document_id": None}):
            with self.subTest(metadata=metadata):
                self.chunk["metadata"] = metadata
                with self.assertRaisesRegex(ValidationError, "metadata.document_id"):
                    RankedChunk(**self.chunk)
                with self.assertRaisesRegex(ValidationError, "metadata.document_id"):
                    RetrievedChunk(document_name="fallback.pdf", chunk_index=0,
                                   content="text", metadata=metadata, similarity_score=0.5)

    def test_document_id_must_match_ingested_metadata(self):
        self.chunk["document_id"] = "DIFFERENT-ID"
        with self.assertRaisesRegex(ValidationError, "document_id must match metadata.document_id"):
            RankedChunk(**self.chunk)

    def test_internal_result_has_no_rank_or_latency(self):
        result = RetrievedChunk(document_name=self.chunk["source"], chunk_index=0,
                                content=self.chunk["text"], metadata=self.chunk["metadata"],
                                similarity_score=self.chunk["score"])
        self.assertEqual(result.document_id, self.chunk["document_id"])
        self.assertEqual(set(result.model_dump()),
                         {"document_name", "chunk_index", "content", "metadata", "similarity_score"})

    def test_response_supports_no_results(self):
        result = RetrievalResponse(query="question", latency_ms=0, results=[])
        self.assertEqual(result.results, [])
        self.assertEqual(result.method, "dense")

    def test_invalid_rank_method_latency_and_nonfinite_score(self):
        for field, value in (("rank", 0), ("retrieval_method", "hybrid"), ("score", float("nan"))):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    RankedChunk(**{**self.chunk, field: value})
        for field, value in (("method", "hybrid"), ("latency_ms", -1), ("latency_ms", float("inf"))):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValidationError):
                    RetrievalResponse(**{**self.payload, field: value})


if __name__ == "__main__":
    unittest.main()
