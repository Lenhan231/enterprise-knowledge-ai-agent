"""Exercise translation -> scoped searches -> fusion -> RAG, without API/DB calls."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.database.document_chunks_repository import DocumentChunkRepository
from core.rag.rag_service import RAGService
from core.retrieval.query_translator import QueryTranslator
from core.retrieval.retrieval import RetrievalRequest, RetrievedChunk
from core.retrieval.retrieval_service import RetrievalService


def chunk(doc, index):
    return RetrievedChunk(document_name=doc + ".pdf", chunk_index=index,
                          content="Evidence " + doc, metadata={"document_id": doc},
                          retrieval_score=0.8)


class TranslatedHybridTest(unittest.IsolatedAsyncioTestCase):
    def service(self, source="vn", error=None):
        llm = MagicMock()
        llm.model_name = "fake-translator"
        llm.generate.return_value = json.dumps({"source_lang": source, "translation": "translated"})
        if error:
            llm.generate.side_effect = error
        repo = MagicMock()
        repo.similarity_search.side_effect = lambda vector, limit, **kw: (
            [chunk("EN", 1), chunk("VN", 2)] if kw["method"] == "dense" else
            [chunk("EN", 1)] if kw.get("document_ids") == ["EN"] else
            [chunk("VN", 2)] if kw.get("document_ids") == ["VN"] else [])
        embedding = MagicMock()
        embedding.embed_query.return_value = [0.1]
        return RetrievalService(embedding, repo, QueryTranslator(llm)), llm

    def test_auto_detects_both_languages_and_routes_only_authorized_scoped_queries(self):
        for source, question in [("vn", "Doanh thu năm 2008?"), ("en", "Revenue in 2008?")]:
            with self.subTest(source=source):
                service, llm = self.service(source)
                rag = RAGService(service, MagicMock())
                contexts = rag.retrieve_contexts(
                    question, limit=1, company="Company", roles=["employee"],
                    retrieval_method="translated_hybrid", document_ids=["EN", "VN"],
                    document_languages={"EN": "en", "VN": "vn"})
                calls = service.repository.similarity_search.call_args_list
                self.assertEqual([c.kwargs["method"] for c in calls], ["dense", "bm25", "bm25"])
                self.assertEqual([c.kwargs["document_ids"] for c in calls], [["EN", "VN"], ["EN"], ["VN"]])
                for call in calls:
                    self.assertEqual(call.kwargs["company"], "Company")
                    self.assertEqual(call.kwargs["roles"], ["employee"])
                    self.assertEqual(call.args[1], 10)
                self.assertEqual(calls[0].kwargs["query"], question)
                self.assertEqual(calls[1 if source == "en" else 2].kwargs["query"], question)
                self.assertEqual(len(contexts), 1)
                self.assertEqual(contexts[0]["retrieval_method"], "translated_hybrid")
                self.assertEqual(contexts[0]["retrieval_details"]["lexical_queries"][source], question)
                # One cached translation; searches still run with this call's trusted filters.
                rag.retrieve_contexts(question, roles=["admin"], retrieval_method="translated_hybrid",
                                      document_ids=[], document_languages={})
                llm.generate.assert_called_once()
                for call in service.repository.similarity_search.call_args_list[-3:]:
                    self.assertEqual(call.kwargs["document_ids"], [])
                    self.assertEqual(call.kwargs["roles"], ["admin"])

    async def test_knowledge_agent_forwards_the_strategy_and_retains_translation_provenance(self):
        from core.agents.knowledge_agent import KnowledgeAgent
        from core.models.agents import AgentRequest, VerifiedIdentity
        service, _ = self.service()
        answer_llm = MagicMock()
        answer_llm.generate.return_value = "Answer [S1]"
        agent = KnowledgeAgent(RAGService(service, answer_llm))
        result = await agent.run(AgentRequest(question="Doanh thu?", identity=VerifiedIdentity(subject="test", permissions={"documents:read"}, document_roles={"employee"}), metadata={
            "role": "employee", "company": "Company", "retrieval_method": "translated_hybrid"}))
        self.assertEqual(result.evidence[0].metadata["retrieval_method"], "translated_hybrid")
        self.assertEqual(result.evidence[0].metadata["retrieval_details"]["translation_model"], "fake-translator")
        self.assertEqual(service.repository.similarity_search.call_count, 3)

    def test_two_stage_rrf_matches_expected_scores_and_deduplicates(self):
        service, llm = self.service()
        a, b = chunk("EN", 1), chunk("VN", 2)
        service.repository.similarity_search.side_effect = [[a, b], [b, b], [a]]
        result = service.retrieve(RetrievalRequest(query="question", top_k=2),
                                  method="translated_hybrid", document_ids=["EN", "VN"])
        self.assertEqual([x.document_id for x in result.results], ["EN", "VN"])
        self.assertAlmostEqual(result.results[0].score, 3 / 61)
        self.assertAlmostEqual(result.results[1].score, 3 / 62)
        self.assertEqual(result.retrieval_details["lexical_document_scopes"],
                         {"en": ["EN", "VN"], "vn": ["EN", "VN"]})
        self.assertEqual(a.retrieval_score, 0.8)  # No mutation of repository candidates.

    def test_invalid_translation_and_provider_setup_fall_back_to_scoped_dense(self):
        for error in [ValueError("bad JSON"), RuntimeError("empty output")]:
            service, _ = self.service(error=error)
            result = service.retrieve(RetrievalRequest(query="question", top_k=1),
                                      method="translated_hybrid", document_ids=["EN"])
            self.assertEqual(len(result.results), 1)
            self.assertTrue(result.retrieval_details["dense_fallback"])
            self.assertEqual(result.retrieval_details["effective_method"], "dense")
            self.assertEqual(service.repository.similarity_search.call_count, 1)
            self.assertEqual(service.repository.similarity_search.call_args.kwargs["document_ids"], ["EN"])
        service, _ = self.service()
        service.query_translator = None
        with patch("core.llm.groq_provider.GroqProvider", side_effect=ValueError("missing key")):
            result = service.retrieve(RetrievalRequest(query="question"), method="translated_hybrid")
        self.assertTrue(result.retrieval_details["dense_fallback"])

    def test_malformed_detected_translation_and_api_failure_are_explicit_fallbacks(self):
        import httpx
        from openai import APIConnectionError
        for raw in ["not JSON", '{"source_lang":"fr","translation":"text"}',
                    '{"source_lang":"en","translation":"   "}']:
            service, llm = self.service()
            llm.generate.return_value = raw
            response = service.retrieve(RetrievalRequest(query="question"), method="translated_hybrid")
            self.assertTrue(response.retrieval_details["dense_fallback"])
            self.assertEqual(service.repository.similarity_search.call_count, 1)
        service, _ = self.service(error=APIConnectionError(request=httpx.Request("POST", "https://example.test")))
        response = service.retrieve(RetrievalRequest(query="question"), method="translated_hybrid")
        self.assertEqual(response.retrieval_details["translation_error"], "APIConnectionError")

    def test_sql_filters_are_present_in_all_three_searches(self):
        service, llm = self.service()
        repo = DocumentChunkRepository.__new__(DocumentChunkRepository)
        repo.conn = MagicMock()
        cursor = repo.conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        service.repository = repo
        service.retrieve(RetrievalRequest(query="question"), method="translated_hybrid",
                         company="Company", roles=["employee"], document_ids=["EN", "VN"],
                         metadata_filter={"domain": "finance"}, document_languages={"EN": "en", "VN": "vn"})
        self.assertEqual(cursor.execute.call_count, 3)
        for call, scope in zip(cursor.execute.call_args_list, [["EN", "VN"], ["EN"], ["VN"]]):
            sql, params = call.args
            for clause in ["d.document_id = ANY(%s::text[])", "d.allowed_roles && %s::text[]",
                           "d.company = %s::text", "c.metadata @> %s::jsonb", "coalesce(d.processing_status, 'ready') = 'ready'"]:
                self.assertIn(clause, sql)
                self.assertLess(sql.index(clause), sql.index("LIMIT"))
            self.assertIn(scope, [x for x in params if isinstance(x, list)])

    def test_incomplete_language_map_and_unsupported_query_language_fail_before_search(self):
        for options in [dict(document_languages={"EN": "en"}, document_ids=["EN", "VN"]),
                        dict(document_languages={"EN": "en"}), dict(query_language="fr")]:
            service, llm = self.service()
            with self.assertRaises(ValueError):
                service.retrieve(RetrievalRequest(query="question"), method="translated_hybrid", **options)
            service.repository.similarity_search.assert_not_called()
            llm.generate.assert_not_called()

    def test_generate_answer_preserves_question_and_forwards_scope_and_known_language(self):
        service, llm = self.service()
        llm.generate.return_value = '{"translation":"Revenue?"}'
        answer_llm = MagicMock()
        answer_llm.generate.return_value = "Answer [S1]"
        result = RAGService(service, answer_llm).generate_answer(
            "Doanh thu?", roles=["employee"], retrieval_method="translated_hybrid",
            document_ids=["EN", "VN"], query_language="vn",
            document_languages={"EN": "en", "VN": "vn"})
        self.assertEqual(result.answer, "Answer [S1]")
        self.assertIn("Doanh thu?", answer_llm.generate.call_args.args[0])
        self.assertEqual(result.contexts[0]["retrieval_details"]["lexical_queries"]["en"], "Revenue?")

    def test_owned_translation_provider_is_lazy_and_closed_even_if_repository_close_fails(self):
        service, llm = self.service()
        service.query_translator = None
        with patch("core.llm.groq_provider.GroqProvider", return_value=llm) as factory:
            service.retrieve(RetrievalRequest(query="question"), method="dense")
            factory.assert_not_called()
            service.retrieve(RetrievalRequest(query="question"), method="translated_hybrid")
            factory.assert_called_once()
            service.repository.close.side_effect = RuntimeError("close failed")
            with self.assertRaises(RuntimeError):
                service.close()
            llm.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
