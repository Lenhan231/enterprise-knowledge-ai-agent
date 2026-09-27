import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.rag.rag_service import (
    INSUFFICIENT_ANSWER,
    RAGService,
)
from core.retrieval.retrieval import RankedChunk, RetrievalResponse, SourceLocation, make_chunk_id


class FakeRetrieval:
    def __init__(self, contexts):
        self.contexts = contexts

    def retrieve(self, request, company=None, roles=None):
        results = []
        for rank, item in enumerate(self.contexts[:request.top_k], 1):
            document_id = item["metadata"]["document_id"]
            chunk_index = item["chunk_index"]
            results.append(RankedChunk(
                rank=rank,
                chunk_id=make_chunk_id(document_id, chunk_index),
                document_id=document_id,
                text=item["content"],
                score=item["retrieval_score"],
                source=item["document_name"],
                location=SourceLocation(chunk_index=chunk_index, page_number=item["metadata"].get("page_number"), section_title=item["metadata"].get("section_title")),
                metadata=item["metadata"],
                retrieval_method=item["retrieval_method"],
            ))
        return RetrievalResponse(query=request.query, latency_ms=0, results=results)

    def close(self):
        pass


class FakeLLM:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def generate(self, prompt):
        self.calls.append(prompt)
        return self.answer


def context(document_id="DOC-1"):
    return {
        "document_name": "policy.pdf",
        "chunk_index": 7,
        "content": "Employees may report policy concerns.",
        "metadata": {
            "document_id": document_id,
            "source_document": "policy.pdf",
            "page_number": 12,
            "section_title": "Reporting Concerns",
        },
        "retrieval_score": 0.81,
        "retrieval_method": "hybrid",
    }


class RAGServiceTest(unittest.TestCase):
    def test_retrieve_contexts_does_not_generate_an_intermediate_answer(self):
        llm = FakeLLM("Should not be used")
        result = RAGService(FakeRetrieval([context()]), llm).retrieve_contexts(
            "How are concerns reported?", roles=["employee"]
        )

        self.assertEqual(result[0]["source_id"], "S1")
        self.assertEqual(llm.calls, [])

    def test_grounded_answer(self):
        result = RAGService(
            FakeRetrieval([context()]),
            FakeLLM("Concerns may be reported [S1]."),
        ).generate_answer("How are concerns reported?")

        self.assertEqual(result.source_ids, ["S1"])
        self.assertFalse(result.insufficient_context)
        self.assertEqual(len(result.prompt_sha256), 64)

    def test_prompt_fingerprint_is_stable_for_identical_evidence(self):
        first = RAGService(FakeRetrieval([context()]), FakeLLM("Claim [S1].")).generate_answer("Question")
        second = RAGService(FakeRetrieval([context()]), FakeLLM("Claim [S1].")).generate_answer("Question")

        self.assertEqual(first.prompt_sha256, second.prompt_sha256)

    def test_multiple_sources(self):
        result = RAGService(
            FakeRetrieval([context("DOC-1"), context("DOC-2")]),
            FakeLLM("The requirements are described in [S1] and [S2]."),
        ).generate_answer("What are the requirements?")

        self.assertEqual(result.source_ids, ["S1", "S2"])

    def test_fullwidth_citation_is_normalized_then_validated(self):
        result = RAGService(
            FakeRetrieval([context()]),
            FakeLLM("Concerns may be reported 【S1】."),
        ).generate_answer("How are concerns reported?")

        self.assertEqual(result.source_ids, ["S1"])

    def test_localized_and_zero_width_citations_are_normalized_then_validated(self):
        for answer in (
            "Claim [Nguồn: S1].",
            "Claim [\u200bS1].",
            "Claim 【Nguồn: S1】.",
        ):
            with self.subTest(answer=answer):
                result = RAGService(
                    FakeRetrieval([context()]), FakeLLM(answer),
                ).generate_answer("Question")
                self.assertEqual(result.source_ids, ["S1"])

    def test_empty_retrieval(self):
        result = RAGService(
            FakeRetrieval([]),
            FakeLLM("Should not be called"),
        ).generate_answer("Unknown question")

        self.assertEqual(result.answer, INSUFFICIENT_ANSWER)
        self.assertTrue(result.insufficient_context)

    def test_unknown_citation(self):
        service = RAGService(
            FakeRetrieval([context()]),
            FakeLLM("Unsupported claim [S9]."),
        )

        with self.assertRaises(ValueError):
            service.generate_answer("Question")


if __name__ == "__main__":
    unittest.main()
