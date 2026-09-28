import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.rag.rag_service import (
    INSUFFICIENT_ANSWER,
    RAGService,
    _RESPONSE_CACHE,
    _RESPONSE_CACHE_LOCK,
    _cache_response,
    _get_cached_response,
)
from core.retrieval.retrieval import RankedChunk, RetrievalResponse, SourceLocation, make_chunk_id


class FakeRetrieval:
    def __init__(self, contexts):
        self.contexts = contexts
        self.calls = []

    def retrieve(self, request, company=None, roles=None, method="hybrid"):
        self.calls.append((request, company, roles, method))
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
    def setUp(self):
        with _RESPONSE_CACHE_LOCK:
            _RESPONSE_CACHE.clear()

    def test_invoice_request_does_not_misstate_an_annual_report_as_an_invoice(self):
        report = context("VNM-AR-2020-VI")
        report["document_name"] = "Vinamilk_Annual_Report_2020.pdf"
        report["metadata"].update({
            "document_type": "annual_report",
            "source_document": "Vinamilk_Annual_Report_2020.pdf",
            "page_number": 87,
        })
        report["content"] = (
            "Associates Miraka Holdings Limited 15,801,851,520 - "
            "The trade related amounts due to the related parties were unsecured, "
            "interest free and payable within 60 days from invoice date."
        )
        llm = FakeLLM("Should not be used")
        retrieval = FakeRetrieval([report])
        result = RAGService(retrieval, llm).generate_answer(
            "What are the payment terms on the invoice?", roles=["employee"],
        )

        self.assertIn("not an invoice", result.answer)
        self.assertIn("related parties", result.answer)
        self.assertIn("payable within 60 days from invoice date", result.answer)
        self.assertNotIn("15,801,851,520", result.answer)
        self.assertIn("No invoice document", result.answer)
        self.assertEqual(result.source_ids, ["S1"])
        self.assertFalse(result.insufficient_context)
        self.assertEqual(llm.calls, [])
        self.assertEqual(retrieval.calls[0][3], "parent")

    def test_invoice_request_abstains_when_wrong_document_has_no_narrow_disclosure(self):
        report = context("VNM-AR-2020-VI")
        report["metadata"]["document_type"] = "annual_report"
        llm = FakeLLM("Should not be used")
        result = RAGService(FakeRetrieval([report]), llm).generate_answer(
            "What does the invoice require?", roles=["employee"],
        )

        self.assertEqual(result.answer, INSUFFICIENT_ANSWER)
        self.assertTrue(result.insufficient_context)
        self.assertEqual(result.source_ids, [])
        self.assertEqual(llm.calls, [])

    def test_invoice_document_type_allows_normal_grounded_generation(self):
        invoice = context("INV-1")
        invoice["metadata"]["document_type"] = "invoice"
        llm = FakeLLM("Invoice terms are net 30 days [S1].")
        result = RAGService(FakeRetrieval([invoice]), llm).generate_answer(
            "What are the terms on this invoice?", roles=["employee"],
        )

        self.assertEqual(result.source_ids, ["S1"])
        self.assertEqual(len(llm.calls), 1)

    def test_retrieval_fails_closed_without_a_role(self):
        retrieval = FakeRetrieval([context()])
        service = RAGService(retrieval, FakeLLM("Should not be used"))

        for roles in (None, [], ["employee", ""]):
            with self.subTest(roles=roles), self.assertRaisesRegex(ValueError, "authenticated roles"):
                service.retrieve_contexts("restricted question", roles=roles)

        self.assertEqual(retrieval.calls, [])

    def test_retrieve_contexts_does_not_generate_an_intermediate_answer(self):
        llm = FakeLLM("Should not be used")
        result = RAGService(FakeRetrieval([context()]), llm).retrieve_contexts(
            "How are concerns reported?", roles=["employee"]
        )

        self.assertEqual(result[0]["source_id"], "S1")
        self.assertEqual(llm.calls, [])

    def test_grounded_answer(self):
        llm = FakeLLM("Concerns may be reported [S1].")
        result = RAGService(
            FakeRetrieval([context()]), llm,
        ).generate_answer("How are concerns reported?", roles=["employee"])

        self.assertEqual(result.source_ids, ["S1"])
        self.assertFalse(result.insufficient_context)
        self.assertEqual(len(result.prompt_sha256), 64)
        self.assertIn("Preserve the exact scope of each source", llm.calls[0])
        self.assertIn("terms of a different document", llm.calls[0])
        self.assertIn("state that the dedicated policy or record", llm.calls[0])
        self.assertIn("not present in", llm.calls[0])

    def test_reuses_grounded_answer_across_request_scoped_service_instances(self):
        first_llm = FakeLLM("The policy permits reporting concerns [S1].")
        first = RAGService(FakeRetrieval([context()]), first_llm).generate_answer(
            "cache cross-request policy question", roles=["employee"], company="Example Co",
        )
        second_llm = FakeLLM("This must not be generated")
        second = RAGService(FakeRetrieval([context()]), second_llm).generate_answer(
            "cache cross-request policy question", roles=["employee"], company="Example Co",
        )

        self.assertEqual(first.answer, second.answer)
        self.assertEqual(second.source_ids, ["S1"])
        self.assertEqual(len(first_llm.calls), 1)
        self.assertEqual(second_llm.calls, [])

    def test_response_cache_is_scoped_to_authenticated_role(self):
        question = "cache must not cross role boundaries"
        first_llm = FakeLLM("Claim [S1].")
        RAGService(FakeRetrieval([context()]), first_llm).generate_answer(
            question, roles=["finance_analyst"], company="Example Co",
        )
        second_llm = FakeLLM("Claim [S1].")
        RAGService(FakeRetrieval([context()]), second_llm).generate_answer(
            question, roles=["employee"], company="Example Co",
        )

        self.assertEqual(len(first_llm.calls), 1)
        self.assertEqual(len(second_llm.calls), 1)

    def test_response_cache_is_scoped_to_company(self):
        question = "cache must not cross company boundaries"
        first_llm = FakeLLM("Claim [S1].")
        RAGService(FakeRetrieval([context()]), first_llm).generate_answer(
            question, roles=["employee"], company="Example Co A",
        )
        second_llm = FakeLLM("Claim [S1].")
        RAGService(FakeRetrieval([context()]), second_llm).generate_answer(
            question, roles=["employee"], company="Example Co B",
        )

        self.assertEqual(len(second_llm.calls), 1)

    def test_response_cache_expires_after_ttl(self):
        with patch("core.rag.rag_service.monotonic", side_effect=[10.0, 71.0]):
            _cache_response("expiry-test", "Answer [S1].", ["S1"])
            result = _get_cached_response("expiry-test")

        self.assertIsNone(result)

    def test_response_cache_misses_when_retrieved_evidence_changes(self):
        question = "cache must include current evidence"
        first_llm = FakeLLM("First claim [S1].")
        RAGService(FakeRetrieval([context()]), first_llm).generate_answer(
            question, roles=["employee"], company="Example Co",
        )
        changed = context()
        changed["content"] = "Updated evidence has different wording."
        second_llm = FakeLLM("Updated claim [S1].")
        result = RAGService(FakeRetrieval([changed]), second_llm).generate_answer(
            question, roles=["employee"], company="Example Co",
        )

        self.assertEqual(result.answer, "Updated claim [S1].")
        self.assertEqual(len(second_llm.calls), 1)

    def test_response_cache_misses_when_generation_model_changes(self):
        question = "cache must include generation model"
        first_llm = FakeLLM("Claim [S1].")
        first_llm.model_name = "model-a"
        RAGService(FakeRetrieval([context()]), first_llm).generate_answer(
            question, roles=["employee"], company="Example Co",
        )
        second_llm = FakeLLM("Claim [S1].")
        second_llm.model_name = "model-b"
        RAGService(FakeRetrieval([context()]), second_llm).generate_answer(
            question, roles=["employee"], company="Example Co",
        )

        self.assertEqual(len(second_llm.calls), 1)

    def test_prompt_fingerprint_is_stable_for_identical_evidence(self):
        first = RAGService(FakeRetrieval([context()]), FakeLLM("Claim [S1].")).generate_answer("Question", roles=["employee"])
        second = RAGService(FakeRetrieval([context()]), FakeLLM("Claim [S1].")).generate_answer("Question", roles=["employee"])

        self.assertEqual(first.prompt_sha256, second.prompt_sha256)

    def test_multiple_sources(self):
        result = RAGService(
            FakeRetrieval([context("DOC-1"), context("DOC-2")]),
            FakeLLM("The requirements are described in [S1] and [S2]."),
        ).generate_answer("What are the requirements?", roles=["employee"])

        self.assertEqual(result.source_ids, ["S1", "S2"])

    def test_fullwidth_citation_is_normalized_then_validated(self):
        result = RAGService(
            FakeRetrieval([context()]),
            FakeLLM("Concerns may be reported 【S1】."),
        ).generate_answer("How are concerns reported?", roles=["employee"])

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
                ).generate_answer("Question", roles=["employee"])
                self.assertEqual(result.source_ids, ["S1"])

    def test_empty_retrieval(self):
        result = RAGService(
            FakeRetrieval([]),
            FakeLLM("Should not be called"),
        ).generate_answer("Unknown question", roles=["employee"])

        self.assertEqual(result.answer, INSUFFICIENT_ANSWER)
        self.assertTrue(result.insufficient_context)

    def test_unknown_citation(self):
        service = RAGService(
            FakeRetrieval([context()]),
            FakeLLM("Unsupported claim [S9]."),
        )

        with self.assertRaises(ValueError):
            service.generate_answer("Question", roles=["employee"])


if __name__ == "__main__":
    unittest.main()
