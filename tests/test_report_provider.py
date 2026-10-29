import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.llm.groq_provider import GroqProvider
from core.agents.knowledge_agent import KnowledgeAgent
from core.models.agents import AgentRequest, VerifiedIdentity


class ReportProviderTest(unittest.TestCase):
    @patch("core.llm.groq_provider.OpenAI")
    def test_report_budget_is_opt_in_and_timeout_is_bounded(self, openai):
        client = openai.return_value
        client.responses.create.return_value = MagicMock(output_text="answer")
        client.with_options.return_value.responses.create.return_value = MagicMock(output_text="report")
        provider = GroqProvider(api_key="fake-test-key")
        self.assertEqual(provider.generate("chat"), "answer")
        self.assertEqual(client.responses.create.call_args.kwargs["max_output_tokens"], 1000)
        self.assertEqual(provider.generate("report", max_output_tokens=4096), "report")
        client.with_options.assert_called_once_with(timeout=60, max_retries=0)
        self.assertEqual(client.with_options.return_value.responses.create.call_args.kwargs["max_output_tokens"], 4096)


class DocumentScopeTest(unittest.IsolatedAsyncioTestCase):
    @patch("core.database.commerce_repository.create_repository_from_env", new_callable=AsyncMock)
    async def test_document_runtime_does_not_connect_to_analytics(self, factory):
        from core.database.commerce_repository import LazyCommerceRepository
        repository = LazyCommerceRepository()
        await repository.close()
        factory.assert_not_awaited()
        factory.return_value.execute_approved_query.return_value = [{"revenue": 100}]
        self.assertEqual(await repository.execute_approved_query("query"), [{"revenue": 100}])
        factory.assert_awaited_once()

    async def test_report_retrieval_passes_only_verified_roles(self):
        rag = MagicMock()
        rag.retrieve_contexts.return_value = [{"document_name": "permitted.md", "content": "Allowed policy",
                                             "metadata": {}, "chunk_index": 0}]
        agent = KnowledgeAgent(rag)
        request = AgentRequest(question="Policy", metadata={"roles": ["admin"]}, identity=VerifiedIdentity(
            subject="employee", permissions={"documents:read"}, document_roles={"employee"}))
        evidence = await agent.retrieve(request)
        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["roles"], ["employee"])
        self.assertEqual(evidence[0].source, "permitted.md")
        with self.assertRaises(PermissionError):
            await agent.retrieve(request.model_copy(update={"identity": None}))


if __name__ == "__main__":
    unittest.main()
