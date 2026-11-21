from __future__ import annotations

import json
import unittest
from pathlib import Path

from core.agents.sql.agent import SQLAnalyticsAgent
from core.agents.sql.text_to_sql import build_sql_prompt
from followup_adapter import adapt_followup_case


HERE = Path(__file__).resolve().parent
CASES = json.loads((HERE / "cases_v3_draft.json").read_text(encoding="utf-8"))["cases"]


class FollowupAdapterTests(unittest.TestCase):
    def test_all_five_followups_become_direct_sql_requests(self):
        followups = [case for case in CASES if case["category"] == "sql_followup_context"]
        self.assertEqual(len(followups), 5)
        for case in followups:
            adapted = adapt_followup_case(case)
            request = adapted.to_chat_request()
            self.assertEqual(request.agent_mode, "sql")
            self.assertEqual(request.metadata, {})
            agent_question = SQLAnalyticsAgent._query_text(request)
            prompt = build_sql_prompt(
                agent_question,
                metric_names=set(),
                allowed_sources={"commerce.sales"},
                schema_columns={"commerce.sales": {"date", "cogs", "revenue"}},
                schema_tables={"commerce.sales"},
            )
            self.assertIn(case["conversation_setup"]["prior_user_question"], request.question)
            self.assertIn(case["question"], request.question)
            self.assertIn(case["conversation_setup"]["prior_user_question"], prompt)
            self.assertIn(case["question"], prompt)
            self.assertIn("Approved semantic context from that user request", prompt)
            self.assertIn(json.dumps(
                case["conversation_setup"]["semantic_context"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ), request.question)
            self.assertEqual(adapted.evaluation_mode, "context-conditioned SQL; not conversational-memory evaluation")

    def test_short_followup_requires_inherited_metric_and_time(self):
        case = next(item for item in CASES if item["id"] == "B40-026")
        adapted = adapt_followup_case(case)
        self.assertEqual(case["question"], "Hãy trình bày theo từng tháng.")
        self.assertIn("COGS", adapted.question)
        self.assertIn('"start":"2024-01-01"', adapted.question)
        self.assertIn('"end_exclusive":"2025-01-01"', adapted.question)

    def test_no_gold_sql_parameters_rows_or_assistant_answer_are_serialized(self):
        case = dict(next(item for item in CASES if item["id"] == "B40-027"))
        case.update(
            gold_sql="LEAKED GOLD SQL",
            gold_parameters=["LEAKED PARAMETER"],
            gold_result=[{"LEAKED": "RESULT"}],
        )
        adapted = adapt_followup_case(case)
        for forbidden in ("LEAKED GOLD SQL", "LEAKED PARAMETER", "LEAKED"):
            self.assertNotIn(forbidden, adapted.question)

    def test_context_digest_mismatch_is_rejected(self):
        case = dict(next(item for item in CASES if item["id"] == "B40-028"))
        setup = dict(case["conversation_setup"])
        setup["semantic_context"] = dict(setup["semantic_context"])
        setup["semantic_context"]["start"] = "2022-01-01"
        case["conversation_setup"] = setup
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            adapt_followup_case(case)

    def test_unapproved_context_fields_are_rejected(self):
        case = dict(next(item for item in CASES if item["id"] == "B40-030"))
        setup = dict(case["conversation_setup"])
        setup["semantic_context"] = dict(setup["semantic_context"], gold_sql="SELECT 1")
        from followup_adapter import canonical_sha256
        setup["semantic_context_sha256"] = canonical_sha256(setup["semantic_context"])
        case["conversation_setup"] = setup
        with self.assertRaisesRegex(ValueError, "forbidden field"):
            adapt_followup_case(case)

    def test_assistant_output_injection_is_rejected(self):
        case = dict(next(item for item in CASES if item["id"] == "B40-029"))
        setup = dict(case["conversation_setup"], assistant_output_injected=True)
        case["conversation_setup"] = setup
        with self.assertRaisesRegex(ValueError, "assistant output"):
            adapt_followup_case(case)

    def test_non_followup_case_is_rejected(self):
        case = next(item for item in CASES if item["id"] == "B40-001")
        with self.assertRaisesRegex(ValueError, "follow-up cases only"):
            adapt_followup_case(case)


if __name__ == "__main__":
    unittest.main()
