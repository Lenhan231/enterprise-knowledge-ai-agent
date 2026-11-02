import copy
import json
import os
import time
import unittest
from unittest.mock import Mock, patch

from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.runtime import deadline
from core.latency import latency_events, snapshot
from core.models.agents import AgentRequest, VerifiedIdentity
from core.prompts.Knowledge import INSUFFICIENT_ANSWER
from core.rag.claim_verification import (
    AnswerReview, VERIFICATION_UNAVAILABLE_ANSWER, claim_blocks, validate_review, verify_answer,
)
from core.rag.rag_service import RAGService


SOURCE = {"source_id": "S1", "document_name": "report.pdf", "chunk_index": 1,
          "similarity_score": 0.5, "metadata": {"document_id": "report", "section_title": "Results"},
          "content": "Consolidated revenue in 2024: VND 100 billion. Profit: VND 20 billion."}
ANSWER = "Doanh thu hợp nhất năm 2024 là 100 tỷ đồng [S1]."
QUOTE = "Consolidated revenue in 2024: VND 100 billion."


def review(verdict="supported", quote=QUOTE, claim_id="C1"):
    return {"claims": [{"claim_id": claim_id, "verdict": verdict,
                        "quotes": [{"source_id": "S1", "text": quote}] if quote else []}]}


