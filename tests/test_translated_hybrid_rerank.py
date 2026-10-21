"""Offline integration checks: no model weights, translation API, or database."""
import unittest
from unittest.mock import MagicMock, patch

import test_translated_hybrid as existing
from core.rag.rag_service import RAGService
from core.retrieval.reranker import BGEReranker, MODEL_ID, REVISION
from core.retrieval.retrieval import RetrievalRequest


class RerankTest(unittest.TestCase):
    def test_reorders_original_chunks_stably_without_mutating_fusion_scores(self):
        chunks = [existing.chunk("EN", i) for i in range(3)]
        model = MagicMock()
        model.predict.return_value = [-2.0, 4.0, 4.0]
        ranked, details = BGEReranker(model).rerank("original question", chunks, 2)
        self.assertEqual([x.chunk_index for x in ranked], [1, 2])
        self.assertEqual([x.retrieval_score for x in ranked], [4.0, 4.0])
        self.assertEqual(chunks[1].retrieval_score, 0.8)
        self.assertEqual(model.predict.call_args.args[0][0], ("original question", chunks[0].content))
        self.assertEqual(details["reranker_revision"], REVISION)
        self.assertTrue(details["reranker_applied"])

    def test_end_to_end_rag_preserves_filters_scope_sources_and_provenance(self):
        service, llm = existing.TranslatedHybridTest().service()
        model = MagicMock()
        model.predict.return_value = [1.0, 5.0]
        service.reranker = BGEReranker(model)
        contexts = RAGService(service, MagicMock()).retrieve_contexts(
            "original", limit=1, company="Company", roles=["employee"],
            metadata_filter={"domain": "inventory"},
            retrieval_method="translated_hybrid_rerank", document_ids=["EN", "VN"],
            document_languages={"EN": "en", "VN": "vn"})
        calls = service.repository.similarity_search.call_args_list
        self.assertEqual(len(calls), 3)
        for call in calls:
            self.assertEqual(call.args[1], 300)
            self.assertEqual(call.kwargs["company"], "Company")
            self.assertEqual(call.kwargs["roles"], ["employee"])
            self.assertEqual(call.kwargs["metadata_filter"], {"domain": "inventory"})
        self.assertEqual([c.kwargs["document_ids"] for c in calls], [["EN", "VN"], ["EN"], ["VN"]])
        self.assertEqual(contexts[0]["chunk_id"], "VN::chunk::2")
        self.assertEqual(contexts[0]["source_id"], "S1")
        self.assertEqual(contexts[0]["retrieval_method"], "translated_hybrid_rerank")
        self.assertTrue(contexts[0]["retrieval_details"]["language_aware"])
        self.assertEqual(contexts[0]["retrieval_details"]["reranker_model"], MODEL_ID)
        llm.generate.assert_called_once()

    def test_fallback_is_reranked_and_reported_as_dense_rerank(self):
        service, _ = existing.TranslatedHybridTest().service(error=ValueError("bad translation"))
        model = MagicMock()
        model.predict.return_value = [0.0, 1.0]
        service.reranker = BGEReranker(model)
        result = service.retrieve(RetrievalRequest(query="question", top_k=1),
                                  method="translated_hybrid_rerank", document_ids=["VN"])
        self.assertEqual(result.results[0].document_id, "VN")
        self.assertEqual(result.retrieval_details["effective_method"], "dense_rerank")
        self.assertTrue(result.retrieval_details["dense_fallback"])
        self.assertEqual(service.repository.similarity_search.call_count, 1)

    def test_default_method_never_loads_reranker(self):
        service, _ = existing.TranslatedHybridTest().service()
        with patch("core.retrieval.reranker._load_model") as load:
            service.retrieve(RetrievalRequest(query="question"))
            load.assert_not_called()
        self.assertIsNone(service.reranker)

    def test_empty_results_skip_model_and_bad_scores_fail(self):
        model = MagicMock()
        reranker = BGEReranker(model)
        self.assertEqual(reranker.rerank("question", [], 10)[0], [])
        model.predict.assert_not_called()
        for scores in [[float("nan")], [], [1, 2]]:
            model.predict.return_value = scores
            with self.assertRaises(ValueError):
                reranker.rerank("question", [existing.chunk("EN", 0)], 1)

    def test_missing_weights_raise_actionable_error_without_fallback(self):
        with patch("core.retrieval.reranker._load_model", side_effect=OSError("not cached")):
            with self.assertRaisesRegex(RuntimeError, "RERANKER_ALLOW_DOWNLOAD"):
                BGEReranker().rerank("q", [existing.chunk("EN", 0)], 1)

    def test_agent_dispatch_and_api_accept_new_method(self):
        from core.agents.knowledge_agent import KnowledgeAgent
        from core.models.agents import AgentRequest
        service, _ = existing.TranslatedHybridTest().service()
        model = MagicMock()
        model.predict.return_value = [0.0, 1.0]
        service.reranker = BGEReranker(model)
        answer_llm = MagicMock()
        answer_llm.generate.return_value = "Answer [S1]"
        result = KnowledgeAgent(RAGService(service, answer_llm)).run(AgentRequest(
            question="question", metadata={"role": "employee", "company": "Company",
                                            "retrieval_method": "translated_hybrid_rerank"}))
        self.assertEqual(result.evidence[0].metadata["retrieval_method"], "translated_hybrid_rerank")
        self.assertTrue(result.evidence[0].metadata["retrieval_details"]["reranker_applied"])
        self.assertFalse(result.evidence[0].metadata["retrieval_details"]["language_aware"])
        from app.main import AskRequest
        self.assertEqual(AskRequest(question="question", retrieval_method="translated_hybrid_rerank").retrieval_method,
                         "translated_hybrid_rerank")
        self.assertEqual(AskRequest(question="question").retrieval_method, "hybrid")


if __name__ == "__main__":
    unittest.main()
