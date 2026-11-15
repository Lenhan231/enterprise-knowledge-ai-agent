import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.knowledge.agent import KnowledgeAgent
from core.agents.orchestration.execution import TaskOutcome, outcome_status
from core.agents.orchestration.response import assemble_response, compose_single_result
from core.agents.sql.analytics_agent import AnalyticsAgent
from core.models.agents import AgentRequest, AgentResult, Evidence, VerifiedIdentity
from core.models.agent_plan import AgentPlan, AgentTask


class ContextOnlyRag:
    def __init__(self):
        self.calls = []
        self.answer_calls = []
        self.contexts = [{
            "source_id": "S1", "document_name": "policy.pdf", "chunk_index": 3,
            "content": "Annual leave policy evidence.", "similarity_score": 0.9,
            "metadata": {"document_id": "DOC-1"}, "retrieval_method": "bm25",
        }]

    def retrieve_for_answer(self, question, **options):
        self.calls.append((question, options))
        return self.contexts, False

    def generate_answer(self, question, **options):
        self.answer_calls.append((question, options))
        return SimpleNamespace(
            answer="Annual leave is one-twelfth of the annual entitlement per completed month [S1].",
            source_ids=["S1"], contexts=self.contexts,
            insufficient_context=False, verification=None,
        )


class Provider:
    def __init__(self, answer):
        self.answer = answer
        self.prompt = ""

    def generate(self, prompt):
        self.prompt = prompt
        return json.dumps(self.answer, ensure_ascii=False)


class TextProvider:
    def __init__(self, answer):
        self.answer = answer
        self.prompt = ""

    def generate(self, prompt):
        self.prompt = prompt
        return self.answer


class ContextOnlySQL:
    def __init__(self, provider):
        self.provider = provider

    async def run_payload(self, _request):
        return {
            "ok": True,
            "rows": [{"revenue": 125}],
            "evidence": [{"source": "commerce.sales"}],
            "metadata": {"source": ["commerce.sales"], "metrics": {},
                         "semantic_interpretation": {"metric": "revenue"}},
            "limitations": [],
        }

    def _provider(self):
        return self.provider

    async def close(self):
        pass


class SharedAnswerComposerTest(unittest.IsolatedAsyncioTestCase):
    async def test_final_layer_receives_each_specialist_response_with_global_citations(self):
        knowledge = AgentTask(id="k", agent="knowledge", question="Compare policy and revenue")
        sql = AgentTask(id="s", agent="sql", question="Compare policy and revenue")
        plan = AgentPlan(objective="Compare policy and revenue", tasks=[knowledge, sql])
        execution = SimpleNamespace(outcomes={
            "k": TaskOutcome(knowledge, "complete", result=AgentResult(
                answer="Policy requires manager approval [S1].", agent="knowledge",
                evidence=[Evidence(citation_id="S1", source_type="document", source="policy.pdf",
                                   content="Manager approval is required.")],
            )),
            "s": TaskOutcome(sql, "complete", result=AgentResult(
                answer="Revenue was 125 [S1].", agent="sql",
                evidence=[Evidence(citation_id="S1", source_type="database", source="commerce.sales",
                                   content="Revenue row: 125")],
                data={"rows": [{"revenue": 125}]},
            )),
        }, trace=[], invocations=2)
        provider = Provider({"answer": "Policy requires manager approval [S1]. Revenue was 125 [S2].",
                             "used_tasks": ["k", "s"]})

        result = await assemble_response(AgentRequest(question=plan.objective), plan, execution, provider)

        self.assertFalse(result.metadata["fallback"])
        self.assertIn('Policy requires manager approval [S1].', provider.prompt)
        self.assertIn('Revenue was 125 [S2].', provider.prompt)
        self.assertEqual([item.citation_id for item in result.evidence], ["S1", "S2"])

    async def test_task_coverage_uses_citations_not_model_task_name_guess(self):
        task = AgentTask(id="k", agent="knowledge", question="Who approves this purchase?")
        plan = AgentPlan(objective=task.question, tasks=[task])
        specialist_result = AgentResult(
            answer="", agent="knowledge",
            evidence=[Evidence(source_type="document", source="policy.pdf",
                               content="The department head and Finance approve the purchase.")],
        )
        execution = SimpleNamespace(
            outcomes={"k": TaskOutcome(task, "complete", result=specialist_result)},
            trace=[], invocations=1,
        )
        provider = Provider({
            "answer": "The department head and Finance approve it [S1].",
            "used_tasks": ["knowledge"],  # Agent label, while the planner task ID is "k".
        })

        result = await assemble_response(
            AgentRequest(question=task.question), plan, execution, provider,
        )

        self.assertEqual(result.answer, provider.answer["answer"])
        self.assertFalse(result.metadata["fallback"])
        self.assertIn('Valid task IDs for used_tasks: ["k"]', provider.prompt)
        self.assertIn('"specialist_response": ""', provider.prompt)

    async def test_knowledge_agent_returns_context_without_answer_generation(self):
        rag = ContextOnlyRag()
        agent = KnowledgeAgent(rag)
        identity = VerifiedIdentity(subject="employee-1", permissions={"documents:read"},
                                    document_roles={"employee"})
        request = AgentRequest(question="chính sách nghỉ phép năm", identity=identity,
                               metadata={"retrieval_method": "bm25"})

        with patch.dict("os.environ", {"KNOWLEDGE_MULTIQUERY_ENABLED": "1"}):
            result = await agent.run(request)

        self.assertIn("one-twelfth", result.answer)
        self.assertEqual(result.evidence[0].content, "Annual leave policy evidence.")
        self.assertEqual(rag.answer_calls[0][1]["retrieval_method"], "bm25")
        self.assertTrue(rag.answer_calls[0][1]["decompose"])

    async def test_sql_agent_summarizes_rows_and_preserves_structured_result(self):
        provider = TextProvider("Doanh thu ghi nhận là 125 [S1].")
        agent = AnalyticsAgent(ContextOnlySQL(provider))

        result = await agent.run(AgentRequest(question="Doanh thu hiện tại là bao nhiêu?"))

        self.assertEqual(result.data["rows"], [{"revenue": 125}])
        self.assertEqual(result.evidence[0].source, "commerce.sales")
        self.assertIn("Doanh thu ghi nhận là 125 [S1].", result.answer)
        self.assertIn("Canonical metric definitions", provider.prompt)
        self.assertIn('"revenue": 125', provider.prompt)

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
        self.assertIn("The product with the highest", provider.prompt)
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