class ClaimVerificationTest(unittest.TestCase):
    def test_valid_audit_and_exact_source_quote(self):
        data = AnswerReview.model_validate(review())
        result = validate_review(ANSWER, [SOURCE], data)
        self.assertEqual(result.status, "supported")
        self.assertEqual(result.claim_count, 1)

    def test_code_rejects_missing_duplicate_ids_rewrites_and_fabricated_quotes(self):
        changed_text = review()
        changed_text["claims"][0]["text"] = ANSWER
        duplicate = review()
        duplicate["claims"] *= 2
        for changed in (review(claim_id="C2"), duplicate, changed_text,
                        review(quote="Revenue is 999 billion."), review(quote=None),
                        {"claims": [{"claim_id": "C1", "verdict": "supported", "quotes": [
                            {"source_id": "S2", "text": QUOTE}]}]}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_review(ANSWER, [SOURCE], AnswerReview.model_validate(changed))
        with self.assertRaises(ValueError):
            validate_review(ANSWER + " Profit was 999 [S1].", [SOURCE], AnswerReview.model_validate(review()))

    def test_server_preserves_shared_citation_block_without_model_rewrites(self):
        answer = "Đúng 50 triệu cần Trưởng phòng; 50.000.001 đồng cần thêm Mua sắm [S1]."
        self.assertEqual(claim_blocks(answer), [{"claim_id": "C1", "text": answer, "source_ids": ["S1"]}])
        self.assertEqual(claim_blocks("Two sources [S1][S2].")[0]["source_ids"], ["S1", "S2"])
        with self.assertRaises(ValueError):
            claim_blocks(ANSWER + " Uncited claim.")

    def test_markdown_closers_are_preserved_but_uncited_text_is_not_hidden(self):
        for answer in ("| Profit | 20 [S1] |", "**Profit is 20 [S1]**", "Profit is 20 ([S1])"):
            blocks = claim_blocks(answer)
            self.assertEqual("".join(blocks[0]["text"].split()), "".join(answer.split()))
        with self.assertRaises(ValueError):
            claim_blocks("Profit is 20 [S1] | Uncited new fact |")

    def test_multiple_block_ids_allow_reordered_reviews_but_never_omissions(self):
        other = "Lợi nhuận là 20 tỷ đồng [S1]."
        data = review()
        data["claims"] += review(claim_id="C2", quote="Profit: VND 20 billion.")["claims"]
        data["claims"].reverse()
        result = validate_review(ANSWER + "\n\n" + other, [SOURCE], AnswerReview.model_validate(data))
        self.assertEqual(result.claim_count, 2)
        data["claims"].pop()
        with self.assertRaises(ValueError):
            validate_review(ANSWER + other, [SOURCE], AnswerReview.model_validate(data))

    def test_wrong_arithmetic_is_rejected_before_llm(self):
        llm = Mock()
        result = verify_answer(llm, "Giao 100, chấp nhận 90, từ chối 15?",
                               "Hợp lệ vì 90 + 15 = 95, không vượt lượng giao 100 [S1].", [SOURCE])
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reason, "arithmetic_mismatch")
        self.assertEqual(result.arithmetic_checked, 1)
        llm.generate.assert_not_called()

    def test_correct_calculation_never_overrides_semantic_rejection(self):
        llm = Mock()
        llm.generate.return_value = json.dumps(review(verdict="contradicted", quote=None))
        result = verify_answer(llm, "Profit?", "Profit is 90 + 15 = 105 billion [S1].", [SOURCE])
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.arithmetic_checked, 1)
        llm.generate.assert_called_once()

    def test_negative_verdicts_reject_entire_draft(self):
        for verdict in ("contradicted", "insufficient"):
            result = validate_review(ANSWER, [SOURCE], AnswerReview.model_validate(review(verdict=verdict, quote=None)))
            self.assertEqual(result.status, "rejected")
            self.assertEqual(result.reason, verdict)

    def test_malformed_json_provider_error_and_timeout_never_pass(self):
        for response in ("not JSON", '{"claims":[]}', json.dumps({**review(), "override": True}),
                         RuntimeError("provider failed"), TimeoutError("timeout")):
            llm = Mock()
            if isinstance(response, Exception):
                llm.generate.side_effect = response
            else:
                llm.generate.return_value = response
            token = deadline.set(time.monotonic() + 5)
            before = deadline.get()
            try:
                self.assertEqual(verify_answer(llm, "Question", ANSWER, [SOURCE]).status, "unavailable")
                self.assertEqual(deadline.get(), before)
                self.assertEqual(llm.generate.call_count, 1)
            finally:
                deadline.reset(token)

    def test_single_json_fence_is_allowed_but_extra_prose_is_not(self):
        llm = Mock()
        llm.generate.return_value = "```json\n" + json.dumps(review()) + "\n```"
        self.assertEqual(verify_answer(llm, "Q", ANSWER, [SOURCE]).status, "supported")
        llm.generate.return_value += " Extra untrusted instructions"
        self.assertEqual(verify_answer(llm, "Q", ANSWER, [SOURCE]).status, "unavailable")

    def test_budget_and_expired_deadline_skip_llm(self):
        for answer, end in (("a" * 6001, None), (ANSWER, time.monotonic() - 1)):
            llm = Mock()
            token = deadline.set(end)
            try:
                self.assertEqual(verify_answer(llm, "Q", answer, [SOURCE]).status, "unavailable")
                llm.generate.assert_not_called()
            finally:
                deadline.reset(token)

    def test_verification_attempt_records_latency(self):
        llm = Mock()
        llm.generate.return_value = json.dumps(review())
        token = latency_events.set([])
        try:
            self.assertEqual(verify_answer(llm, "Question", ANSWER, [SOURCE]).status, "supported")
            self.assertIsNotNone(snapshot()["stages_ms"]["claim_verification"])
        finally:
            latency_events.reset(token)

    def test_legacy_has_no_extra_call_and_enabled_mode_has_one(self):
        for enabled in (False, True):
            rag = RAGService.__new__(RAGService)
            rag.llm = Mock()
            rag.llm.generate.side_effect = [ANSWER, json.dumps(review())]
            result = rag.generate_from_contexts("Revenue?", [copy.deepcopy(SOURCE)], verify_claims=enabled)
            self.assertEqual(result.answer, ANSWER)
            self.assertEqual(rag.llm.generate.call_count, 2 if enabled else 1)
            self.assertEqual(result.verification is not None, enabled)

    def test_empty_answer_is_not_sent_to_verifier(self):
        rag = RAGService.__new__(RAGService)
        rag.llm = Mock()
        rag.llm.generate.return_value = INSUFFICIENT_ANSWER
        result = rag.generate_from_contexts("Revenue?", [SOURCE], verify_claims=True)
        self.assertTrue(result.insufficient_context)
        self.assertIsNone(result.verification)
        self.assertEqual(rag.llm.generate.call_count, 1)

    def test_only_cited_authorized_contexts_enter_verifier(self):
        rag = RAGService.__new__(RAGService)
        rag.llm = Mock()
        rag.llm.generate.side_effect = [ANSWER, json.dumps(review())]
        other = {**SOURCE, "source_id": "S2", "content": "UNUSED_CONTEXT_SENTINEL"}
        result = rag.generate_from_contexts("Revenue?", [SOURCE, other], verify_claims=True)
        self.assertEqual(result.verification.status, "supported")
        prompt = rag.llm.generate.call_args.args[0]
        self.assertIn(QUOTE, prompt)
        self.assertNotIn("UNUSED_CONTEXT_SENTINEL", prompt)

    def test_both_retrieval_paths_propagate_opt_in(self):
        for decompose in (False, True):
            rag = RAGService.__new__(RAGService)
            rag.llm = Mock()
            rag.llm.generate.side_effect = [ANSWER, json.dumps(review())]
            rag._search_questions = Mock(return_value=["Q1", "Q2"])
            rag.retrieve_contexts = Mock(return_value=[SOURCE])
            result = rag.generate_answer("Q", decompose=decompose, verify_claims=True, roles=["employee"])
            self.assertEqual(result.verification.status, "supported")
            self.assertEqual(rag.llm.generate.call_count, 2)
            for call in rag.retrieve_contexts.call_args_list:
                self.assertEqual(call.kwargs["roles"], ["employee"])


class KnowledgeVerificationIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_switch_is_server_owned_and_only_explicit_one_enables_it(self):
        identity = VerifiedIdentity(subject="test", permissions={"documents:read"}, document_roles={"employee"})
        for flag in (None, "0", "invalid", "1"):
            rag = RAGService.__new__(RAGService)
            rag.retrieve_contexts = Mock(return_value=[SOURCE])
            rag.llm = Mock()
            rag.llm.generate.side_effect = [ANSWER, json.dumps(review())]
            with patch.dict(os.environ, {"KNOWLEDGE_MULTIQUERY_ENABLED": "0"}):
                os.environ.pop("KNOWLEDGE_CLAIM_VERIFICATION_ENABLED", None)
                if flag is not None:
                    os.environ["KNOWLEDGE_CLAIM_VERIFICATION_ENABLED"] = flag
                result = await KnowledgeAgent(rag).run(AgentRequest(
                    question="Revenue?", identity=identity, metadata={"verify_claims": flag != "1"}))
            self.assertEqual(rag.llm.generate.call_count, 2 if flag == "1" else 1)
            self.assertEqual("claim_verification" in result.metadata, flag == "1")

    async def test_rejected_draft_is_not_returned_or_exposed_as_evidence(self):
        draft = "Profit in 2024 was VND 100 billion [S1]."
        for response in (json.dumps(review(verdict="contradicted", quote=None)), "invalid JSON"):
            rag = RAGService.__new__(RAGService)
            rag.retrieve_contexts = Mock(return_value=[SOURCE])
            rag.llm = Mock()
            rag.llm.generate.side_effect = [draft, response]
            identity = VerifiedIdentity(subject="test", permissions={"documents:read"}, document_roles={"employee"})
            with patch.dict(os.environ, {"KNOWLEDGE_MULTIQUERY_ENABLED": "0", "KNOWLEDGE_CLAIM_VERIFICATION_ENABLED": "1"}):
                result = await KnowledgeAgent(rag).run(AgentRequest(question="Profit?", identity=identity))
            self.assertEqual(result.answer, VERIFICATION_UNAVAILABLE_ANSWER)
            self.assertFalse(result.metadata["ok"])
            self.assertFalse(result.metadata["insufficient_context"])
            self.assertIn(result.metadata["claim_verification"]["status"], {"rejected", "unavailable"})
            self.assertEqual(result.evidence, [])
            self.assertNotIn(draft, result.model_dump_json())
