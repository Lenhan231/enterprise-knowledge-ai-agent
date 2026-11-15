import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.knowledge.agent import KnowledgeAgent
from core.agents.decision_support.execution import outcome_status
from core.agents.decision_support.response import compose_single_result
from core.models.agents import AgentRequest, AgentResult, Evidence, VerifiedIdentity


class ContextOnlyRag:
    def __init__(self):
        self.calls = []
        self.contexts = [{
            "source_id": "S1", "document_name": "policy.pdf", "chunk_index": 3,
            "content": "Annual leave policy evidence.", "similarity_score": 0.9,
            "metadata": {"document_id": "DOC-1"}, "retrieval_method": "bm25",
        }]

    def retrieve_for_answer(self, question, **options):
        self.calls.append((question, options))
        return self.contexts, False

    def generate_answer(self, *_args, **_kwargs):
        raise AssertionError("Knowledge retrieval must not generate a specialist answer")


class Provider:
    def __init__(self, answer):
        self.answer = answer
        self.prompt = ""

    def generate(self, prompt):
        self.prompt = prompt
        return json.dumps(self.answer, ensure_ascii=False)


class SharedAnswerComposerTest(unittest.IsolatedAsyncioTestCase):
    async def test_knowledge_agent_returns_context_without_answer_generation(self):
        rag = ContextOnlyRag()
        agent = KnowledgeAgent(rag)
        identity = VerifiedIdentity(subject="employee-1", permissions={"documents:read"},
                                    document_roles={"employee"})
        request = AgentRequest(question="chính sách nghỉ phép năm", identity=identity,
                               metadata={"retrieval_method": "bm25"})

        with patch.dict("os.environ", {"KNOWLEDGE_MULTIQUERY_ENABLED": "1"}):
            result = await agent.run(request)

        self.assertEqual(result.answer, "")
        self.assertEqual(result.evidence[0].content, "Annual leave policy evidence.")
        self.assertEqual(rag.calls[0][1]["retrieval_method"], "bm25")
        self.assertTrue(rag.calls[0][1]["decompose"])

    async def test_single_sql_result_uses_shared_language_aware_composer(self):
        answer = "Sản phẩm bán chạy nhất là UrbanVN RP-49 với 12 sản phẩm [S1]."
        provider = Provider({"answer": answer, "used_tasks": ["sql"]})
        request = AgentRequest(question="sản phẩm bán chạy nhất tính đến nay")
        specialist_result = AgentResult(
            answer="The product with the highest total inventory_units_sold is UrbanVN RP-49 with 12 units sold.",
            agent="analytics",
            evidence=[Evidence(citation_id="S1", source_type="database", source="commerce.inventory")],
            data={"rows": [
                {"product_name": "UrbanVN RP-49", "inventory_units_sold": 12},
                {"product_name": "VietMotion RP-60", "inventory_units_sold": 4},
            ], "query_status": "executed"},
            metadata={"ok": True},
        )

        with patch.dict("os.environ", {"KNOWLEDGE_CLAIM_VERIFICATION_ENABLED": "0",
                                        "KNOWLEDGE_COMPLETENESS_RULE": "1",
                                        "KNOWLEDGE_STRICT_CITATION_RULE": "1"}):
            result = await compose_single_result(request, "sql", specialist_result, provider)

        self.assertEqual(result.answer, answer)
        self.assertIn("strictly in the same language", provider.prompt)
        self.assertIn("Address every material part", provider.prompt)
        self.assertIn("every factual sentence and bullet", provider.prompt)
        self.assertNotIn("The product with the highest", provider.prompt)
        self.assertEqual(result.data["rows"], specialist_result.data["rows"])

    async def test_single_bestselling_product_uses_grounded_deterministic_answer(self):
        request = AgentRequest(question="sản phẩm bán chạy nhất")
        raw = AgentResult(
            answer="Query completed.", agent="analytics",
            evidence=[Evidence(citation_id="S1", source_type="database", source="commerce.order_items"),
                      Evidence(citation_id="S2", source_type="database", source="commerce.products")],
            data={"rows": [{"product_id": 1086, "product_name": "MekongFit RP-32", "total_qty": 152}],
                  "query_status": "executed"}, metadata={"ok": True},
        )

        result = await compose_single_result(request, "sql", raw, provider=None)

        self.assertEqual(result.answer,
                         "Sản phẩm bán chạy nhất là MekongFit RP-32 với 152 sản phẩm đã bán [S1] [S2].")

    async def test_claim_verification_setting_runs_on_the_final_shared_answer(self):
        from core.rag.claim_verification import VerificationOutcome

        provider = Provider({"answer": "Policy grants 12 days [S1].", "used_tasks": ["knowledge"]})
        request = AgentRequest(question="What is the annual leave entitlement?")
        specialist_result = AgentResult(
            answer="Specialist draft that is not passed to the composer.", agent="knowledge",
            evidence=[Evidence(citation_id="S1", source_type="document", source="policy.pdf",
                               content="Annual paid leave is 12 working days.")],
        )
        with patch.dict("os.environ", {"KNOWLEDGE_CLAIM_VERIFICATION_ENABLED": "1"}), \
             patch("core.rag.claim_verification.verify_answer",
                   return_value=VerificationOutcome(status="supported", reason="all_claims_supported")) as verify:
            result = await compose_single_result(request, "knowledge", specialist_result, provider)

        verify.assert_called_once()
        self.assertEqual(result.metadata["claim_verification"]["status"], "supported")

    def test_successful_empty_sql_result_remains_answerable(self):
        result = AgentResult(
            answer="", agent="analytics",
            evidence=[Evidence(source_type="database", source="commerce.products")],
            data={"rows": [], "query_status": "executed"}, metadata={"ok": False},
        )

        self.assertEqual(outcome_status(result), "complete")

    async def test_null_sql_result_is_explained_by_shared_composer(self):
        request = AgentRequest(question="Doanh thu tháng 3 năm nay")
        raw = AgentResult(
            answer="Query completed.", agent="analytics",
            evidence=[Evidence(citation_id="S1", source_type="database", source="commerce.sales")],
            data={"rows": [{"revenue": None}], "parameters": ["2026-03-01", "2026-04-01"],
                  "query_status": "executed"}, metadata={"ok": True},
        )

        result = await compose_single_result(request, "sql", raw, provider=None)

        self.assertIn("kết quả revenue là NULL", result.answer)
        self.assertIn("không đồng nghĩa với doanh thu bằng không", result.answer)

if __name__ == "__main__":
    unittest.main()
