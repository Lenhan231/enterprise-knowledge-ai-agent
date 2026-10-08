import json
import os
from pathlib import Path
import sys
import unittest
from datetime import date
from unittest.mock import Mock, patch

import httpx
from openai import APIConnectionError, APIStatusError, RateLimitError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.intent_classifier import IntentClassifier
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.commerce_decision_support import COMMERCE_DECISION_PROFILES, resolve_commerce_decision_domain
from core.analytics.sql_safety import UnsafeAnalyticsQuery
from core.llm.llm_interface import EmptyLLMResponseError
from core.agents.knowledge_agent import (
    KnowledgeAgent,
    _rank_commerce_reference_evidence,
)
from core.agents.report_agent import (
    ReportAgent, _commerce_safe_fallback, _commerce_question_safe_fallback, _format_commerce_number,
    _asks_for_unavailable_promotion_roi,
    _generate_conditional_draft, _ensure_commerce_dataset_disclosure,
    _has_unsupported_campaign_causal_claim,
    _decision_numeric_facts_match_cited_evidence,
    _unsupported_decision_numeric_tokens,
    _commerce_schema_gap_citation_failure, _financial_facts_match_cited_evidence, _format_prompt_evidence,
    _has_untranslated_prose, _has_unsolicited_commerce_recommendation, _has_unsupported_logistics_intervention,
    _claims_missing_commerce_dimension_is_available,
    _suggests_unsupported_inventory_transfer,
    _has_unprovided_logistics_fields, _omits_cited_logistics_method,
    _report_validation_failure, _has_unsupported_monotonic_commerce_trend,
    _asks_for_operating_steps, _is_decision_support_request, _is_financial_summary,
    _commerce_requested_observation_missing, _commerce_fill_rate_missing_percent,
    _has_multiple_unrequested_actions,
)
from core.agents.router import AgentRouter
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.agents.report_agent import (
    _has_unsupported_numeric_decision_gate,
    _normalize_numeric_citations,
    _is_decision_suggestions_request,
)
from core.models.agents import AgentRequest, AgentResult, Evidence
from core.models.intent import IntentResult
from core.rag.rag_service import RAGResult
from core.llm import provider_fallback


class AgentFlowTest(unittest.TestCase):
    def tearDown(self):
        provider_fallback._huggingface_fallback_disabled = False

    def test_transfer_guard_distinguishes_recommendations_from_negated_advice(self):
        for answer in (
            "Do not recommend a transfer from category aggregates.",
            "The evidence does not support that we should transfer inventory.",
            "Không nên điều chuyển hàng khi chưa đối chiếu SKU và địa điểm.",
            "Chưa khuyến nghị phân bổ lại hàng dựa trên các aggregate này.",
            "Chỉ cân nhắc điều chuyển sau khi đối chiếu SKU gửi/nhận, tồn khả dụng và nhu cầu.",
            "Only consider a transfer after matching SKU-level stock and destination demand.",
        ):
            with self.subTest(answer=answer):
                self.assertFalse(_suggests_unsupported_inventory_transfer(answer))

        self.assertTrue(_suggests_unsupported_inventory_transfer("We should transfer stock."))
        self.assertTrue(_suggests_unsupported_inventory_transfer("Nên điều chuyển hàng."))

    def test_decision_detector_catches_evidence_gaps_and_inflected_reallocation(self):
        self.assertTrue(_is_decision_support_request(
            "Which product categories have the most stockout-flagged SKUs, and what evidence is still needed before reallocating stock?"
        ))
        self.assertTrue(_is_decision_support_request("Should we be reallocating inventory?"))
        self.assertTrue(_is_decision_support_request("What data is needed before inventory reallocation?"))
        self.assertTrue(_is_decision_support_request("How can we reduce inventory stockouts?"))
        self.assertTrue(_is_decision_support_request(
            "Does the evidence justify increasing campaign budgets?"
        ))
        self.assertTrue(_is_decision_support_request(
            "Tổng stock_on_hand theo danh mục có đủ căn cứ để điều chuyển hàng không?"
        ))
        self.assertTrue(_is_decision_support_request(
            "Có đủ căn cứ để thay đổi kế hoạch giao hàng không?"
        ))
        self.assertFalse(_is_decision_support_request("Did inventory stockouts reduce last year?"))
        self.assertFalse(_is_decision_support_request("Which category had the most stockout-flagged products?"))

    def test_sufficiency_question_uses_dynamic_inventory_rows_and_withholds_transfer(self):
        question = "Tổng stock_on_hand theo danh mục có đủ căn cứ để điều chuyển hàng không?"
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Inventory category totals",
                content=("question-specific SQL observations: "
                         '[{"category":"Outdoor","total_stock_on_hand":49929},'
                         '{"category":"Streetwear","total_stock_on_hand":45085}]'),
                metadata={
                    "commerce_domain": "inventory_allocation",
                    "commerce_observation_group": "question_specific_query",
                    "commerce_observations": [
                        {"category": "Outdoor", "total_stock_on_hand": 49929},
                        {"category": "Streetwear", "total_stock_on_hand": 45085},
                    ],
                },
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Inventory schema",
                content="The dataset lacks SKU/location matches, demand, transfer costs, and service constraints.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Synthetic inventory policy",
                content="Policy note",
                metadata={
                    "evidence_class": "company_policy_reference",
                    "synthetic_company_policy": True,
                    "source_publisher": "Commerce Demo (fictional organization)",
                    "source_notes": "Match SKU, available stock, demand, lead time, transfer cost, and service constraints.",
                },
            ),
        ]

        answer = _commerce_question_safe_fallback(
            question, evidence,
            decision_request=_is_decision_support_request(question),
        )

        self.assertIn("Chưa điều chuyển tồn kho", answer)
        self.assertIn("Outdoor", answer)
        self.assertIn("49.929", answer)
        self.assertIn("Tổng lượng tồn kho hiện có", answer)
        self.assertIn("Chưa điều chuyển tồn kho", answer)
        self.assertIn("[S1]", answer)

    def test_operating_step_detector_recognizes_policy_prerequisite_questions(self):
        for question in (
            "Which checks does the policy require before transferring inventory?",
            "What must be verified before moving stock between locations?",
            "Trong snapshot mới nhất, danh mục nào có nhiều stockout nhất và policy giả lập yêu cầu kiểm tra gì trước khi điều chuyển?",
            "Cần đối chiếu những gì trước khi phân bổ lại hàng?",
        ):
            with self.subTest(question=question):
                self.assertTrue(_asks_for_operating_steps(question))

    def test_decision_fallback_includes_overlap_when_question_says_reallocating(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Inventory category aggregate",
                content=('inventory_latest_by_category aggregate observations: '
                         '[{"snapshot_date":"2022-12-31","category":"Streetwear","stockout_products":134},'
                         '{"snapshot_date":"2022-12-31","category":"Outdoor","stockout_products":95}]'),
            ),
            Evidence(
                citation_id="C2", source_type="commerce_sql", source="Inventory flag-overlap aggregate",
                content=('inventory_latest_flag_overlap aggregate observations: '
                         '[{"snapshot_date":"2022-12-31","both_flagged_rows":232}]'),
                metadata={"commerce_aggregate_key": "inventory_latest_flag_overlap"},
            ),
            Evidence(citation_id="L1", source_type="commerce_schema", source="Commerce schema",
                     content="Category data has no matched SKU/location transfer evidence."),
            Evidence(citation_id="S1", source_type="document", source="Commerce Demo policy",
                     content="Only consider transfers after matching SKU, stock, demand and location.",
                     metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True}),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "Which product categories have the most stockout-flagged SKUs, and what evidence is still needed before reallocating stock?",
            evidence,
        )

        self.assertIn("232", answer)
        self.assertIn("[C2]", answer)
        self.assertIn("Do not rebalance inventory yet", answer)
        self.assertIn("SKU-level demand", answer)
        self.assertIn("[L1]", answer)
        self.assertIn("[S1]", answer)

    def test_dynamic_inventory_fallback_keeps_overlap_citation_with_fact(self):
        question = (
            "Should inventory be reallocated from overstocked categories to stockout categories? "
            "Compare recent evidence, check whether the flags overlap, and state what is still needed before moving stock."
        )
        rows = [{
            "snapshot_date": "2022-12-31", "category": "Streetwear",
            "stockout_products": 134, "overstock_products": 162,
        }]
        overlap = [{"snapshot_date": "2022-12-31", "both_flagged_rows": 232}]
        category_rows = [
            {"snapshot_date": "2022-12-31", "category": "Streetwear", "stockout_products": 134, "overstock_products": 162},
            {"snapshot_date": "2022-12-31", "category": "Outdoor", "stockout_products": 95, "overstock_products": 113},
        ]
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Inventory question query",
                content=f"question_specific_query observations: {json.dumps(rows)}",
                metadata={"commerce_domain": "inventory_allocation", "commerce_observations": rows},
            ),
            Evidence(
                citation_id="C2", source_type="commerce_sql", source="Inventory category aggregate",
                content=f"inventory_latest_by_category aggregate observations: {json.dumps(category_rows)}",
                metadata={
                    "commerce_observation_group": "inventory_latest_by_category",
                    "commerce_observations": category_rows,
                },
            ),
            Evidence(
                citation_id="C3", source_type="commerce_sql", source="Inventory flag-overlap aggregate",
                content=f"inventory_latest_flag_overlap aggregate observations: {json.dumps(overlap)}",
                metadata={
                    "commerce_aggregate_key": "inventory_latest_flag_overlap",
                    "commerce_observations": overlap,
                },
            ),
            Evidence(citation_id="L1", source_type="commerce_schema", source="Schema limits",
                     content="No SKU/location transfer evidence; lead time and transfer costs are absent."),
            Evidence(citation_id="S1", source_type="document", source="Commerce Demo policy",
                     content="Match demand, stock and location before transfer.", metadata={
                         "evidence_class": "company_policy_reference", "synthetic_company_policy": True,
                     }),
        ]

        answer = _commerce_question_safe_fallback(question, evidence, decision_request=True)

        self.assertIn("232 rows with both flags", answer)
        self.assertEqual(answer.count("232"), 1)
        self.assertIn("not unique incidents [C3]", answer)
        self.assertIn("stockout: Streetwear (134)", answer)
        self.assertIn("overstock: Streetwear (162)", answer)
        self.assertNotIn("None stockout", answer)
        self.assertIsNone(_report_validation_failure(answer, evidence, {"C1", "C2", "C3", "L1", "S1"}, question))
        self.assertFalse(_suggests_unsupported_inventory_transfer(answer))

        localized_question = "Trong snapshot tồn kho mới nhất, nhóm hàng nào có nhiều sản phẩm bị gắn cờ stockout nhất? Có nên chuyển hàng từ nhóm overstock sang không?"
        localized_answer = _commerce_question_safe_fallback(
            localized_question, evidence, decision_request=True,
        )
        self.assertEqual(localized_answer.count("232"), 1)
        self.assertIn("[C3]", localized_answer)

    def test_operating_step_detector_recognizes_vietnamese_data_checks_before_action(self):
        for question in (
            "Trước khi chuyển hàng giữa các nhóm có stockout và overstock, cần kiểm tra dữ liệu nào?",
            "Before transferring stock, what data should we check?",
        ):
            with self.subTest(question=question):
                self.assertTrue(_asks_for_operating_steps(question))
                self.assertTrue(_is_decision_support_request(question))

    def test_english_inventory_fallback_keeps_overlap_fact_in_english(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Inventory category aggregate",
                content=('inventory_latest_by_category aggregate observations: '
                         '[{"snapshot_date":"2022-12-31","category":"Streetwear","stockout_products":134}]'),
            ),
            Evidence(
                citation_id="C2", source_type="commerce_sql", source="Inventory flag-overlap aggregate",
                content=('inventory_latest_flag_overlap aggregate observations: '
                         '[{"snapshot_date":"2022-12-31","both_flagged_rows":232}]'),
                metadata={"commerce_aggregate_key": "inventory_latest_flag_overlap"},
            ),
            Evidence(citation_id="L1", source_type="commerce_schema", source="Schema limits",
                     content="No SKU/location transfer evidence."),
            Evidence(citation_id="S1", source_type="document", source="Commerce Demo policy",
                     content="Match SKU, demand, stock and location before transfer.",
                     metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True}),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "What evidence is needed before reallocating inventory from overstock to stockout categories?",
            evidence,
        )

        self.assertIn("In snapshot 2022-12-31, 232 product rows", answer)
        self.assertNotIn("Trong snapshot", answer)
        self.assertIn("[C2]", answer)
        self.assertIn("[S1]", answer)

    def test_inventory_reallocation_fallback_reports_category_review_cues(self):
        category_rows = [
            {"snapshot_date": "2022-12-31", "category": "Streetwear", "stockout_products": 134, "overstock_products": 162},
            {"snapshot_date": "2022-12-31", "category": "Outdoor", "stockout_products": 95, "overstock_products": 113},
        ]
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Latest inventory flags",
                content="inventory_latest_flag_overlap aggregate observations: [{\"snapshot_date\":\"2022-12-31\",\"both_flagged_rows\":232}]",
                metadata={"commerce_aggregate_key": "inventory_latest_flag_overlap", "commerce_observations": [
                    {"snapshot_date": "2022-12-31", "both_flagged_rows": 232},
                ]},
            ),
            Evidence(
                citation_id="C2", source_type="commerce_sql", source="Latest inventory by category",
                content=f"inventory_latest_by_category aggregate observations: {json.dumps(category_rows)}",
                metadata={"commerce_observation_group": "inventory_latest_by_category", "commerce_observations": category_rows},
            ),
            Evidence(citation_id="L1", source_type="commerce_schema", source="Schema limits",
                     content="SKU/location matches, lead time, and transfer costs are unavailable."),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "Which product categories should an operations manager review first for inventory reallocation using the latest available snapshot?",
            evidence,
            decision_request=True,
        )

        self.assertIn("Highest category flag counts (2022-12-31): stockout: Streetwear (134); overstock: Streetwear (162)", answer)
        self.assertIn("use these only to select categories for review", answer)
        self.assertIn("Do not rebalance inventory yet", answer)
        self.assertIn("[C2]", answer)
        self.assertIn("[L1]", answer)

        localized = _commerce_safe_fallback(
            "inventory_allocation",
            "Nên rà soát nhóm hàng nào trước khi điều chuyển tồn kho?",
            evidence,
            decision_request=True,
        )
        self.assertIn("Danh mục có số cờ cao nhất (2022-12-31): stockout: Streetwear (134); overstock: Streetwear (162)", localized)
        self.assertIn("chỉ dùng để chọn danh mục cần rà soát", localized)

    def test_depleted_huggingface_fallback_preserves_primary_rate_limit_for_safe_fallback(self):
        primary_error = RateLimitError(
            "rate limited", response=httpx.Response(429, request=httpx.Request("POST", "https://llm.test")), body={},
        )
        depleted_error = APIStatusError(
            "credits depleted",
            response=httpx.Response(402, request=httpx.Request("POST", "https://huggingface.test")),
            body={"error": "credits depleted"},
        )
        llm = Mock()
        llm.generate.side_effect = primary_error
        with patch.dict(os.environ, {
            "HUGGINGFACE_LLM_FALLBACK": "true", "HUGGINGFACE_API_KEY": "test-token",
        }), patch("core.llm.provider_fallback.HuggingFaceProvider") as fallback_factory:
            fallback_factory.return_value.generate.side_effect = depleted_error
            with self.assertRaises(RateLimitError) as raised:
                _generate_conditional_draft(llm, "evidence", "instructions")

        self.assertIs(raised.exception, primary_error)
        fallback_factory.return_value.close.assert_called_once()

    def test_commerce_query_generation_rate_limit_uses_bounded_snapshot(self):
        query_error = RateLimitError(
            "rate limited", response=httpx.Response(429, request=httpx.Request("POST", "https://llm.test")), body=None,
        )
        analytics = object.__new__(SQLAnalyticsAgent)
        analytics.commerce_question_observations = Mock(side_effect=query_error)
        analytics.commerce_decision_snapshot = Mock(return_value={
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {"inventory_latest_by_category": [
                {"category": "Shoes", "stockout_products": 42},
            ]},
            "limitations": [], "dataset_note": "Synthetic Commerce data.",
        })
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[])
        llm = Mock()
        report = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Which category has the most stockout flags, and what should we inspect before acting?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
        ))

        analytics.commerce_question_observations.assert_called_once()
        analytics.commerce_decision_snapshot.assert_called_once_with("inventory_allocation")
        self.assertEqual(report.metadata["question_sql_fallback"], "provider_rate_limited")
        self.assertEqual(report.metadata["answer_fallback_reason"], "provider_rate_limited")
        self.assertEqual(report.metadata["generation_provider"], "deterministic_safety_fallback")
        self.assertFalse(report.metadata["citation_validation_failed"])
        self.assertIn("42", report.answer)
        self.assertIn("[C1]", report.answer)
        llm.generate.assert_not_called()
        knowledge.run.assert_called_once()

    def test_inventory_method_fallback_explains_undefined_many_without_a_fake_gate(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Inventory flag overlap",
                content=("inventory_latest_flag_overlap aggregate observations: "
                         '[{"snapshot_date":"2022-12-31","product_rows":424,'
                         '"stockout_flagged_rows":285,"overstock_flagged_rows":341,'
                         '"both_flagged_rows":232}]'),
                metadata={"commerce_domain": "inventory_allocation",
                          "commerce_aggregate_key": "inventory_latest_flag_overlap",
                          "commerce_observations": [{
                              "snapshot_date": "2022-12-31", "product_rows": 424,
                              "stockout_flagged_rows": 285, "overstock_flagged_rows": 341,
                              "both_flagged_rows": 232,
                          }]},
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Commerce schema",
                content="Supplier lead time, SKU location, and approved service target are unavailable.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Synthetic Commerce Demo policy",
                content="Review categories with many stockout flags; verify item and location before replenishment.",
                metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True},
            ),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "Explain the steps to review stockout and overstock flags before replenishment.",
            evidence,
            decision_request=True,
        )

        self.assertIn("285 stockout-flagged rows", answer)
        self.assertIn("341 overstock-flagged rows", answer)
        self.assertIn("232 rows with both flags", answer)
        self.assertIn("without defining a threshold", answer)
        self.assertIn("not an automatic replenishment condition", answer)
        self.assertIn("[C1]", answer)
        self.assertIn("[S1]", answer)
        self.assertIn("[L1]", answer)

    def test_vietnamese_inventory_fallback_localizes_overlap_observation(self):
        question = "Trước khi chuyển hàng giữa các nhóm có stockout và overstock, cần kiểm tra dữ liệu nào?"
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Inventory flag overlap",
                content=("inventory_latest_flag_overlap aggregate observations: "
                         '[{"snapshot_date":"2022-12-31","product_rows":424,'
                         '"stockout_flagged_rows":232,"overstock_flagged_rows":232,'
                         '"both_flagged_rows":232}]'),
                metadata={"commerce_domain": "inventory_allocation",
                          "commerce_aggregate_key": "inventory_latest_flag_overlap",
                          "commerce_observations": [{
                              "snapshot_date": "2022-12-31", "product_rows": 424,
                              "stockout_flagged_rows": 232, "overstock_flagged_rows": 232,
                              "both_flagged_rows": 232,
                          }]},
            ),
            Evidence(citation_id="L1", source_type="commerce_schema", source="Schema limits",
                     content="SKU/location demand, lead time, transfer cost, and service constraints are absent."),
            Evidence(citation_id="S1", source_type="document", source="Commerce Demo inventory policy",
                     content="Match the same SKU at the source and destination before transferring stock.",
                     metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True}),
        ]

        answer = _commerce_safe_fallback("inventory_allocation", question, evidence, decision_request=True)

        self.assertFalse(_has_untranslated_prose(answer, question))
        self.assertIn("2022-12-31", answer)
        self.assertIn("232", answer)
        self.assertIn("[C1]", answer)

        dynamic_answer = _commerce_question_safe_fallback(
            "Explain the steps to review stockout and overstock flags before replenishment.",
            evidence,
            decision_request=True,
        )
        self.assertIn("without defining a threshold", dynamic_answer)
        self.assertIn("not an automatic replenishment condition", dynamic_answer)

    def test_provider_limited_inventory_fallback_discloses_unchecked_repeatability(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Annual inventory aggregate",
                content="inventory_by_year aggregate observations: [{\"year\":2022,\"stockout_snapshots\":3490}]",
                metadata={"commerce_observation_group": "inventory_by_year",
                          "commerce_observations": [{"year": 2022, "stockout_snapshots": 3490}]},
            ),
            Evidence(
                citation_id="C2", source_type="commerce_sql", source="Latest category aggregate",
                content="inventory_latest_by_category aggregate observations: [{\"category\":\"Shoes\",\"stockout_products\":42}]",
                metadata={"commerce_observation_group": "inventory_latest_by_category",
                          "commerce_observations": [{"category": "Shoes", "stockout_products": 42}]},
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Schema coverage",
                content="Warehouse location, demand forecast and transfer cost are unavailable.",
            ),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "Should inventory be reallocated toward products with repeated stockout signals?",
            evidence,
        )

        self.assertIn("do not count repeated stockout snapshots by product", answer)
        self.assertIn("persistently flagged products [C1][C2]", answer)
        self.assertIn("Do not rebalance inventory yet", answer)

    def test_inventory_transfer_fallback_does_not_treat_snapshot_counts_as_recurrence(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Latest inventory flags",
                content="Latest snapshot contains overlapping stockout and overstock rows.",
                metadata={
                    "commerce_aggregate_key": "inventory_latest_flag_overlap",
                    "commerce_observations": [{
                        "snapshot_date": "2022-12-31", "stockout_flagged_rows": 285,
                        "overstock_flagged_rows": 341, "both_flagged_rows": 232,
                    }],
                },
            ),
            Evidence(
                citation_id="C2", source_type="commerce_sql", source="Annual inventory aggregates",
                content="Annual inventory counts are product-date snapshots.",
                metadata={"commerce_aggregate_key": "inventory_by_year",
                          "commerce_observations": [{"year": 2022, "stockout_snapshots": 3490}]},
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Commerce schema",
                content="Source and destination warehouse stock, lead time, and transfer cost are unavailable.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Synthetic inventory policy",
                content="Check matched SKU and source/destination availability before a transfer.",
                metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True},
            ),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "Should we transfer inventory from overstocked categories to categories with repeated stockout snapshots? What should we check first?",
            evidence,
            decision_request=True,
        )

        self.assertIn("does not establish recurrence", answer)
        self.assertIn("count distinct snapshot dates per product", answer)
        self.assertIn("do not support a transfer decision", answer)
        self.assertIn("same SKU at source and destination", answer)
        self.assertIn("[C1]", answer)
        self.assertIn("[C2]", answer)
        self.assertIn("[S1]", answer)
        self.assertIn("[L1]", answer)

        vietnamese = _commerce_safe_fallback(
            "inventory_allocation",
            "Có nên điều chuyển từ danh mục tồn kho dư sang danh mục hết hàng lặp lại không? Cần kiểm tra gì trước?",
            evidence,
            decision_request=True,
        )
        self.assertIn("không chứng minh cờ lặp lại", vietnamese)
        self.assertIn("chưa đủ căn cứ điều chuyển", vietnamese)
        self.assertIn("[C2]", vietnamese)

    def test_commerce_query_connection_failure_uses_bounded_snapshot(self):
        connection_error = APIConnectionError(request=httpx.Request("POST", "https://llm.test"))
        repository = Mock()
        repository.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {"inventory_latest_by_category": [
                {"category": "Shoes", "stockout_products": 42},
            ]},
            "limitations": [], "dataset_note": "Synthetic Commerce data.",
        }
        llm = Mock()
        llm.generate.side_effect = [connection_error, "Shoes had 42 stockout flags [C1]."]
        knowledge = Mock()
        analytics = SQLAnalyticsAgent(repository=repository, llm=llm)

        with patch.dict(os.environ, {"HUGGINGFACE_LLM_FALLBACK": "false"}):
            result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
                question="Which inventory category has the most stockout flags?",
                metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
            ))

        self.assertEqual(result.metadata["question_sql_fallback"], "provider_unavailable")
        self.assertIn("42", result.answer)
        self.assertIn("[C1]", result.answer)

    def test_missing_commerce_dimension_keeps_supported_domain_snapshot_evidence(self):
        repository = Mock()
        repository.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {
                "inventory_latest_by_category": [{
                    "snapshot_date": "2022-12-31", "category": "Shoes",
                    "stockout_products": 42, "overstock_products": 31,
                }],
                "inventory_latest_flag_overlap": [{
                    "snapshot_date": "2022-12-31", "stockout_flagged_rows": 42,
                    "overstock_flagged_rows": 31, "both_flagged_rows": 8,
                }],
            },
            "limitations": [], "dataset_note": "Synthetic Commerce data.",
        }
        llm = Mock()
        llm.generate.return_value = (
            "Snapshot tổng hợp ghi nhận tín hiệu stockout và overstock ở danh mục Shoes [C1]. "
            "Chưa thể đánh giá theo vùng hoặc quyết định điều chuyển vì schema không có chiều kho/vị trí [L1]."
        )
        analytics = SQLAnalyticsAgent(repository=repository, llm=llm)
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[])

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Có đủ cơ sở để phân bổ lại hàng giữa các vùng nhằm giảm stockout?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
        ))

        repository.commerce_decision_snapshot.assert_called_once_with("inventory_allocation")
        repository.execute_commerce_analytics.assert_not_called()
        llm.generate.assert_called_once()
        self.assertEqual(result.metadata["question_sql_fallback"], "requested_dimension_unavailable")
        self.assertTrue(any(
            item.source_type == "commerce_schema"
            and "not available in the approved inventory_allocation schema" in item.content
            for item in result.evidence
        ))
        self.assertTrue(any(item.source_type == "commerce_sql" for item in result.evidence))
        self.assertIn("[L1]", result.answer)
        self.assertIn("[C1]", result.answer)

    def test_missing_commerce_dimension_uses_retrieved_policy_before_abstaining(self):
        repository = Mock()
        repository.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"], "observations": {},
            "limitations": [], "dataset_note": "Synthetic Commerce data.",
        }
        llm = Mock()
        llm.generate.return_value = (
            "Chưa đủ dữ liệu theo vùng để quyết định điều chuyển [L1]. "
            "Policy giả lập Commerce Demo yêu cầu đối chiếu SKU, tồn khả dụng và nhu cầu trước khi xem xét chuyển hàng [S1]."
        )
        analytics = SQLAnalyticsAgent(repository=repository, llm=llm)
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="Commerce Demo inventory policy",
            content="Chỉ xem xét điều chuyển khi có đối chiếu SKU giữa nơi gửi và nơi nhận, tồn khả dụng và nhu cầu.",
            metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True,
                      "reference_applicability": "Fictional Commerce Demo inventory scenario only."},
        )])

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Có đủ cơ sở để phân bổ lại hàng giữa các vùng nhằm giảm stockout?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
        ))

        self.assertEqual(result.metadata["question_sql_fallback"], "requested_dimension_unavailable")
        self.assertFalse(any(item.source_type == "commerce_sql" for item in result.evidence))
        self.assertTrue(any(item.source_type == "document" for item in result.evidence))
        self.assertIn("[L1]", result.answer)
        self.assertIn("[S1]", result.answer)
        llm.generate.assert_called_once()

    def test_schema_guard_rejects_claims_that_missing_dimensions_are_queryable(self):
        unsafe = (
            "Commerce Demo data can confirm that the same SKU exists at both locations [L1]. "
            "The schema has no forecast field, but units_sold and units_received can be used to approximate "
            "recent demand trends [L1]."
        )
        safe = (
            "Commerce Demo data cannot confirm a regional SKU match or demand forecast because region, location, "
            "and forecast fields are absent from the inventory schema [L1]."
        )
        safe_with_known_field = (
            "Commerce data can confirm stock on hand, but it has no location column [C1][L1]."
        )
        self.assertTrue(_claims_missing_commerce_dimension_is_available(unsafe, "inventory_allocation"))
        self.assertFalse(_claims_missing_commerce_dimension_is_available(safe, "inventory_allocation"))
        self.assertFalse(_claims_missing_commerce_dimension_is_available(safe_with_known_field, "inventory_allocation"))

    def test_missing_dimension_answer_is_repaired_without_substituting_a_proxy(self):
        repository = Mock()
        repository.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"], "observations": {},
            "limitations": [], "dataset_note": "Synthetic Commerce data.",
        }
        llm = Mock()
        llm.generate.side_effect = [
            "Commerce Demo data can confirm that the same SKU exists at both locations [L1]. "
            "The schema has no forecast field, but units_sold and units_received can be used to approximate "
            "recent demand trends [L1].",
            "Commerce Demo data cannot confirm a regional SKU match or demand forecast because region, location, "
            "and forecast fields are absent from the inventory schema [L1]. "
            "The fictional Commerce Demo inventory policy asks the team to match SKU, available stock, and demand "
            "before considering a transfer [S1]. Collect stock and demand by location, lead time, and transfer cost "
            "before deciding [L1].",
        ]
        analytics = SQLAnalyticsAgent(repository=repository, llm=llm)
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="Commerce Demo inventory policy",
            content="Before transfer, match the same SKU, available stock, and demand at source and destination.",
            metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True,
                      "reference_applicability": "Fictional Commerce Demo inventory scenario only."},
        )])

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Before rebalancing stock between regions, what evidence should the team check?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
        ))

        self.assertEqual(result.metadata["question_sql_fallback"], "requested_dimension_unavailable")
        self.assertTrue(result.metadata["decision_validation_repair_attempted"])
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertEqual(llm.generate.call_count, 2)
        self.assertNotIn("can confirm", result.answer)
        self.assertNotIn("approximate recent demand trends", result.answer)
        self.assertIn("[L1]", result.answer)
        self.assertIn("[S1]", result.answer)
        self.assertIn("unvalidated proxy", llm.generate.call_args_list[1].args[0])

    def test_rejected_commerce_query_repair_uses_bounded_snapshot(self):
        repository = Mock()
        repository.latest_commerce_inventory_snapshot.return_value = "2022-12-31"
        repository.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {"inventory_latest_by_category": [
                {"category": "Shoes", "stockout_products": 42},
            ]},
            "limitations": [], "dataset_note": "Synthetic Commerce data.",
        }
        repository.execute_commerce_analytics.side_effect = UnsafeAnalyticsQuery(
            "The Commerce SELECT could not be executed (UndefinedFunction, SQLSTATE 42883)"
        )
        llm = Mock()
        llm.generate.side_effect = [
            '{"sql":"SELECT i.category, COUNT(*) FROM commerce.inventory i '
            'WHERE i.snapshot_date = (SELECT MAX(snapshot_date) FROM commerce.inventory) '
            'GROUP BY i.category LIMIT 100"}',
            '{"sql":"SELECT i.category, SUM(i.stockout_flag) AS stockout_count '
            'FROM commerce.inventory i GROUP BY i.category LIMIT 100"}',
            "Shoes had 42 stockout flags [C1].",
        ]
        analytics = SQLAnalyticsAgent(repository=repository, llm=llm)

        result = ReportAgent(knowledge=Mock(), analytics=analytics, llm=llm).run(AgentRequest(
            question="Which inventory category has the most stockout flags?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
        ))

        self.assertEqual(result.metadata["question_sql_fallback"], "query_rejected")
        self.assertIn("42", result.answer)
        self.assertIn("[C1]", result.answer)
        repository.commerce_decision_snapshot.assert_called_once_with("inventory_allocation")

    def test_malformed_commerce_sql_falls_back_to_bounded_snapshot(self):
        repository = Mock()
        repository.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {"inventory_latest_by_category": [
                {"category": "Shoes", "stockout_products": 42},
            ]},
            "limitations": ["Category aggregates do not identify SKU/location transfer matches."],
            "dataset_note": "Synthetic Commerce data.",
        }
        llm = Mock()
        llm.generate.side_effect = [
            '{"sql":"SELECT product_i',
            '{"sql":"SELECT product_i',
            "The latest inventory aggregate contains 42 stockout-flagged products in Shoes [C1].",
        ]
        analytics = SQLAnalyticsAgent(repository=repository, llm=llm)

        result = ReportAgent(knowledge=Mock(), analytics=analytics, llm=llm).run(AgentRequest(
            question="Describe the latest inventory flag results.",
            metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
        ))

        self.assertEqual(result.metadata["question_sql_fallback"], "query_rejected")
        self.assertIn("42", result.answer)
        self.assertIn("[C1]", result.answer)
        repository.commerce_decision_snapshot.assert_called_once_with("inventory_allocation")
        repository.execute_commerce_analytics.assert_not_called()

    def test_dynamic_commerce_fallback_returns_query_rows_without_domain_template(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
            content='question_specific_query question-specific SQL observations: '
                    '[{"category": "Shoes", "units_sold": 42}]',
        )]

        answer = _commerce_question_safe_fallback(
            "How do the unbenchmarked category movement patterns compare?", evidence, decision_request=True,
        )

        self.assertIn("| Units Sold |", answer)
        self.assertIn("| Shoes | 42 |", answer)
        self.assertIn("[C1]", answer)
        self.assertIn("recommendation could not be synthesized", answer)
        self.assertNotIn("transfer inventory", answer.casefold())
        self.assertNotIn("holdout experiment", answer.casefold())

    def test_dynamic_fallback_row_omission_note_does_not_add_an_uncited_number(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
            content="question-specific SQL observations: " + json.dumps([{"campaign": "Spring Sale"}] * 50),
            metadata={"commerce_domain": "promotion_planning"},
        )]

        answer = _commerce_question_safe_fallback(
            "Should we expand a campaign based on order outcomes?", evidence, decision_request=True,
        )

        self.assertIn("(Additional rows omitted.)", answer)
        self.assertNotIn("30", answer)
        self.assertTrue(_decision_numeric_facts_match_cited_evidence(answer, evidence))

    def test_promotion_incrementality_fallback_suppresses_irrelevant_campaign_baselines(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Campaign outcomes",
                content=("question-specific SQL observations: " + json.dumps([
                    {"campaign": "Spring Sale", "orders_before": 0, "net_sales_before": None,
                     "delivered_orders": 115, "net_item_sales": 728500.0},
                ])),
                metadata={"commerce_domain": "promotion_planning"},
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Promotion data coverage",
                content="The dataset has no randomized holdout or customer-level counterfactual.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Synthetic promotion policy",
                content="Expand the campaign when sales are high.",
                metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True},
            ),
            Evidence(
                citation_id="S2", source_type="document", source="Campaign measurement guide",
                content="Use a treatment/control or holdout experiment to estimate incremental sales.",
                metadata={"evidence_class": "management_cookbook_reference",
                          "source_publisher": "Measurement Guide"},
            ),
        ]

        answer = _commerce_question_safe_fallback(
            "How can we test whether a campaign caused incremental sales before scaling it?",
            evidence,
            decision_request=True,
        )

        self.assertNotIn("Spring Sale", answer)
        self.assertNotIn("orders_before", answer)
        self.assertNotIn("115", answer)
        self.assertIn("does not establish", answer)
        self.assertIn("holdout", answer)
        self.assertIn("[L1]", answer)
        self.assertIn("[S2]", answer)
        self.assertNotIn("[S1]", answer)

    def test_promotion_incrementality_comparison_keeps_explicitly_requested_sql_measures(self):
        question = (
            "Should we expand discounts based on observed sales, or wait for an incrementality test? "
            "Compare the available sales outcome and profit proxy."
        )
        rows = [
            {"year": 2022, "used_promotion": True, "net_sales": 245344841.2,
             "merchandise_gross_profit_proxy": -33563798.173748},
            {"year": 2022, "used_promotion": False, "net_sales": 615242495.15,
             "merchandise_gross_profit_proxy": 107063950.746632},
        ]
        evidence = [
            Evidence(citation_id="C1", source_type="commerce_sql", source="Promotion outcomes",
                     content="promotions_by_year aggregate observations: " + json.dumps(rows),
                     metadata={"commerce_domain": "promotion_planning", "commerce_observations": rows,
                               "commerce_observation_group": "promotions_by_year"}),
            Evidence(citation_id="L1", source_type="commerce_schema", source="Promotion limitations",
                     content="Promotion-tagged and untagged results are descriptive, not causal."),
            Evidence(citation_id="S1", source_type="document", source="Measurement guide",
                     content="A holdout experiment estimates incremental sales.",
                     metadata={"evidence_class": "management_cookbook_reference",
                               "source_publisher": "Measurement Guide"}),
        ]

        answer = _commerce_question_safe_fallback(question, evidence, decision_request=True)

        self.assertIn("merchandise gross profit proxy", answer.casefold())
        self.assertIn("-33,563,798.17", answer)
        self.assertIn("107,063,950.75", answer)
        self.assertIn("not causal", answer.casefold())
        self.assertNotIn("SQL tagged-versus-untagged", answer)
        self.assertIsNone(_commerce_requested_observation_missing(answer, evidence, question))

    def test_commerce_fallback_rounds_average_columns_but_preserves_other_sql_precision(self):
        rows = [{"avg_transit_days": 4.498636825538454, "net_sales": 245344841.2}]
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Logistics summary",
            content="question-specific SQL observations: " + json.dumps(rows),
            metadata={"commerce_domain": "nationwide_logistics"},
        )]

        answer = _commerce_question_safe_fallback("Compare transit and sales", evidence, decision_request=False)

        self.assertIn("4.5", answer)
        self.assertNotIn("4.498636825538454", answer)
        self.assertIn("245,344,841.2", answer)

    def test_commerce_number_format_uses_locale_grouping_without_claiming_currency(self):
        self.assertEqual(_format_commerce_number(570817418.55, "net_sales", True), "570.817.418,55")
        self.assertEqual(_format_commerce_number(570817418.55, "net_sales", False), "570,817,418.55")
        self.assertEqual(_format_commerce_number(0.204015, "merchandise_gross_margin_proxy", True), "20,4%")
        self.assertEqual(_format_commerce_number(2022, "year", False), "2022")

    def test_dynamic_commerce_fallback_filters_to_explicit_years(self):
        rows = [
            {"year": 2020, "used_promotion": False, "net_sales": 570817418.55},
            {"year": 2020, "used_promotion": True, "net_sales": 235597280.59},
            {"year": 2021, "used_promotion": False, "net_sales": 493703251.83},
        ]
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Promotion summary",
            content="question-specific SQL observations: " + json.dumps(rows),
            metadata={"commerce_domain": "promotion_planning"},
        )]

        answer = _commerce_question_safe_fallback(
            "So sánh doanh thu thuần giữa nhóm gắn khuyến mãi và không gắn khuyến mãi năm 2020.",
            evidence,
            decision_request=False,
        )

        self.assertIn("570.817.418,55", answer)
        self.assertIn("235.597.280,59", answer)
        self.assertNotIn("493.703.251,83", answer)
        self.assertNotIn("2021", answer)

    def test_dynamic_commerce_fallback_uses_relevant_snapshot_group_and_abstains_for_missing_year(self):
        annual_rows = [
            {"year": 2020, "used_promotion": True, "net_sales": 235597280.59,
             "merchandise_gross_profit_proxy": -21191181.87},
            {"year": 2022, "used_promotion": True, "net_sales": 245344841.2,
             "merchandise_gross_profit_proxy": -33563798.17},
        ]
        campaign_rows = [
            {"year": 2020, "campaign": "Spring Sale 2020", "net_item_sales": 90175249.9,
             "merchandise_gross_profit_proxy": -2095831.50},
            {"year": 2022, "campaign": "Spring Sale 2022", "net_item_sales": 90345105.91,
             "merchandise_gross_profit_proxy": -6503552.08},
        ]
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Annual promotion observations",
                content="promotions_by_year aggregate observations: " + json.dumps(annual_rows),
                metadata={"commerce_domain": "promotion_planning", "commerce_observation_group": "promotions_by_year",
                          "commerce_observations": annual_rows},
            ),
            Evidence(
                citation_id="C2", source_type="commerce_sql", source="Campaign observations",
                content="promotions_by_campaign aggregate observations: " + json.dumps(campaign_rows),
                metadata={"commerce_domain": "promotion_planning", "commerce_observation_group": "promotions_by_campaign",
                          "commerce_observations": campaign_rows},
            ),
            Evidence(citation_id="L1", source_type="commerce_schema", source="Promotion schema limits",
                     content="Campaign spend and randomized holdout data are absent; observed promotion comparisons are not causal."),
            Evidence(citation_id="S1", source_type="document", source="IAB measurement guide",
                     content="Use a holdout or counterfactual to estimate incremental campaign outcomes.",
                     metadata={"evidence_class": "management_cookbook_reference", "source_publisher": "IAB"}),
        ]
        question = (
            "For 2024 campaigns, compare net item sales and the merchandise gross-profit proxy by campaign. "
            "Does that evidence justify increasing campaign budgets?"
        )

        answer = _commerce_question_safe_fallback(question, evidence, decision_request=True)

        self.assertIn("no sql observations matched", answer.casefold())
        self.assertIn("2020", answer)
        self.assertIn("2022", answer)
        self.assertNotIn("2024", answer)
        self.assertIn("[C2]", answer)
        self.assertIn("[S1]", answer)
        self.assertIsNone(_commerce_requested_observation_missing(answer, evidence, question))
        self.assertIsNone(_report_validation_failure(answer, evidence, {"C1", "C2", "L1", "S1"}, question))

    def test_dynamic_sql_fallback_limits_metrics_to_the_measures_in_the_question(self):
        rows = [{
            "year": 2022, "used_promotion": True, "delivered_orders": 10173,
            "units": 48768, "net_sales": 245344841.2, "discounts": 41728464.79,
            "catalog_cogs": 278908639.37,
            "merchandise_gross_profit_proxy": -33563798.17,
            "merchandise_gross_margin_proxy": -0.1368,
        }]
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Promotion summary",
            content="question-specific SQL observations: " + json.dumps(rows),
            metadata={"commerce_domain": "promotion_planning", "commerce_observations": rows},
        )]

        answer = _commerce_question_safe_fallback(
            "So sánh số đơn đã giao, số lượng, doanh thu thuần và giảm giá theo năm.",
            evidence,
            decision_request=False,
        )

        for expected in ("Năm", "Đơn có gắn khuyến mãi", "Đơn đã giao", "Số lượng", "Doanh thu thuần", "Giảm giá"):
            self.assertIn(expected, answer)
        self.assertNotIn("Giá vốn theo catalog", answer)
        self.assertNotIn("Lợi nhuận gộp hàng hóa", answer)
        self.assertNotIn("Biên lợi nhuận gộp hàng hóa", answer)

    def test_commerce_fallback_formats_fill_rate_as_percentage_and_keeps_it_grounded(self):
        rows = [
            {"year": 2020, "avg_fill_rate": 0.9656, "stockout_snapshots": 3795, "total_snapshots": 5686},
            {"year": 2021, "avg_fill_rate": 0.9619, "stockout_snapshots": 3788, "total_snapshots": 5609},
        ]
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Inventory annual summary",
            content="question-specific SQL observations: " + json.dumps(rows),
            metadata={"commerce_domain": "inventory_allocation", "commerce_observations": rows},
        )]

        for question, fragments in (
            ("So sánh tỷ lệ đáp ứng trung bình theo năm và có nên đặt mục tiêu mới không?",
             ("Tỷ lệ đáp ứng TB", "96,56%")),
            ("Compare annual average fill rate and should we set a new target?",
             ("Avg Fill Rate", "96.56%")),
        ):
            with self.subTest(question=question):
                answer = _commerce_question_safe_fallback(question, evidence, decision_request=False)
                for fragment in fragments:
                    self.assertIn(fragment, answer)
                self.assertNotIn("0.9656", answer)
                self.assertTrue(_decision_numeric_facts_match_cited_evidence(answer, evidence))
                self.assertIsNone(_commerce_requested_observation_missing(
                    answer, evidence, question,
                ))

    def test_inventory_snapshot_fallback_formats_fill_rate_as_percentage(self):
        rows = [
            {"year": 2020, "avg_fill_rate": 0.9656, "stockout_snapshots": 3795, "sku_snapshots": 5686},
            {"year": 2021, "avg_fill_rate": 0.9619, "stockout_snapshots": 3788, "sku_snapshots": 5609},
            {"year": 2022, "avg_fill_rate": 0.9635, "stockout_snapshots": 3490, "sku_snapshots": 5232},
        ]
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Inventory annual summary",
            content="inventory_by_year aggregate observations: " + json.dumps(rows),
            metadata={"commerce_domain": "inventory_allocation", "commerce_observations": rows},
        )]

        for question, expected in (
            ("Trong từng năm 2020–2022, fill rate thay đổi thế nào?", "Fill rate TB=96,56%"),
            ("How did average fill rate change from 2020–2022?", "Avg fill rate=96.56%"),
        ):
            with self.subTest(question=question):
                answer = _commerce_safe_fallback(
                    "inventory_allocation", question, evidence, decision_request=False,
                )
                self.assertIn(expected, answer)
                self.assertNotIn("0.9656", answer)
                self.assertIn("3795", answer)
                self.assertIn("5686", answer)

    def test_logistics_decision_fallback_validation_accepts_rounded_sql_averages(self):
        query_error = RateLimitError(
            "rate limited", response=httpx.Response(429, request=httpx.Request("POST", "https://llm.test")), body=None,
        )
        analytics = object.__new__(SQLAnalyticsAgent)
        analytics.commerce_question_observations = Mock(return_value={
            "domain": "nationwide_logistics",
            "domain_label": "Nationwide logistics",
            "source_tables": ["commerce.shipments", "commerce.geography"],
            "sql_query": "SELECT region, avg_transit_time_days, avg_shipping_fee FROM commerce.shipments",
            "observations": [{
                "year": 2024,
                "region": "North",
                "avg_transit_time_days": "4.5066761363636364",
                "avg_shipping_fee": "4.244421",
            }],
            "limitations": ["Route, carrier, and promised-SLA dimensions are unavailable."],
            "dataset_note": "Synthetic Commerce competition data.",
        })
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[])
        llm = Mock()
        llm.generate.side_effect = query_error
        question = "Should we redesign the nationwide delivery network based on regional transit time and shipping fee?"

        with patch.dict(os.environ, {"HUGGINGFACE_LLM_FALLBACK": "false"}):
            result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
                question=question,
                metadata={"business_decision_domain": "nationwide_logistics", "role": "analyst"},
            ))

        self.assertIn("4.51", result.answer)
        self.assertIn("4.24", result.answer)
        self.assertTrue(result.metadata["decision_fallback_used"])
        self.assertEqual(result.metadata["generation_provider"], "deterministic_safety_fallback")
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertIn("[C1]", result.answer)

    def test_commerce_fallback_rounds_serialized_decimal_average_columns(self):
        rows = [{
            "avg_stock_on_hand": "7.6333333333333333",
            "avg_units_sold": "3.3333333333333333",
            "total_products": 232,
        }]
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Inventory summary",
            content="question-specific SQL observations: " + json.dumps(rows),
            metadata={"commerce_domain": "inventory_allocation"},
        )]

        answer = _commerce_question_safe_fallback(
            "Tóm tắt lượng tồn và số bán trung bình", evidence, decision_request=False,
        )

        self.assertIn("7,63", answer)
        self.assertIn("3,33", answer)
        self.assertNotIn("7.6333333333333333", answer)
        self.assertNotIn("3.3333333333333333", answer)
        self.assertIn("232", answer)

    def test_dynamic_commerce_fallback_cites_retrieved_synthetic_policy(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
                content='question-specific SQL observations: [{"category": "Streetwear", "stockouts": 134}]',
                metadata={"commerce_domain": "inventory_allocation"},
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Commerce Demo policy",
                content=(
                    "Chính sách hướng dẫn rà soát tổng thể trước khi ra quyết định. "
                    "Chỉ xem xét điều chuyển khi có đối chiếu SKU giữa nơi gửi và nơi nhận, tồn khả dụng, "
                    "nhu cầu dự báo, thời gian bổ sung, chi phí vận chuyển và ràng buộc dịch vụ. "
                    "Chỉ đề xuất thay đổi đặt hàng khi có lịch sử nhu cầu và lead time."
                ),
                metadata={
                    "evidence_class": "company_policy_reference",
                    "synthetic_company_policy": True,
                    "source_publisher": "Commerce Demo (fictional)",
                    "ocr": {"engine": "tesseract", "language": "vie+eng"},
                    "text_extraction_method": "tesseract",
                },
            ),
        ]

        answer = _commerce_question_safe_fallback(
            "Trước khi điều chuyển, cần đối chiếu SKU, tồn khả dụng, nhu cầu dự báo hay chi phí vận chuyển?",
            evidence,
            decision_request=True,
        )

        self.assertIn("[C1]", answer)
        self.assertIn("[S1]", answer)
        self.assertIn("văn bản OCR chưa được xác minh", answer)
        self.assertIn("Kiểm tra PDF gốc trước khi áp dụng", answer)
        self.assertNotIn("đối chiếu SKU giữa nơi gửi và nơi nhận", answer)
        self.assertNotIn("Chính sách hướng dẫn rà soát tổng thể", answer)
        self.assertIn("không phải chính sách của doanh nghiệp thật", answer)

    def test_dynamic_commerce_fallback_keeps_ocr_context_for_cross_language_question(self):
        repeated_context = "Nguyên tắc chung là kiểm tra snapshot được chọn trước khi đề xuất phương án. " * 10
        action_rule = (
            "Chỉ xem xét điều chuyển khi có đối chiếu SKU giữa nơi gửi và nơi nhận, tồn khả dụng, "
            "nhu cầu dự báo, thời gian bổ sung và chi phí vận chuyển."
        )
        evidence = [Evidence(
            citation_id="S1", source_type="document", source="Commerce Demo inventory policy",
            content=repeated_context + action_rule,
            metadata={
                "evidence_class": "company_policy_reference",
                "synthetic_company_policy": True,
                "ocr": {"engine": "tesseract"},
                "text_extraction_method": "tesseract",
            },
        )]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "What should be checked before transferring inventory?",
            evidence,
            decision_request=True,
        )

        self.assertIn("OCR text is not verified", answer)
        self.assertIn("Check the source PDF before relying on it", answer)
        self.assertNotIn(action_rule, answer)

    def test_synthetic_policy_fallback_uses_curated_source_note_not_ocr_text(self):
        ocr_text = "Chỉ xem xét điều chuyến khi có dũ liêu phù hợp."
        source_note = (
            "Quy tắc giả lập chỉ áp dụng trong demo: cần ghép nhu cầu, tồn khả dụng, "
            "lead time và chi phí trước khi điều chuyển."
        )
        evidence = [Evidence(
            citation_id="S1", source_type="document", source="Commerce Demo inventory policy",
            content=ocr_text,
            metadata={
                "evidence_class": "company_policy_reference",
                "synthetic_company_policy": True,
                "ocr": {"engine": "tesseract"},
                "text_extraction_method": "tesseract",
                "source_notes": source_note,
            },
        )]

        answer = _commerce_safe_fallback(
            "inventory_allocation", "Có nên điều chuyển hàng tồn kho không?", evidence,
            decision_request=True,
        )

        self.assertIn(source_note, answer)
        self.assertIn("Tóm tắt biên mục (không phải trích nguyên văn)", answer)
        self.assertIn("đối chiếu trang PDF gốc", answer)
        self.assertIn("[S1]", answer)
        self.assertNotIn(ocr_text, answer)

    def test_inventory_service_target_fallback_omits_unrelated_ocr_policy_notes(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Inventory annual summary",
                content="inventory_by_year aggregate observations: " + json.dumps([
                    {"year": 2022, "avg_fill_rate": 0.9635},
                ]),
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Inventory schema",
                content="The supplied data has no approved service-level target.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Commerce Demo inventory policy",
                content="OCR policy text", metadata={
                    "evidence_class": "company_policy_reference",
                    "synthetic_company_policy": True,
                    "ocr": {"engine": "tesseract"},
                    "source_notes": (
                        "Trong demo, hai cờ có thể chồng lấp. "
                        "Không tự đặt service-level target hoặc ngưỡng. "
                        "Chỉ cân nhắc điều chuyển sau khi ghép nhu cầu, tồn kho và chi phí."
                    ),
                },
            ),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "Có thể đặt service target mới từ fill rate lịch sử không?",
            evidence,
            decision_request=True,
        )

        self.assertIn("Dữ liệu không có service-level target đã được phê duyệt", answer)
        self.assertIn("Kiểm tra PDF gốc trước khi áp dụng", answer)
        self.assertNotIn("điều chuyển", answer)
        self.assertNotIn("service-level target hoặc ngưỡng", answer)

    def test_dynamic_inventory_fallback_ranks_each_returned_flag_for_unseen_imbalance_question(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
            content=("question-specific SQL observations: " + json.dumps([
                {"category": "Streetwear", "stockout_count": 134, "overstock_count": 162},
                {"category": "Outdoor", "stockout_count": 95, "overstock_count": 113},
            ])),
            metadata={"commerce_domain": "inventory_allocation"},
        )]

        answer = _commerce_question_safe_fallback(
            "Which product categories should we inspect first for inventory imbalance?",
            evidence,
            decision_request=True,
        )

        self.assertIn("stockout: Streetwear (134)", answer)
        self.assertIn("overstock: Streetwear (162)", answer)
        self.assertIn("aggregate review order only", answer)
        self.assertIn("[C1]", answer)

    def test_unseen_replenishment_question_does_not_receive_transfer_only_advice(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
                content=("question-specific SQL observations: " + json.dumps([
                    {"category": "Streetwear", "stockout_count": 134, "overstock_count": 162},
                ])),
                metadata={"commerce_domain": "inventory_allocation"},
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Commerce schema",
                content="SKU-level demand, available stock, lead time, order constraints, and approved service target are unavailable.",
            ),
        ]

        answer = _commerce_question_safe_fallback(
            "Which inventory categories should be investigated first before changing replenishment, and what evidence should we check?",
            evidence,
            decision_request=True,
        )

        self.assertIn("Streetwear", answer)
        self.assertIn("Before adjusting replenishment", answer)
        self.assertIn("SKU-level demand", answer)
        self.assertIn("approved service target", answer)
        self.assertNotIn("Do not rebalance inventory yet", answer)
        self.assertNotIn("before considering a transfer", answer)

    def test_dynamic_promotion_fallback_honors_router_decision_metadata(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
                content=('question-specific SQL observations: '
                         '[{"year": 2022, "campaign_tagged_net_sales": 570817418.55}]'),
                metadata={"commerce_domain": "promotion_planning"},
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Commerce schema",
                content="Campaign cost, control-group outcomes, and incremental margin are unavailable.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Campaign measurement cookbook",
                content="Use a holdout group to estimate incremental sales before changing campaign investment.",
                metadata={
                    "evidence_class": "management_cookbook_reference",
                    "source_publisher": "Demo cookbook",
                },
            ),
        ]

        answer = _commerce_question_safe_fallback(
            "Summarize the campaign signals for the planning review.",
            evidence,
            decision_request=True,
        )

        self.assertIn("Do not expand a campaign", answer)
        self.assertIn("[L1]", answer)
        self.assertIn("[S1]", answer)

    def test_dynamic_decision_fallback_keeps_sql_rows_and_gives_a_conditional_safe_action(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
                content=("question_specific_query question-specific SQL observations: "
                         '[{"category":"Streetwear","stockout_count":134},'
                         '{"category":"Outdoor","stockout_count":95}]'),
                metadata={"commerce_domain": "inventory_allocation"},
            ),
            Evidence(
                citation_id="C2", source_type="commerce_sql", source="Commerce inventory overlap aggregate",
                content=('inventory_latest_flag_overlap aggregate observations: '
                         '[{"snapshot_date":"2022-12-31","both_flagged_rows":232}]'),
                metadata={"commerce_domain": "inventory_allocation",
                          "commerce_aggregate_key": "inventory_latest_flag_overlap"},
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Commerce schema",
                content="Category data has no SKU/location match, lead time, or transfer cost.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Commerce Demo policy",
                content="Only consider transfers after matching SKU, available stock, demand, lead time and costs.",
                metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True},
            ),
        ]

        answer = _commerce_question_safe_fallback(
            "Trong snapshot tồn kho mới nhất, có nên chuyển hàng để giảm stockout?",
            evidence, decision_request=True,
        )

        self.assertIn("| Cờ stockout |", answer)
        self.assertIn("| Streetwear | 134 |", answer)
        self.assertIn("232 dòng", answer)
        self.assertIn("[C2]", answer)
        self.assertIn("Chưa điều chuyển tồn kho", answer)
        self.assertIn("[C1]", answer)
        self.assertIn("[L1]", answer)
        self.assertIn("[S1]", answer)
        self.assertNotIn("fallback chưa tổng hợp", answer)
        self.assertIn("Policy giả lập Commerce Demo đã được truy xuất", answer)
        self.assertIn("không phải chính sách của doanh nghiệp thật", answer)

    def test_dynamic_inventory_fallback_ranks_requested_stockout_category(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
            content=("question_specific_query question-specific SQL observations: "
                     '[{"category":"GenZ","stockout_count":25,"avg_stockout_days":0.84},'
                     '{"category":"Streetwear","stockout_count":134,"avg_stockout_days":1.13},'
                     '{"category":"Outdoor","stockout_count":95,"avg_stockout_days":1.29}]'),
            metadata={"commerce_domain": "inventory_allocation"},
        )]

        answer = _commerce_question_safe_fallback(
            "Nên ưu tiên kiểm tra danh mục nào để giảm tình trạng thiếu hàng?",
            evidence,
            decision_request=True,
        )

        self.assertIn("Ưu tiên rà soát theo từng cờ", answer)
        self.assertIn("stockout: Streetwear (134)", answer)
        self.assertIn("chỉ là thứ tự rà soát theo aggregate", answer)
        self.assertIn("[C1]", answer)
        self.assertNotIn("[[C1]]", answer)

    def test_dynamic_inventory_fallback_ranks_group_label_from_live_query_rows(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
            content=("question_specific_query question-specific SQL observations: "
                     '[{"group_label":"GenZ","overstock_count":37,"stockout_count":25},'
                     '{"group_label":"Casual","overstock_count":29,"stockout_count":31},'
                     '{"group_label":"Streetwear","overstock_count":162,"stockout_count":134},'
                     '{"group_label":"Outdoor","overstock_count":113,"stockout_count":95}]'),
            metadata={"commerce_domain": "inventory_allocation"},
        )]

        answer = _commerce_question_safe_fallback(
            "Nhóm hàng nào có nhiều sản phẩm bị gắn cờ stockout nhất?",
            evidence,
            decision_request=True,
        )

        self.assertIn("| Nhóm hàng |", answer)
        self.assertIn("stockout: Streetwear (134)", answer)
        self.assertIn("thứ tự rà soát theo aggregate [C1]", answer)

    def test_dynamic_inventory_fallback_localizes_group_category_from_live_sql_rows(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
            content=("question_specific_query question-specific SQL observations: "
                     '[{"group_category":"Outdoor","overstock_count":113,"stockout_count":95},'
                     '{"group_category":"Streetwear","overstock_count":162,"stockout_count":134}]'),
            metadata={"commerce_domain": "inventory_allocation"},
        )]

        answer = _commerce_question_safe_fallback(
            "Nhóm hàng nào có nhiều sản phẩm bị gắn cờ stockout nhất?",
            evidence,
            decision_request=True,
        )

        self.assertIn("| Nhóm hàng |", answer)
        self.assertNotIn("Group Category", answer)
        self.assertIn("stockout: Streetwear (134)", answer)
        self.assertIn("thứ tự rà soát theo aggregate [C1]", answer)

    def test_report_agent_dynamic_inventory_sql_rate_limit_uses_group_label_fallback(self):
        question = (
            "Trong snapshot tồn kho mới nhất, nhóm hàng nào có nhiều sản phẩm bị gắn cờ stockout nhất? "
            "Có nên chuyển hàng từ nhóm overstock sang không?"
        )
        analytics = SQLAnalyticsAgent(repository=Mock(), llm=Mock())
        analytics.commerce_question_observations = Mock(return_value={
            "domain": "inventory_allocation",
            "source_tables": ["commerce.inventory"],
            "sql_query": "SELECT group_label, stockout_count, overstock_count FROM commerce.inventory",
            "observations": [
                {"group_label": "GenZ", "overstock_count": 37, "stockout_count": 25},
                {"group_label": "Casual", "overstock_count": 29, "stockout_count": 31},
                {"group_label": "Streetwear", "overstock_count": 162, "stockout_count": 134},
                {"group_label": "Outdoor", "overstock_count": 113, "stockout_count": 95},
            ],
            "limitations": ["Category aggregates do not match SKU, location, demand or transfer cost."],
            "dataset_note": "Synthetic Commerce data.",
        })
        analytics.commerce_latest_inventory_flag_overlap = Mock(return_value=[{
            "snapshot_date": "2022-12-31", "both_flagged_rows": 232,
        }])
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="Commerce Demo inventory policy",
            content="Match SKU demand and available stock by location before transferring inventory.",
            metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True},
        )])
        llm = Mock()
        llm.generate.side_effect = RateLimitError(
            "rate limited",
            response=httpx.Response(429, request=httpx.Request("POST", "https://llm.test")),
            body=None,
        )

        with patch.dict(os.environ, {"HUGGINGFACE_LLM_FALLBACK": "false"}):
            result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
                question=question,
                metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
            ))

        analytics.commerce_question_observations.assert_called_once_with(question, "inventory_allocation")
        analytics.commerce_latest_inventory_flag_overlap.assert_called_once_with()
        self.assertIn("Streetwear (134)", result.answer)
        self.assertIn("Nhóm hàng", result.answer)
        self.assertIn("[C1]", result.answer)
        self.assertIn("[C2]", result.answer)
        self.assertIn("[S1]", result.answer)
        self.assertFalse(_suggests_unsupported_inventory_transfer(result.answer))
        self.assertEqual(result.metadata["generation_provider"], "deterministic_safety_fallback")
        self.assertEqual(result.metadata["answer_fallback_reason"], "provider_rate_limited")

    def test_report_agent_uses_question_specific_commerce_sql_for_unseen_aggregate(self):
        analytics = SQLAnalyticsAgent(repository=Mock(), llm=Mock())
        analytics.commerce_question_observations = Mock(return_value={
            "domain": "inventory_allocation",
            "source_tables": ["commerce.inventory"],
            "sql_query": (
                "SELECT i.category, SUM(i.units_received) AS units_received "
                "FROM commerce.inventory i WHERE i.year = 2022 GROUP BY i.category LIMIT 10"
            ),
            "sql_generation_usage": {"input_tokens": 80, "output_tokens": 14, "total_tokens": 94},
            "observations": [{"snapshot_date": date(2022, 12, 31), "category": "Streetwear", "units_received": 35844}],
            "limitations": ["Category receipts do not establish a stock transfer opportunity."],
            "dataset_note": "Synthetic Commerce data.",
        })
        knowledge, llm = Mock(), Mock(last_usage={
            "input_tokens": 120, "output_tokens": 26, "total_tokens": 146,
        })
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[])
        llm.generate.return_value = (
            "Streetwear has the highest received-unit total in this requested category comparison [C1]. "
            "This receipt volume alone does not establish a transfer or replenishment decision [L1]."
        )

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Which categories received the most stock during 2022?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
        ))

        analytics.commerce_question_observations.assert_called_once_with(
            "Which categories received the most stock during 2022?", "inventory_allocation",
        )
        self.assertIn("35844", result.evidence[0].content)
        self.assertIn("2022-12-31", result.evidence[0].content)
        self.assertIn("sql_query", result.evidence[0].metadata)
        self.assertEqual(result.evidence[0].metadata["commerce_observations"], [
            {"snapshot_date": date(2022, 12, 31), "category": "Streetwear", "units_received": 35844},
        ])
        self.assertIn("[C1]", result.answer)
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertEqual(result.metadata["token_usage"]["total"], {
            "input_tokens": 200, "output_tokens": 40, "total_tokens": 240,
        })

    def test_question_specific_inventory_answer_includes_vetted_flag_overlap_aggregate(self):
        analytics = SQLAnalyticsAgent(repository=Mock(), llm=Mock())
        analytics.commerce_question_observations = Mock(return_value={
            "domain": "inventory_allocation",
            "source_tables": ["commerce.inventory"],
            "sql_query": "SELECT category, COUNT(*) FILTER (WHERE stockout_flag) AS stockout_products FROM commerce.inventory GROUP BY category",
            "observations": [{"category": "Streetwear", "stockout_products": 134}],
            "limitations": ["Category counts do not identify SKU and location matches or transfer costs."],
            "dataset_note": "Synthetic Commerce data.",
        })
        analytics.commerce_latest_inventory_flag_overlap = Mock(return_value=[{
            "snapshot_date": "2022-12-31", "both_flagged_rows": 232,
        }])
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[])
        llm = Mock()
        llm.generate.return_value = (
            "Trong snapshot 2022-12-31, Streetwear có nhiều cờ stockout nhất: 134 [C1]. "
            "Có 232 dòng đồng thời mang hai cờ stockout và overstock [C2]. "
            "Chưa điều chuyển vì số tổng hợp theo danh mục không ghép SKU, địa điểm và chi phí [L1]."
        )

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question=("Trong snapshot tồn kho mới nhất, nhóm hàng nào có nhiều sản phẩm bị gắn cờ stockout nhất? "
                      "Có nên chuyển hàng từ nhóm overstock sang không?"),
            metadata={"business_decision_domain": "inventory_allocation", "role": "operations"},
        ))

        analytics.commerce_latest_inventory_flag_overlap.assert_called_once_with()
        overlap = next(item for item in result.evidence if item.citation_id == "C2")
        self.assertEqual(overlap.metadata["commerce_aggregate_key"], "inventory_latest_flag_overlap")
        self.assertNotIn("sql_query", overlap.metadata)
        self.assertIn('"both_flagged_rows": 232', overlap.content)
        self.assertIn("232 dòng", result.answer)
        self.assertFalse(result.metadata["citation_validation_failed"])

    def test_commerce_answer_language_check_ignores_quoted_source_but_rejects_english_narration(self):
        vietnamese_question = "Trong snapshot mới nhất, nhóm hàng nào có nhiều stockout nhất?"

        self.assertTrue(_has_untranslated_prose(
            "Campaign-window outcomes ranked by campaign sales [C1].", vietnamese_question,
        ))
        self.assertFalse(_has_untranslated_prose(
            "Tài liệu ghi: “Advertisers need an accurate way to evaluate the impact.” [S1] "
            "Dữ liệu này chưa đủ để quyết định.",
            vietnamese_question,
        ))
        self.assertFalse(_has_untranslated_prose(
            "Campaign-window outcomes ranked by campaign sales [C1].",
            "Which campaign had the highest sales?",
        ))

    def test_commerce_answer_language_check_treats_dynamic_sql_table_as_structured_data(self):
        question = "Có nên mở rộng khuyến mãi dựa trên doanh số ghi nhận?"
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Promotion outcomes",
            content="question-specific SQL observations: " + json.dumps([{
                "applicable_category": None, "avg_discount_per_item": 2.2,
                "gross_sales": 129.0, "net_sales": 125.0, "order_item_count": 160,
                "promo_channel": "online", "promo_id": "PROMO-0001",
                "promo_name": "Spring Sale 2013", "total_discount": 4.0,
            }]),
            metadata={"commerce_domain": "promotion_planning"},
        )]

        answer = _commerce_question_safe_fallback(question, evidence, decision_request=True)

        self.assertIn("| Danh mục áp dụng |", answer)
        self.assertIn("Kênh khuyến mãi", answer)
        self.assertIn("Tên chiến dịch", answer)
        self.assertNotIn("Applicable Category", answer)
        self.assertIn("Quan sát SQL", answer)
        self.assertFalse(_has_untranslated_prose(answer, question))

    def test_commerce_question_resolves_domain_before_reference_ranking(self):
        self.assertEqual(resolve_commerce_decision_domain("How should we allocate inventory to reduce stockouts?"), "inventory_allocation")
        self.assertEqual(resolve_commerce_decision_domain("Should we repeat the discount campaign?"), "promotion_planning")
        self.assertEqual(resolve_commerce_decision_domain("Compare transit time by region"), "nationwide_logistics")

        contexts = [
            {"document_name": "TikTok discount rules", "content": "Discount thresholds for a campaign.",
             "metadata": {"document_id": "TTS", "knowledge_domains": ["promotion_planning"],
                          "evidence_class": "platform_operating_rule", "source_publisher": "TikTok Shop",
                          "commerce_reference_active": True}},
            {"document_name": "Walmart operations", "content": "Promotion markdown risk and inventory decisions.",
             "chunk_index": 14,
             "metadata": {"document_id": "WMT", "knowledge_domains": ["promotion_planning"],
                          "evidence_class": "company_practice_reference", "commerce_reference_active": True}},
            {"document_name": "Walmart operations", "content": "Promotion markdown risk and inventory decisions.",
             "chunk_index": 14,
             "metadata": {"document_id": "WMT", "knowledge_domains": ["promotion_planning"],
                          "evidence_class": "company_practice_reference", "commerce_reference_active": True}},
        ]
        ranked = _rank_commerce_reference_evidence(contexts, "Should we repeat a promotion?", "promotion_planning", 3)
        self.assertEqual([item["metadata"]["document_id"] for item in ranked], ["WMT"])
        self.assertEqual(ranked[0]["source_id"], "S1")

    def test_commerce_reference_ranking_accepts_management_cookbook(self):
        context = {
            "document_name": "Manage your inventory",
            "content": "Record stock and set reorder points using usual sales and supplier lead time.",
            "metadata": {
                "document_id": "AUS-BUSINESS-INVENTORY-MANAGEMENT",
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "management_cookbook_reference",
                "source_publisher": "Australian Government, business.gov.au",
                "commerce_reference_active": True,
            },
        }

        ranked = _rank_commerce_reference_evidence(
            [context], "How should inventory replenishment be reviewed?", "inventory_allocation", 3,
        )

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["metadata"]["evidence_class"], "management_cookbook_reference")

    def test_commerce_reference_ranking_uses_matching_section_heading(self):
        question = "What customer needs should guide logistics planning?"
        contexts = [
            {
                "document_name": "General delivery guide", "chunk_index": 0,
                "content": "Balance delivery speed and shipping cost against customer needs.",
                "metadata": {
                    "document_id": "GENERAL-GUIDE",
                    "knowledge_domains": ["nationwide_logistics"],
                    "evidence_class": "management_cookbook_reference",
                    "commerce_reference_active": True,
                },
            },
            {
                "document_name": "Amazon supply-chain guide", "chunk_index": 4,
                "content": "Balance delivery speed and shipping cost against customer needs.",
                "metadata": {
                    "document_id": "AMAZON-GUIDE",
                    "section_title": "Customer needs",
                    "knowledge_domains": ["nationwide_logistics"],
                    "evidence_class": "company_practice_reference",
                    "commerce_reference_active": True,
                },
            },
        ]

        ranked = _rank_commerce_reference_evidence(
            contexts, question, "nationwide_logistics", 2,
        )

        self.assertEqual(ranked[0]["metadata"]["document_id"], "AMAZON-GUIDE")

    def test_commerce_reference_ranking_prefers_question_topic_over_broad_domain_terms(self):
        question = "Why are attributed campaign sales and ROAS insufficient to prove incremental sales?"
        contexts = [
            {
                "document_name": "General marketing plan",
                "content": (
                    "Promotion campaigns should define a target market, marketing goals, campaign budget, "
                    "measure campaign results, and review campaign results."
                ),
                "metadata": {
                    "document_id": "GENERAL-MARKETING-PLAN",
                    "knowledge_domains": ["promotion_planning"],
                    "evidence_class": "management_cookbook_reference",
                    "commerce_reference_active": True,
                },
            },
            {
                "document_name": "Incremental measurement guide",
                "content": (
                    "Incrementality asks what changed because of a campaign versus what would have happened "
                    "without it. Attributed sales and ROAS do not prove incremental sales. Use holdout, "
                    "treatment and control groups to estimate the difference."
                ),
                "metadata": {
                    "document_id": "INCREMENTAL-MEASUREMENT-GUIDE",
                    "knowledge_domains": ["promotion_planning"],
                    "evidence_class": "management_cookbook_reference",
                    "commerce_reference_active": True,
                },
            },
        ]

        ranked = _rank_commerce_reference_evidence(contexts, question, "promotion_planning", 1)

        self.assertEqual(ranked[0]["metadata"]["document_id"], "INCREMENTAL-MEASUREMENT-GUIDE")

    def test_commerce_domain_queries_cover_management_cookbook_topics(self):
        expected_terms = {
            "inventory_allocation": ("reorder point", "stocktake", "supplier reliability"),
            "promotion_planning": ("marketing plan", "promotion budget", "review campaign results"),
            "nationwide_logistics": ("delivery provider selection", "parcel size weight", "express delivery"),
        }
        for domain, terms in expected_terms.items():
            query = COMMERCE_DECISION_PROFILES[domain]["retrieval_query"].casefold()
            with self.subTest(domain=domain):
                for term in terms:
                    self.assertIn(term, query)

    def test_commerce_logistics_ranking_prefers_explicit_order_routing_criteria(self):
        contexts = [
            {
                "document_name": "Amazon parcel service overview", "chunk_index": 11,
                "content": "Amazon parcel shipping includes 2-5 day ground shipping and photo on delivery. It can fill geographic gaps and reduce long-distance shipping costs.",
                "metadata": {"document_id": "AMAZON", "knowledge_domains": ["nationwide_logistics"],
                             "evidence_class": "company_practice_reference", "commerce_reference_active": True},
            },
            {
                "document_name": "Shopify Smart Order Routing", "chunk_index": 2,
                "content": "Smart order routing checks which fulfillment locations have inventory available for all items, then applies routing rules: ship from the closest location, stay within the destination market, minimize split fulfillments, and use ranked locations.",
                "metadata": {"document_id": "SHOPIFY-ROUTING", "knowledge_domains": ["nationwide_logistics"],
                             "evidence_class": "company_practice_reference", "commerce_reference_active": True},
            },
        ]

        ranked = _rank_commerce_reference_evidence(
            contexts, "Should we redesign the nationwide delivery network?", "nationwide_logistics", 2,
        )

        self.assertEqual(ranked[0]["metadata"]["document_id"], "SHOPIFY-ROUTING")

    def test_logistics_document_selection_question_is_not_misread_as_network_comparison(self):
        context = {
            "document_name": "Kroger Vendor General Routing Instructions",
            "chunk_index": 0,
            "content": (
                "THE KROGER CO. VENDOR STANDARD ROUTING INSTRUCTIONS "
                "(Parcel, LTL, & TL Routing). Suppliers must follow Kroger's "
                "carrier and shipment requirements."
            ),
            "metadata": {
                "document_id": "KROGER-VENDOR-ROUTING-INSTRUCTIONS-2024",
                "section_title": "VENDOR STANDARD ROUTING INSTRUCTIONS",
                "knowledge_domains": ["nationwide_logistics"],
                "evidence_class": "company_practice_reference",
                "commerce_reference_active": True,
            },
        }

        ranked = _rank_commerce_reference_evidence(
            [context],
            "According to Kroger Vendor General Routing Instructions, what factors determine parcel versus LTL selection?",
            "nationwide_logistics",
            3,
        )

        self.assertEqual(
            [item["metadata"]["document_id"] for item in ranked],
            ["KROGER-VENDOR-ROUTING-INSTRUCTIONS-2024"],
        )

    def test_verified_company_policy_ranks_before_external_practice_for_same_domain(self):
        policy = {
            "document_name": "Commerce inventory policy",
            "content": "Review inventory for regional replenishment decisions.",
            "metadata": {
                "document_id": "INTERNAL-POLICY",
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_policy_reference",
                "commerce_reference_active": True,
            },
        }
        external = {
            "document_name": "External inventory example",
            "content": "Review inventory for regional replenishment decisions.",
            "metadata": {
                "document_id": "EXTERNAL-PRACTICE",
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_practice_reference",
                "commerce_reference_active": True,
            },
        }
        cookbook = {
            "document_name": "Manage inventory guide",
            "content": "Review inventory for regional replenishment decisions.",
            "metadata": {
                "document_id": "MANAGEMENT-COOKBOOK",
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "management_cookbook_reference",
                "commerce_reference_active": True,
            },
        }
        ranked = _rank_commerce_reference_evidence(
            [external, policy, cookbook], "How should we allocate inventory?", "inventory_allocation", 3,
        )
        self.assertEqual(
            [item["metadata"]["document_id"] for item in ranked],
            ["INTERNAL-POLICY", "MANAGEMENT-COOKBOOK", "EXTERNAL-PRACTICE"],
        )

    def test_commerce_reference_context_prefers_distinct_sources_before_repeating_chunks(self):
        def reference(document_id, chunk_index, evidence_class, content):
            return {
                "document_name": document_id,
                "chunk_index": chunk_index,
                "content": content,
                "metadata": {
                    "document_id": document_id,
                    "knowledge_domains": ["inventory_allocation"],
                    "evidence_class": evidence_class,
                    "commerce_reference_active": True,
                },
            }

        contexts = [
            reference("POLICY", 0, "company_policy_reference", "Review stock and inventory allocation."),
            reference("POLICY", 1, "company_policy_reference", "Check stock before inventory allocation."),
            reference("GUIDE", 2, "management_cookbook_reference", "Review stock and inventory allocation."),
        ]

        ranked = _rank_commerce_reference_evidence(
            contexts, "How should we review inventory allocation?", "inventory_allocation", 3,
        )

        self.assertEqual([item["metadata"]["document_id"] for item in ranked], ["POLICY", "GUIDE", "POLICY"])

    def test_company_policy_prompt_provenance_is_not_external_practice(self):
        evidence = Evidence(
            citation_id="S1", source_type="document", source="Uploaded policy",
            content="Use the approved allocation procedure.",
            metadata={"evidence_class": "company_policy_reference", "source_publisher": "Commerce Demo"},
        )
        formatted = _format_prompt_evidence(evidence)
        self.assertIn("Company-issued operating policy", formatted)
        self.assertNotIn("not Commerce Demo policy", formatted)

    def test_synthetic_company_policy_is_labeled_as_demo_only(self):
        evidence = Evidence(
            citation_id="S1", source_type="document", source="Commerce Demo inventory policy",
            content="Dung dữ liệu tồn kho để ưu tiên điều tra; không điều chuyển hàng chỉ tir cờ stockout.",
            metadata={
                "evidence_class": "company_policy_reference",
                "source_publisher": "Commerce Demo (fictional organization)",
                "synthetic_company_policy": True,
                "reference_applicability": "Fictional Commerce Demo scenario only.",
            },
        )
        formatted = _format_prompt_evidence(evidence)
        self.assertIn("Synthetic policy for fictional Commerce Demo", formatted)
        self.assertIn("never as policy of a real company", formatted)

        answer = _commerce_safe_fallback(
            "inventory_allocation", "Có nên điều chuyển hàng?", [evidence], decision_request=True,
        )
        self.assertIn("Policy giả lập Commerce Demo đã được truy xuất", answer)
        self.assertIn("không phải chính sách của doanh nghiệp thật", answer)
        self.assertIn("đối chiếu nguồn trước khi áp dụng", answer)
        self.assertNotIn("Dung dữ liệu", answer)

    def test_report_rejects_verbatim_quote_from_synthetic_scan_policy(self):
        analytics, knowledge, llm = Mock(), Mock(), Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {"inventory_latest_by_category": [{
                "snapshot_date": "2022-12-31", "category": "Streetwear",
                "stockout_products": 134, "overstock_products": 162,
            }]},
            "limitations": ["Category aggregates do not match surplus and shortage by SKU and location."],
            "dataset_note": "Synthetic Commerce data.",
        }
        policy_text = (
            "| SYNTHETIC DEMO POLICY | Dung dữ liệu tồn kho để ưu tiên điều tra; "
            "không tự động điều chuyển hàng chỉ tir cờ thiếu hoặc dư."
        )
        policy = Evidence(
            source_type="document", source="Inventory policy scan", content=policy_text,
            metadata={
                "evidence_class": "company_policy_reference", "synthetic_company_policy": True,
                "ocr": {"engine": "tesseract"}, "text_extraction_method": "tesseract",
            },
        )
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[policy])
        llm.generate.return_value = (
            "Không điều chuyển khi chưa ghép tồn kho theo SKU [L1]. Policy giả lập nêu: “"
            f"{policy_text}” [S1]"
        )

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Có nên điều chuyển hàng để giảm stockout?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
        ))

        self.assertEqual(llm.generate.call_count, 2)
        self.assertIn("văn bản OCR chưa được xác minh", result.answer)
        self.assertIn("Kiểm tra PDF gốc trước khi áp dụng", result.answer)
        self.assertNotIn(policy_text, result.answer)
        self.assertNotIn("không tự động điều chuyển", result.answer)
        self.assertIn("[S1]", result.answer)
        self.assertFalse(result.metadata["citation_validation_failed"])

    def test_commerce_promotion_causal_question_prefers_holdout_method_reference(self):
        def reference(document_id, content):
            return {
                "document_name": document_id,
                "content": content,
                "metadata": {
                    "document_id": document_id,
                    "knowledge_domains": ["promotion_planning"],
                    "evidence_class": "company_practice_reference",
                    "commerce_reference_active": True,
                },
            }

        contexts = [
            reference("AMAZON-REPORTING", "Campaign reporting includes impressions clicks sales and ROAS."),
            reference("DOORDASH-HOLDOUT", "Compare treatment and control groups using a holdout experiment to measure incremental sales and causal lift."),
        ]

        ranked = _rank_commerce_reference_evidence(
            contexts, "Does this promotion prove incremental lift? Use a holdout or control group.",
            "promotion_planning", 2,
        )

        self.assertEqual(ranked[0]["metadata"]["document_id"], "DOORDASH-HOLDOUT")

    def test_commerce_logistics_network_question_prefers_cost_service_method_reference(self):
        def reference(document_id, content):
            return {
                "document_name": document_id,
                "content": content,
                "metadata": {
                    "document_id": document_id,
                    "knowledge_domains": ["nationwide_logistics"],
                    "evidence_class": "company_practice_reference",
                    "commerce_reference_active": True,
                },
            }

        contexts = [
            reference("WALMART-ONBOARDING", "Provide ship points, lead time, facilities, carrier and daily capacity."),
            reference("AMAZON-NETWORK-METHOD", "Balance business priorities and customer needs, including fast shipping, shipping modes, network coverage, and long-distance shipping costs."),
        ]

        ranked = _rank_commerce_reference_evidence(
            contexts, "Should we redesign the regional network based on transit time and shipping costs?",
            "nationwide_logistics", 3,
        )

        self.assertEqual(ranked[0]["metadata"]["document_id"], "AMAZON-NETWORK-METHOD")
        self.assertNotIn("WALMART-ONBOARDING", [item["metadata"]["document_id"] for item in ranked])

    def test_synthetic_logistics_policy_survives_network_method_relevance_guard(self):
        policy = {
            "document_name": "Commerce Demo logistics policy",
            "content": "Policy giả lập: network design hoặc route optimization chỉ sau khi so sánh chi phí và dịch vụ theo tuyến.",
            "metadata": {
                "document_id": "CD-POL-LOG-001",
                "knowledge_domains": ["nationwide_logistics"],
                "evidence_class": "company_policy_reference",
                "synthetic_company_policy": True,
                "commerce_reference_active": True,
            },
        }
        unrelated = {
            "document_name": "Generic logistics checklist",
            "content": "This guide prioritizes customer needs and fast shipping.",
            "metadata": {
                "document_id": "GENERIC-LOGISTICS",
                "knowledge_domains": ["nationwide_logistics"],
                "evidence_class": "company_practice_reference",
                "commerce_reference_active": True,
            },
        }
        ranked = _rank_commerce_reference_evidence(
            [unrelated, policy],
            "Should we redesign the regional network based on transit time and shipping costs?",
            "nationwide_logistics", 3,
        )
        self.assertEqual([item["metadata"]["document_id"] for item in ranked], ["CD-POL-LOG-001"])

    def test_logistics_comparison_keeps_network_priorities_reference(self):
        def reference(document_id, evidence_class, content):
            return {
                "document_name": document_id,
                "content": content,
                "metadata": {
                    "document_id": document_id,
                    "knowledge_domains": ["nationwide_logistics"],
                    "evidence_class": evidence_class,
                    "commerce_reference_active": True,
                },
            }

        contexts = [
            reference("CD-POL-LOG-001", "company_policy_reference",
                      "Compare service and cost by route before changing network design."),
            reference("AMAZON-NETWORK-METHOD", "company_practice_reference",
                      "Consider business priorities and customer needs, including fast shipping, shipping modes, network coverage, and long-distance shipping costs."),
            reference("GENERIC-PARCEL-RATES", "management_cookbook_reference",
                      "Compare parcel shipping rates and transit times across providers."),
        ]

        ranked = _rank_commerce_reference_evidence(
            contexts,
            "What customer needs, service priorities, and cost evidence should guide a logistics-network comparison?",
            "nationwide_logistics", 3,
        )

        self.assertEqual(ranked[0]["metadata"]["document_id"], "CD-POL-LOG-001")
        self.assertIn("AMAZON-NETWORK-METHOD", [item["metadata"]["document_id"] for item in ranked])

    def test_commerce_reference_retrieval_abstains_when_source_does_not_cover_decision_need(self):
        def reference(document_id, domain, content):
            return {
                "document_name": document_id,
                "content": content,
                "metadata": {
                    "document_id": document_id,
                    "knowledge_domains": [domain],
                    "evidence_class": "company_practice_reference",
                    "commerce_reference_active": True,
                },
            }

        shopify_inventory = reference(
            "SHOPIFY-INVENTORY", "inventory_allocation",
            "Review inventory performance by location for regional replenishment decisions.",
        )
        walmart_onboarding = reference(
            "WALMART-ONBOARDING", "nationwide_logistics",
            "Provide ship points, delivery lead time, facilities, carrier and daily capacity.",
        )
        amazon_roas = reference(
            "AMAZON-ROAS", "promotion_planning",
            "Return on ad spend measures revenue against advertising spend.",
        )
        doordash_incrementality = reference(
            "DOORDASH-HOLDOUT", "promotion_planning",
            "Holdout and treatment-control tests estimate causal lift and incremental sales.",
        )
        self.assertEqual(
            _rank_commerce_reference_evidence(
                [shopify_inventory],
                "Can we set a new service target from historical fill rate?",
                "inventory_allocation", 3,
            ),
            [],
        )
        self.assertEqual(
            _rank_commerce_reference_evidence(
                [walmart_onboarding],
                "How did shipping fee and transit time change across regions?",
                "nationwide_logistics", 3,
            ),
            [],
        )
        self.assertEqual(
            _rank_commerce_reference_evidence(
                [walmart_onboarding],
                "Có nên chuyển năng lực giao hàng giữa East, Central và West để giảm trễ không?",
                "nationwide_logistics", 3,
            ),
            [],
        )
        self.assertEqual(
            _rank_commerce_reference_evidence(
                [amazon_roas], "Which promotion channel has the highest ROI?",
                "promotion_planning", 3,
            ),
            [],
        )
        ranked_roi_method = _rank_commerce_reference_evidence(
            [amazon_roas, doordash_incrementality],
            "Which promotion channel has the highest ROI?",
            "promotion_planning", 3,
        )
        self.assertEqual(
            [item["metadata"]["document_id"] for item in ranked_roi_method],
            ["DOORDASH-HOLDOUT"],
        )

    def test_network_decision_requires_a_concrete_routing_or_cost_criterion(self):
        def reference(document_id, content):
            return {
                "document_name": document_id,
                "content": content,
                "metadata": {
                    "document_id": document_id,
                    "knowledge_domains": ["nationwide_logistics"],
                    "evidence_class": "company_practice_reference",
                    "commerce_reference_active": True,
                },
            }

        marketing_copy = reference(
            "AMAZON-MARKETING",
            "Consider your business priorities and customer needs. Looking for fast shipping?",
        )
        network_method = reference(
            "AMAZON-NETWORK-METHOD",
            "Compare geographic gaps and long-distance shipping costs before choosing a network option.",
        )
        ranked = _rank_commerce_reference_evidence(
            [marketing_copy, network_method],
            "Should we redesign the regional network based on transit time and shipping costs?",
            "nationwide_logistics", 3,
        )

        self.assertEqual(
            [item["metadata"]["document_id"] for item in ranked],
            ["AMAZON-NETWORK-METHOD"],
        )

    def test_commerce_platform_rule_requires_platform_named_and_active_reference(self):
        tiktok = {
            "document_name": "TikTok Shop discount threshold guide",
            "content": "Promotion discount threshold guidance.",
            "metadata": {
                "document_id": "TTS", "source_publisher": "TikTok Shop Seller University",
                "knowledge_domains": ["promotion_planning"],
                "evidence_class": "platform_operating_rule", "commerce_reference_active": True,
            },
        }
        archived = {
            "document_name": "Archived campaign guide",
            "content": "Promotion campaign operations and planning.",
            "metadata": {
                "document_id": "OLD", "knowledge_domains": ["promotion_planning"],
                "evidence_class": "company_practice_reference", "commerce_reference_active": False,
            },
        }
        self.assertEqual(
            _rank_commerce_reference_evidence([tiktok, archived], "How should we run a promotion?", "promotion_planning", 3),
            [],
        )
        named = _rank_commerce_reference_evidence(
            [tiktok], "For TikTok Shop, what are the discount rules?", "promotion_planning", 3,
        )
        self.assertEqual([item["metadata"]["document_id"] for item in named], ["TTS"])

        shopee_inventory = {
            "document_name": "SHOPEE-UNI-INVENTORY-MANAGEMENT-VN.pdf",
            "content": "Review average SKU sales over 7 and 30 days; update SKU stock location and replenishment level.",
            "metadata": {
                "document_id": "SHOPEE-INVENTORY",
                "source_publisher": "Shopee Vietnam Seller Education Hub (Shopee Uni)",
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "platform_operating_rule", "commerce_reference_active": True,
            },
        }
        self.assertEqual(
            _rank_commerce_reference_evidence(
                [shopee_inventory], "How should we review stockouts?", "inventory_allocation", 3,
            ),
            [],
        )
        self.assertEqual(
            _rank_commerce_reference_evidence(
                [shopee_inventory],
                "What evidence should be checked before inventory transfer?",
                "inventory_allocation", 3,
            ),
            [],
        )
        named_inventory = _rank_commerce_reference_evidence(
            [shopee_inventory], "For Shopee, how should we review stockouts?", "inventory_allocation", 3,
        )
        self.assertEqual([item["metadata"]["document_id"] for item in named_inventory], ["SHOPEE-INVENTORY"])
        generic_inventory = {
            "document_name": "Sam's Club Smart Inventory",
            "content": "Smart Inventory item category and stock availability; suppliers review replenishment status.",
            "metadata": {
                "document_id": "SAMS-INVENTORY",
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_practice_reference", "commerce_reference_active": True,
            },
        }
        mixed_inventory = _rank_commerce_reference_evidence(
            [generic_inventory, shopee_inventory],
            "For Shopee, how should sellers review stockouts and replenishment?",
            "inventory_allocation", 3,
        )
        self.assertEqual(
            [item["metadata"]["document_id"] for item in mixed_inventory],
            ["SHOPEE-INVENTORY", "SAMS-INVENTORY"],
        )

    def test_named_company_reference_precedes_demo_policy_for_source_specific_question(self):
        amazon = {
            "document_name": "Amazon FBA Restock Tool Guide",
            "content": "Review sales and inventory signals in the Amazon FBA Restock Tool before replenishing.",
            "metadata": {
                "document_id": "AMAZON-FBA",
                "source_publisher": "Amazon",
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_practice_reference",
                "commerce_reference_active": True,
            },
        }
        demo_policy = {
            "document_name": "Commerce Demo inventory policy",
            "content": "Before replenishing, review stock and inventory signals.",
            "metadata": {
                "document_id": "CD-POL-INV-001",
                "source_publisher": "Commerce Demo",
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_policy_reference",
                "commerce_reference_active": True,
                "synthetic_company_policy": True,
            },
        }

        ranked = _rank_commerce_reference_evidence(
            [demo_policy, amazon],
            "What should an Amazon seller review in the FBA Restock Tool before replenishing?",
            "inventory_allocation",
            2,
        )

        self.assertEqual(
            [item["metadata"]["document_id"] for item in ranked],
            ["AMAZON-FBA", "CD-POL-INV-001"],
        )

    def test_commerce_inventory_ranking_prefers_operating_steps_over_table_of_contents(self):
        toc = {
            "document_name": "Sam's Club Supplier Hub guide",
            "chunk_index": 2,
            "content": "Table Of Contents Inventory update Smart Inventory Supplier Management",
            "metadata": {
                "document_id": "SAMS", "page_number": 3,
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_practice_reference",
                "commerce_reference_active": True,
            },
        }
        operating_steps = {
            "document_name": "Sam's Club Supplier Hub guide",
            "chunk_index": 29,
            "content": (
                "Smart Inventory identifies items that are out of stock and low in stock. "
                "Suppliers can use category-level and item-level filters to review alerts."
            ),
            "metadata": {
                "document_id": "SAMS", "page_number": 23,
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_practice_reference",
                "commerce_reference_active": True,
            },
        }
        ranked = _rank_commerce_reference_evidence(
            [toc, operating_steps],
            "Should stockout and overstock products be reallocated?",
            "inventory_allocation",
            3,
        )
        self.assertEqual(ranked[0]["metadata"]["page_number"], 23)

    def test_commerce_bm25_ranking_preserves_the_more_relevant_ocr_page(self):
        question = (
            "Theo trang hướng dẫn Shopee, điều kiện nào khiến một SKU được đánh dấu "
            "cần bổ sung kho hàng sớm?"
        )
        source = {
            "document_id": "SHOPEE-UNI-INVENTORY-MANAGEMENT-VN",
            "knowledge_domains": ["inventory_allocation"],
            "evidence_class": "platform_operating_rule",
            "commerce_reference_active": True,
            "source_publisher": "Shopee Vietnam Seller Education Hub (Shopee Uni)",
        }
        generic_page = {
            "document_name": "Quản lý tồn kho",
            "chunk_index": 3,
            "content": (
                "SELLER EDUCATION HUB Bổ sung hàng tồn kho - tăng doanh số. "
                "Người bán có thể hiểu nhu cầu và chu kỳ bán hàng của sản phẩm "
                "và theo dõi mức độ cần bổ sung hàng."
            ),
            "metadata": {**source, "page_number": 4, "section_title": "Bổ sung hàng tồn kho"},
            "retrieval_score": 26.518,
            "retrieval_method": "bm25",
        }
        relevant_ocr_page = {
            "document_name": "Quản lý tồn kho",
            "chunk_index": 10,
            "content": (
                "Kiểm tra trạng thái Mức độ cần bổ sung hàng cho từng SKU. "
                "Bổ sung kho hàng sớm cho biết SKU sắp hết hàng, nghĩa là số lượng "
                "tồn kho nằm dưới Số lượng tồn kho tối thiểu."
            ),
            "metadata": {
                **source,
                "page_number": 11,
                "section_title": "Giảm thiểu tình trạng hết hàng",
                "text_extraction_method": "pymupdf+tesseract",
            },
            "retrieval_score": 30.409,
            "retrieval_method": "bm25",
        }

        ranked = _rank_commerce_reference_evidence(
            [generic_page, relevant_ocr_page], question, "inventory_allocation", 1,
        )

        self.assertEqual(ranked[0]["metadata"]["page_number"], 11)
        self.assertEqual(ranked[0]["metadata"]["text_extraction_method"], "pymupdf+tesseract")

    def test_commerce_inventory_reallocation_prefers_location_transfer_guidance(self):
        sams_ui = {
            "document_name": "Sam's Club Supplier Hub guide",
            "chunk_index": 29,
            "content": (
                "Smart Inventory page categories tab lets suppliers filter item-level stock availability "
                "and low-stock status."
            ),
            "metadata": {
                "document_id": "SAMS", "page_number": 23,
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_practice_reference",
                "commerce_reference_active": True,
            },
        }
        location_transfer = {
            "document_name": "Shopify multi-location inventory",
            "chunk_index": 8,
            "content": (
                "Reviewing sales and inventory performance by location provides data for regional "
                "replenishment decisions. A multi-location transfer workflow uses location-level inventory "
                "and demand planning rather than rushed reactions."
            ),
            "metadata": {
                "document_id": "SHOPIFY-MULTI-LOCATION", "page_number": None,
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_practice_reference",
                "commerce_reference_active": True,
            },
        }

        ranked = _rank_commerce_reference_evidence(
            [sams_ui, location_transfer],
            "Should stockout and overstock products be reallocated?",
            "inventory_allocation",
            3,
        )

        self.assertEqual(ranked[0]["metadata"]["document_id"], "SHOPIFY-MULTI-LOCATION")

    def test_commerce_inventory_service_target_requires_target_specific_reference(self):
        transfer_guide = {
            "document_name": "Shopify multi-location inventory",
            "chunk_index": 8,
            "content": "Multi-location transfer workflows use location-level demand planning to reduce stockout crises.",
            "metadata": {
                "document_id": "SHOPIFY-MULTI-LOCATION", "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_practice_reference", "commerce_reference_active": True,
            },
        }
        stock_state_guide = {
            "document_name": "Sam's Club Supplier Hub guide",
            "chunk_index": 29,
            "content": (
                "Smart Inventory shows OOS %, low stock, in stock and out of stock status at category and item level."
            ),
            "metadata": {
                "document_id": "SAMS", "page_number": 23,
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_practice_reference", "commerce_reference_active": True,
            },
        }

        ranked = _rank_commerce_reference_evidence(
            [transfer_guide, stock_state_guide],
            "Tình trạng availability thay đổi thế nào, có thể đặt service target mới không?",
            "inventory_allocation",
            3,
        )

        self.assertEqual(ranked, [])

    def test_commerce_retrieval_does_not_treat_negated_service_target_as_target_request(self):
        stock_state_guide = {
            "document_name": "Sam's Club Supplier Hub guide",
            "chunk_index": 29,
            "content": (
                "Smart Inventory shows OOS %, low stock, in stock and out of stock status at category and item level."
            ),
            "metadata": {
                "document_id": "SAMS", "page_number": 23,
                "knowledge_domains": ["inventory_allocation"],
                "evidence_class": "company_practice_reference", "commerce_reference_active": True,
            },
        }

        ranked = _rank_commerce_reference_evidence(
            [stock_state_guide],
            "How should historical stock availability and low-stock signals be reviewed without treating them as an approved service target?",
            "inventory_allocation",
            3,
        )

        self.assertEqual([item["metadata"]["document_id"] for item in ranked], ["SAMS"])

    def test_commerce_logistics_ranking_prefers_supplier_readiness_fields_when_asked(self):
        route_article = {
            "document_name": "Shopify Smart Order Routing",
            "chunk_index": 1,
            "content": "Smart order routing assigns orders to the best fulfillment location.",
            "metadata": {
                "document_id": "SHOPIFY-ROUTING",
                "knowledge_domains": ["nationwide_logistics"],
                "evidence_class": "company_practice_reference",
                "commerce_reference_active": True,
            },
        }
        supplier_checklist = {
            "document_name": "Walmart GFR Supplier Onboarding Checklist",
            "chunk_index": 27,
            "content": (
                "Provide delivery details, set up lead time, and add facilities. "
                "Provide unit capacity by day, ship point, carrier and inventory feed."
            ),
            "metadata": {
                "document_id": "WMT-GFR",
                "knowledge_domains": ["nationwide_logistics", "inventory_allocation"],
                "evidence_class": "company_practice_reference",
                "commerce_reference_active": True,
            },
        }
        ranked = _rank_commerce_reference_evidence(
            [route_article, supplier_checklist],
            "What carrier, facility capacity, inventory feed, and delivery lead-time data should we collect?",
            "nationwide_logistics",
            3,
        )
        self.assertEqual(ranked[0]["metadata"]["document_id"], "WMT-GFR")

    def test_commerce_report_combines_sql_observations_and_management_cookbook(self):
        snapshot = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {"inventory_by_year": [{"year": 2022, "stockout_snapshots": 14, "overstock_snapshots": 9}]},
            "limitations": ["No warehouse-level lead time or transfer cost."],
            "dataset_note": "Synthetic competition data.",
        }
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = snapshot
        reference = Evidence(
            citation_id="S1", source_type="document", source="business.gov.au",
            content="Set reorder points using usual sales, supplier lead time, and seasonal patterns.",
            metadata={"evidence_class": "management_cookbook_reference",
                      "source_publisher": "Australian Government, business.gov.au",
                      "reference_applicability": "General small-business method, not Commerce Demo policy."},
        )
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[reference])
        llm = Mock()
        llm.generate.return_value = (
            "Khuyến nghị: rà soát các nhóm có tín hiệu stockout trước khi cân nhắc điều chuyển [C1]. "
            "Cookbook quản lý của business.gov.au khuyên rà soát doanh số thông thường, lead time và mùa vụ khi đặt điểm đặt hàng; đây là phương pháp tham khảo, không phải chính sách của Commerce Demo [S1]. "
            "Cần xác nhận tồn kho, nhu cầu, lead time và chi phí điều chuyển trước khi thử nghiệm [L1]."
        )

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Có nên phân bổ lại tồn kho để giảm stockout không?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "operations"},
        ))

        self.assertEqual(result.agent, "report")
        self.assertEqual(result.metadata["decision_analysis"], "commerce_sql_and_operating_references")
        self.assertEqual({item.citation_id for item in result.evidence}, {"C1", "L1", "S1"})
        self.assertIn("Answer every explicit factual/comparison subquestion first", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("Build the recommendation from the retrieved reference's actual method", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("connect it to the relevant SQL observation", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("Use only SQL observation groups that directly answer the question", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("latest-snapshot SQL overlap aggregate", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("Citations [L#] refer to curated schema/data-coverage constraints", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("do not quote extracted text verbatim", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("never silently repair an uncertain OCR phrase", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("Cite [L#] when stating that a required field", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("[L1] No warehouse-level lead time or transfer cost.", llm.generate.call_args.args[0])
        self.assertIn("write the entire answer in Vietnamese", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("Management cookbook published by Australian Government, business.gov.au", llm.generate.call_args.args[0])
        self.assertIn("not Commerce Demo policy", llm.generate.call_args.args[0])
        self.assertIn("[C1]", result.answer)
        self.assertNotEqual(result.answer, "The answer was withheld because it could not be validated against the verified evidence. Please retry the question.")

    def test_commerce_ui_mode_retrieves_operating_method_for_indirect_decision_question(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {"inventory_by_year": [{"year": 2022, "stockout_snapshots": 14}]},
            "limitations": ["Warehouse-level lead time and transfer cost are unavailable."],
            "dataset_note": "Synthetic competition data.",
        }
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="Inventory management cookbook",
            content="Set reorder points using usual sales, supplier lead time, and seasonal patterns.",
            metadata={"evidence_class": "management_cookbook_reference",
                      "source_publisher": "business.gov.au"},
        )])
        llm = Mock()
        llm.generate.return_value = (
            "Check item-level demand and stock before adjusting replenishment, using the cited guide's "
            "reorder-point method as a reference [S1]. The 2022 data recorded 14 stockout snapshots [C1], "
            "but warehouse-level lead time and transfer cost are unavailable [L1]."
        )

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="What operational changes would reduce products being unavailable for customers?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "admin",
                      "commerce_decision_support": True},
        ))

        knowledge.run.assert_called_once()
        self.assertEqual({item.citation_id for item in result.evidence}, {"C1", "L1", "S1"})
        self.assertIn("[S1]", result.answer)
        self.assertIn("[L1]", result.answer)

    def test_commerce_report_uses_named_platform_operating_rule_for_conditional_advice(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {"inventory_by_year": [{"year": 2022, "stockout_snapshots": 14}]},
            "limitations": [
                "Commerce rows do not identify a Shopee shop or SKU-level replenishment.",
                "The schema has no separate low-stock alert or seller-defined minimum-stock threshold.",
            ],
            "dataset_note": "Synthetic competition data.",
        }
        platform_rule = Evidence(
            citation_id="S1", source_type="document", source="Shopee Uni inventory guide",
            content="Compare SKU sales over 7 and 30 days and review low-stock alerts before replenishment.",
            metadata={
                "evidence_class": "platform_operating_rule",
                "source_publisher": "Shopee Uni",
                "reference_applicability": "Shopee sellers",
            },
        )
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[platform_rule])
        llm = Mock()
        llm.generate.return_value = (
            "Shopee Uni recommends comparing sales by SKU over 7- and 30-day windows and reviewing low-stock "
            "alerts before replenishment; this guidance applies only to Shopee sellers [S1]. "
            "The Commerce inventory aggregate records 14 stockout snapshots in 2022 [C1]. "
            "Because these synthetic data do not identify a Shopee shop, first validate demand and stock by SKU "
            "for that shop before recommending replenishment [L1]."
        )

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="For a Shopee seller, what should we do when a SKU has a stockout alert?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "operations"},
        ))

        self.assertEqual({item.citation_id for item in result.evidence}, {"C1", "L1", "L2", "S1"})
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertIn("Shopee Uni", llm.generate.call_args.args[0])
        self.assertIn("applies only when that named platform is explicitly in scope", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("no separate low-stock alert", llm.generate.call_args.args[0])
        self.assertIn("[S1]", result.answer)

    def test_report_prompt_labels_management_cookbook_as_method_not_policy(self):
        evidence = Evidence(
            citation_id="S1", source_type="document", source="business.gov.au",
            content="Set reorder points using usual sales and supplier lead time.",
            metadata={
                "evidence_class": "management_cookbook_reference",
                "source_publisher": "Australian Government, business.gov.au",
                "reference_applicability": "General small-business method; not Commerce Demo policy.",
            },
        )

        prompt_evidence = _format_prompt_evidence(evidence)

        self.assertIn("Management cookbook", prompt_evidence)
        self.assertIn("not Commerce Demo policy", prompt_evidence)
        self.assertIn("General small-business method", prompt_evidence)

    def test_commerce_report_rejects_replenishment_from_unattributed_platform_count(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {"inventory_latest_by_category": [{
                "category": "Outdoor", "stockout_products": 12, "overstock_products": 5,
            }]},
            "limitations": ["Commerce rows have no platform, seller, or SKU-level identification."],
            "dataset_note": "Synthetic competition data.",
        }
        reference = Evidence(
            citation_id="S1", source_type="document", source="Shopee inventory guide",
            content="31 SKUs in your shop are Out of Stock and 2 SKUs are in Low Stock. Replenish and update stock immediately.",
            metadata={
                "evidence_class": "platform_operating_rule",
                "source_publisher": "Shopee Uni",
                "reference_applicability": "Historical 2019 interface example; sample counts and thresholds are not current policy.",
            },
        )
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[reference])
        unsafe = (
            "The Commerce data shows 2 low-stock SKUs [C1]. Shopee's guide says to replenish the 2 low-stock SKUs "
            "immediately [S1]. Replenish those 2 SKUs now [C1][S1]."
        )
        llm = Mock()
        llm.generate.side_effect = [unsafe, unsafe]

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="For a Shopee seller, what action should we take for the low-stock alert?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "operations"},
        ))

        self.assertTrue(result.metadata["decision_fallback_used"])
        self.assertEqual(result.metadata["answer_fallback_reason"], "evidence_validation_failed")
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertIn("Verify that Shop's SKU-level stock and demand", result.answer)
        self.assertNotRegex(result.answer, r"(?i)replenish.{0,50}\b2\s+(?:low.stock\s+)?skus?\b")
        self.assertNotIn("Outdoor=12", result.answer)
        self.assertIn("Historical interface example", result.answer)
        self.assertIn("[S1]", result.answer)

    def test_commerce_report_repairs_rounded_values_and_unsupported_inventory_transfer(self):
        snapshot = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {
                "inventory_by_year": [{"year": 2022, "avg_fill_rate": 0.9635, "stockout_snapshots": 3490}],
                "inventory_latest_by_category": [{"category": "Outdoor", "stockout_products": 95, "overstock_products": 113}],
            },
            "limitations": ["No warehouse location or demand forecast."],
            "dataset_note": "Synthetic competition data.",
        }
        sql_evidence = Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce inventory SQL",
            content='avg_fill_rate: 0.9635; stockout_snapshots: 3490',
        )
        self.assertFalse(_decision_numeric_facts_match_cited_evidence("Average fill rate was 0.96 [C1].", [sql_evidence]))
        self.assertEqual(_unsupported_decision_numeric_tokens("Average fill rate was 0.96 [C1].", [sql_evidence]), ["0.96"])
        self.assertTrue(_decision_numeric_facts_match_cited_evidence("Fill rate was 0.9635 [C1].", [sql_evidence]))
        amount_evidence = Evidence(
            citation_id="C2", source_type="commerce_sql", source="Promotion SQL",
            content='promotion observations: [{"net_sales": 454361595.764106}]',
        )
        self.assertTrue(_decision_numeric_facts_match_cited_evidence(
            "Doanh thu thuần là 454.361.595,76 [C2].", [amount_evidence],
        ))
        self.assertTrue(_decision_numeric_facts_match_cited_evidence(
            "1. Collect location-level demand [C1].\n2. Review lead times [C1].", [sql_evidence],
        ))
        company_reference = Evidence(
            citation_id="S1", source_type="document", source="WMT-2023 supply-chain strategy",
            content="Walmart describes data-led inventory placement.",
        )
        self.assertTrue(_decision_numeric_facts_match_cited_evidence(
            "Walmart's 2023 strategy describes this practice [S1].", [company_reference],
        ))

        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = snapshot
        reference = Evidence(
            citation_id="S1", source_type="document", source="Walmart operating reference",
            content="Walmart describes data-led inventory placement.",
            metadata={"evidence_class": "company_practice_reference", "source_publisher": "Walmart Inc."},
        )
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[reference])
        llm = Mock()
        llm.generate.side_effect = [
            "Average fill rate was 0.96 and Outdoor has surplus inventory; move stock to other categories [C1][C2].",
            "Do not reallocate from category counts alone. First collect SKU-level demand and location-level stock before considering a transfer [C1][C2]. "
            "Walmart describes data-led inventory placement; use this as an attributed practice example, not Commerce Demo policy [S1].",
        ]

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Should we rebalance inventory toward categories with repeated stockout signals?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "operations"},
        ))

        self.assertEqual(llm.generate.call_count, 2)
        self.assertTrue(result.metadata["decision_validation_repair_attempted"])
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertIn("Do not reallocate from category counts alone", result.answer)
        self.assertIn("These figures come from the synthetic Commerce Demo dataset", result.answer)
        self.assertIn("[S1]", result.answer)
        self.assertIn("do not claim one SKU has both states", llm.generate.call_args_list[1].args[0])
        self.assertIn("explicitly identify them as synthetic Commerce demo data", llm.generate.call_args_list[0].kwargs["instructions"])

    def test_commerce_answers_present_requested_fill_rate_as_percent(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Inventory query",
            content="question-specific SQL observations",
            metadata={"commerce_observations": [
                {"year": 2020, "avg_fill_rate": 0.9656},
                {"year": 2021, "avg_fill_rate": 0.9619},
                {"year": 2022, "avg_fill_rate": 0.9635},
            ]},
        )]
        question = "Trong từng năm 2020–2022, fill rate thay đổi thế nào?"

        self.assertTrue(_commerce_fill_rate_missing_percent(
            "Fill rate: 0.9656, 0.9619, 0.9635 [C1]", evidence, question,
        ))
        self.assertFalse(_commerce_fill_rate_missing_percent(
            "Fill rate: 96,56%, 96,19%, 96,35% [C1]", evidence, question,
        ))
        self.assertFalse(_commerce_fill_rate_missing_percent(
            "Fill rate: 0.9656, 0.9619, 0.9635 [C1]", evidence,
            "Show the raw ratio (0-to-1) for fill rate in 2020–2022.",
        ))
        row_evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Inventory query",
            metadata={"commerce_observations": [{"fill_rate": 0.95}]},
        )]
        self.assertTrue(_commerce_fill_rate_missing_percent(
            "Fill rate: 0.95 [C1]", row_evidence, "What is the fill rate?",
        ))

    def test_commerce_answer_limits_unrequested_recommendation_list_to_one_action(self):
        self.assertTrue(_has_multiple_unrequested_actions(
            "### 3. Khuyến nghị hành động tiếp theo\n"
            "- Thu thập dữ liệu vị trí.\n- So sánh chi phí.\n"
        ))
        self.assertFalse(_has_multiple_unrequested_actions(
            "### Khuyến nghị hành động tiếp theo\n- Thu thập dữ liệu vị trí.\n"
        ))

    def test_commerce_dataset_disclosure_uses_a_cited_sql_source_and_question_language(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
            content="Read-only synthetic Commerce aggregate.",
            metadata={"dataset_note": "Synthetic Kaggle Commerce data."},
        )]

        english = _ensure_commerce_dataset_disclosure("The campaign led the ranking [C1].", evidence, "Which campaign ranked highest?")
        self.assertTrue(english.startswith("These figures come from the synthetic Commerce Demo dataset, not a real retailer. [C1]"))

        vietnamese = _ensure_commerce_dataset_disclosure("Spring Sale đứng đầu [C1].", evidence, "Chiến dịch nào đứng đầu?")
        self.assertTrue(vietnamese.startswith("Các số liệu dưới đây thuộc bộ dữ liệu Commerce Demo giả lập"))
        self.assertIn("[C1]", vietnamese)

        already_disclosed = "These figures come from the synthetic Commerce Demo dataset [C1]."
        self.assertEqual(_ensure_commerce_dataset_disclosure(already_disclosed, evidence, "Which campaign ranked highest?"), already_disclosed)
        self.assertEqual(_ensure_commerce_dataset_disclosure("Answer [C1].", [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
            metadata={"dataset_note": "Observed production data."},
        )], "Which campaign ranked highest?"), "Answer [C1].")

    def test_commerce_campaign_guard_rejects_causal_ranking_language(self):
        self.assertTrue(_has_unsupported_campaign_causal_claim(
            "The campaign that generated the most tagged net sales also produced the highest profit proxy."
        ))
        self.assertTrue(_has_unsupported_campaign_causal_claim(
            "Chiến dịch này mang lại doanh thu và lãi gộp cao nhất trong kỳ."
        ))
        self.assertFalse(_has_unsupported_campaign_causal_claim(
            "Spring Sale recorded the highest campaign-window tagged net sales; this is descriptive, not causal."
        ))
        self.assertFalse(_has_unsupported_campaign_causal_claim(
            "The data does not establish that the campaign produced incremental sales."
        ))
        self.assertFalse(_has_unsupported_campaign_causal_claim(
            "Chưa thể kết luận chiến dịch tạo ra doanh thu tăng thêm."
        ))

    def test_commerce_report_rejects_overlap_count_without_joint_sql_evidence(self):
        question = "Should we transfer inventory based on stockout and overstock flags?"
        answer = "There were 0 products with both stockout and overstock flags [C1]."
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce inventory SQL",
            content='question_specific_query observations: [{"stockout_days": 0, "stockout_count": 12}]',
            metadata={"sql_query": "SELECT SUM(stockout_flag::int) AS stockout_count FROM commerce.inventory"},
        )]

        self.assertEqual(
            _report_validation_failure(answer, evidence, {"C1"}, question),
            "inventory_overlap_count_not_present_in_cited_sql",
        )

        evidence[0].content = 'question_specific_query observations: [{"both_flagged_rows": 0}]'
        evidence[0].metadata["sql_query"] = (
            "SELECT COUNT(*) FILTER (WHERE i.stockout_flag AND i.overstock_flag) AS both_flagged_rows "
            "FROM commerce.inventory i"
        )
        self.assertIsNone(_report_validation_failure(answer, evidence, {"C1"}, question))

    def test_commerce_sales_and_profit_proxy_use_commerce_numeric_validation(self):
        question = (
            "Should we expand discounts based on sales or wait for an incrementality test? "
            "Compare the available outcome and profit proxy, then identify missing evidence."
        )
        answer = (
            "The available outcome shows net sales of 728500 and a profit proxy of 107000 [C1]. "
            "This supports monitoring the campaign, but does not establish incremental lift; "
            "test against a holdout before scaling [L1][S1]."
        )
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Promotion outcomes",
                content='question-specific SQL observations: '
                        '[{"net_sales": 728500, "gross_profit_proxy": 107000}]',
                metadata={"commerce_domain": "promotion_planning"},
            ),
            Evidence(citation_id="L1", source_type="commerce_schema", source="Promotion coverage",
                     content="The data has no randomized holdout."),
            Evidence(citation_id="S1", source_type="document", source="Measurement guide",
                     content="Use a holdout to estimate incrementality."),
        ]

        self.assertTrue(_is_financial_summary(question))
        self.assertIsNone(_report_validation_failure(answer, evidence, {"C1", "L1", "S1"}, question))

    def test_commerce_decision_validation_detects_an_omitted_requested_sql_measure(self):
        question = "Compare campaign sales and the profit proxy before deciding whether to expand."
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Promotion outcomes",
            content="Aggregate observations.",
            metadata={"commerce_observations": [{
                "net_sales": 728500.0, "merchandise_gross_profit_proxy": 107000.0,
            }]},
        )]
        answer = "Observed campaign sales were 728500 [C1]."

        self.assertEqual(
            _commerce_requested_observation_missing(answer, evidence, question),
            "merchandise_gross_profit_proxy",
        )
        self.assertIsNone(_commerce_requested_observation_missing(
            answer + " The profit proxy was 107000 [C1].", evidence, question,
        ))

    def test_unavailable_incremental_profit_or_roi_does_not_require_profit_proxy(self):
        question = (
            "Should we make deeper discounts the default for campaigns? Compare the 2022 campaign "
            "evidence and explain whether it proves incremental profit or ROI."
        )
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Promotion outcomes",
            content="Aggregate observations.",
            metadata={"commerce_observations": [{
                "year": 2022, "net_sales": 100.0, "merchandise_gross_profit_proxy": 5.0,
            }]},
        )]
        abstention = (
            "These campaign observations do not establish incremental profit or ROI because no "
            "campaign cost or counterfactual is available [C1]."
        )

        self.assertIsNone(_commerce_requested_observation_missing(abstention, evidence, question))
        explicit_proxy_question = question + " Also compare the merchandise gross profit proxy."
        self.assertEqual(
            _commerce_requested_observation_missing(abstention, evidence, explicit_proxy_question),
            "merchandise_gross_profit_proxy",
        )

    def test_requested_net_sales_accepts_campaign_window_net_item_sales_field(self):
        question = "Which campaign had the highest net sales during its campaign window?"
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Campaign window aggregate",
            content="Campaign window outcomes.",
            metadata={"commerce_observations": [{"net_item_sales": 90345105.91}]},
        )]

        self.assertIsNone(_commerce_requested_observation_missing(
            "Spring Sale had net sales of 90345105.91 [C1].", evidence, question,
        ))
        self.assertEqual(_commerce_requested_observation_missing(
            "Spring Sale was the highest by net sales [C1].", evidence, question,
        ), "net_sales")

    def test_commerce_report_repairs_overlap_count_that_query_does_not_measure(self):
        analytics = SQLAnalyticsAgent(repository=Mock(), llm=Mock())
        analytics.commerce_question_observations = Mock(return_value={
            "domain": "inventory_allocation",
            "source_tables": ["commerce.inventory"],
            "sql_query": "SELECT SUM(stockout_flag::int) AS stockout_count FROM commerce.inventory",
            "observations": [{"stockout_count": 12, "stockout_days": 0}],
            "limitations": ["Stock is not available by SKU and location."],
            "dataset_note": "Synthetic Kaggle Commerce data.",
        })
        analytics.commerce_latest_inventory_flag_overlap = Mock(return_value=[])
        reference = Evidence(
            citation_id="S1", source_type="document", source="Shopify location inventory reference",
            content="Review stock and demand by location before reallocation.",
            metadata={"evidence_class": "company_practice_reference", "source_publisher": "Shopify"},
        )
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[reference])
        llm = Mock()
        llm.generate.side_effect = [
            "Truy vấn cho thấy 0 sản phẩm đồng thời có cả hai cờ [C1]. Shopify có quy trình đa vị trí [S1].",
            "Không thể xác định số sản phẩm có cả hai cờ vì truy vấn chỉ đếm stockout [C1][L1]. "
            "Chưa điều chuyển hàng; cần ghép tồn kho và nhu cầu theo SKU, địa điểm trước. "
            "Shopify hướng dẫn rà soát theo địa điểm; đây là ví dụ bên ngoài [S1].",
        ]

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Có bao nhiêu sản phẩm vừa bị gắn cờ stockout vừa overstock, có nên chuyển hàng không?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "operations"},
        ))

        self.assertEqual(llm.generate.call_count, 2)
        self.assertTrue(result.metadata["decision_validation_repair_attempted"])
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertNotIn("0 sản phẩm", result.answer)
        self.assertIn("joint stockout-and-overstock count", llm.generate.call_args_list[1].args[0])

    def test_commerce_report_rejects_inventory_transfer_advice_from_category_counts(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {
                "inventory_latest_by_category": [
                    {"snapshot_date": "2022-12-31", "category": "Streetwear", "stockout_products": 134,
                     "overstock_products": 162, "both_flagged_products": 103},
                    {"snapshot_date": "2022-12-31", "category": "Outdoor", "stockout_products": 95,
                     "overstock_products": 113, "both_flagged_products": 74},
                ],
                "inventory_latest_flag_overlap": [{
                    "snapshot_date": "2022-12-31", "product_rows": 424,
                    "stockout_flagged_rows": 232, "overstock_flagged_rows": 232,
                    "both_flagged_rows": 232,
                }],
            },
            "limitations": ["No SKU/location mapping or transfer economics."],
            "dataset_note": "Synthetic competition data.",
        }
        reference = Evidence(
            citation_id="S1", source_type="document", source="Shopify multi-location reference",
            content="Review sales and inventory by location before regional replenishment decisions.",
            metadata={"evidence_class": "company_practice_reference", "source_publisher": "Shopify"},
        )
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[reference])
        unsafe = (
            "Cân nhắc chuyển hàng từ nhóm overstock sang nhóm stockout. Nếu chưa khớp SKU thì tăng đặt hàng hoặc giảm giá. "
            "Shopify mô tả quy trình quản lý đa vị trí [C1][C2][S1]."
        )
        llm = Mock()
        llm.generate.side_effect = [unsafe, unsafe]

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Trong snapshot tồn kho mới nhất, nhóm hàng nào có nhiều sản phẩm bị gắn cờ stockout nhất? Có nên tái cân bằng tồn kho bằng cách chuyển hàng từ nhóm overstock sang không?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "finance_analyst"},
        ))

        self.assertTrue(result.metadata["decision_fallback_used"])
        self.assertIn("232 dòng sản phẩm", result.answer)
        self.assertIn("Streetwear=134", result.answer)
        self.assertIn("Chưa điều chuyển tồn kho", result.answer)
        self.assertNotIn("Cân nhắc chuyển hàng", result.answer)
        self.assertNotIn("tăng đặt hàng", result.answer)
        self.assertNotIn("giảm giá", result.answer)
        self.assertIn("[S1]", result.answer)

    def test_commerce_safe_fallback_covers_all_domains_with_sql_and_company_citations(self):
        evidence = [
            Evidence(citation_id="C1", source_type="commerce_sql", source="Commerce SQL", content="Aggregate data."),
            Evidence(citation_id="C2", source_type="commerce_sql", source="Commerce SQL", content="Category data."),
            Evidence(citation_id="S1", source_type="document", source="Walmart reference",
                     content="Company practice.", metadata={"evidence_class": "company_practice_reference",
                                                              "source_publisher": "Walmart Inc."}),
        ]
        for domain in ("inventory_allocation", "promotion_planning", "nationwide_logistics"):
            with self.subTest(domain=domain):
                answer = _commerce_safe_fallback(domain, "Should we change the current approach?", evidence)
                self.assertIn("[C1]", answer)
                self.assertIn("[S1]", answer)
                self.assertIn("Retrieved passage from Walmart Inc.: “Company practice.”", answer)
                self.assertIsNone(_report_validation_failure(
                    answer, evidence, {"C1", "C2", "S1"}, "Should we change the current approach?",
                ))

    def test_english_fallback_uses_catalog_summary_for_synthetic_ocr_policy(self):
        cases = (
            (
                "inventory_allocation",
                "Should inventory be transferred between categories?",
                "Consider a transfer only after matching source and destination SKU",
            ),
            (
                "promotion_planning",
                "Should we increase promotion budget based on these outcomes?",
                "separate observed outcomes from incrementality and profitability",
            ),
            (
                "nationwide_logistics",
                "Should we redesign the logistics network from regional averages?",
                "require evidence before redesigning the network",
            ),
        )
        for domain, question, summary in cases:
            with self.subTest(domain=domain):
                evidence = [
                    Evidence(citation_id="C1", source_type="commerce_sql", source="Commerce SQL", content="Synthetic observations."),
                    Evidence(citation_id="L1", source_type="commerce_schema", source="Commerce schema", content="Decision dimensions are incomplete."),
                    Evidence(
                        citation_id="S1", source_type="document", source="Commerce Demo policy page 2",
                        content="OCR policy excerpt", metadata={
                            "evidence_class": "company_policy_reference",
                            "synthetic_company_policy": True,
                            "source_publisher": "Commerce Demo",
                            "ocr": {"engine": "tesseract"},
                            "source_notes_en": summary,
                        },
                    ),
                ]

                answer = _commerce_safe_fallback(domain, question, evidence, decision_request=True)

                self.assertIn(summary, answer)
                self.assertIn("not a verbatim excerpt", answer)
                self.assertIn("Check the original PDF page", answer)
                self.assertIn("[S1]", answer)
                self.assertNotIn("OCR text is not verified", answer)

    def test_commerce_fallback_combines_synthetic_policy_and_ranked_external_method(self):
        evidence = [
            Evidence(citation_id="C1", source_type="commerce_sql", source="Commerce SQL", content="Regional delivery summaries."),
            Evidence(citation_id="L1", source_type="commerce_schema", source="Commerce schema", content="No route, carrier, capacity, or promised SLA fields."),
            Evidence(
                citation_id="S1", source_type="document", source="Commerce Demo logistics policy",
                content="Trước khi thay đổi mạng lưới cần đối chiếu mức dịch vụ và chi phí vận chuyển.",
                metadata={
                    "evidence_class": "company_policy_reference", "synthetic_company_policy": True,
                    "ocr": {"engine": "tesseract"}, "text_extraction_method": "tesseract",
                },
            ),
            Evidence(
                citation_id="S2", source_type="document", source="Amazon supply-chain guide",
                content="Customer needs: balance expectations for fast shipping and on-time delivery with business priorities before selecting logistics options.",
                metadata={"evidence_class": "company_practice_reference", "source_publisher": "Amazon"},
            ),
        ]

        answer = _commerce_safe_fallback(
            "nationwide_logistics",
            "Should we redesign the network based on customer needs and cost?",
            evidence,
            decision_request=True,
        )

        self.assertIn("[S1]", answer)
        self.assertIn("[S2]", answer)
        self.assertIn("Amazon", answer)
        self.assertIn("A synthetic Commerce Demo policy was retrieved", answer)
        self.assertIn("not Commerce Demo policy", answer)
        self.assertIn("OCR text is not verified", answer)
        self.assertNotIn("đối chiếu mức dịch vụ và chi phí vận chuyển", answer)
        self.assertNotIn("Customer needs: balance expectations", answer)

    def test_commerce_safe_fallback_uses_named_platform_rule_before_generic_company_example(self):
        evidence = [
            Evidence(citation_id="C1", source_type="commerce_sql", source="Commerce SQL", content="Category aggregates."),
            Evidence(citation_id="S1", source_type="document", source="Shopee inventory guide",
                     content="Enable low-stock notifications and review SKU inventory before replenishment.",
                     metadata={"evidence_class": "platform_operating_rule", "source_publisher": "Shopee Uni"}),
            Evidence(citation_id="S2", source_type="document", source="Walmart example",
                     content="Use item-level views to review stock.",
                     metadata={"evidence_class": "company_practice_reference", "source_publisher": "Walmart"}),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "For a Shopee seller, what should we do for a low-stock alert?",
            evidence,
        )

        self.assertIn("For the named platform, use the cited SKU-level alert workflow", answer)
        self.assertIn("Shopee Uni", answer)
        self.assertIn("applies only within the named platform", answer)
        self.assertIn("[S1]", answer)
        self.assertNotIn("Walmart", answer)

    def test_commerce_safe_fallback_localizes_platform_source_caveat(self):
        evidence = [
            Evidence(citation_id="C1", source_type="commerce_sql", source="Commerce SQL", content="Category aggregates."),
            Evidence(citation_id="S1", source_type="document", source="Shopee inventory guide",
                     content="Use the Seller Center low-stock alert to review SKU inventory.",
                     metadata={"evidence_class": "platform_operating_rule", "source_publisher": "Shopee Uni",
                               "reference_applicability": "Historical 2019 interface labels and thresholds are not current policy."}),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation", "Với Shop Shopee, nên kiểm tra tồn kho thấp thế nào?", evidence,
        )

        self.assertIn("Đây là hướng dẫn lịch sử", answer)
        self.assertIn("Tài liệu không xác nhận trạng thái tồn kho hiện tại", answer)
        self.assertNotIn("Historical", answer)

    def test_commerce_safe_fallback_preserves_question_relevant_sql_observations(self):
        examples = (
            (
                "inventory_allocation",
                "Which category has the most stockout products? Should we transfer stock?",
                "inventory_latest_by_category",
                [{"category": "Streetwear", "snapshot_date": "2022-12-31", "stockout_products": 134},
                 {"category": "Outdoor", "snapshot_date": "2022-12-31", "stockout_products": 95}],
                ("Streetwear=134", "Outdoor=95", "Highest: Streetwear=134"),
            ),
            (
                "promotion_planning",
                "Compare promotion-tagged orders in 2020-2022 and decide whether to increase budget.",
                "promotion_by_year",
                [{"year": 2020, "used_promotion": True, "delivered_orders": 8, "net_sales": 200.0},
                 {"year": 2021, "used_promotion": True, "delivered_orders": 9, "net_sales": 220.0},
                 {"year": 2022, "used_promotion": True, "delivered_orders": 10, "net_sales": 250.5},
                 {"year": 2022, "used_promotion": False, "delivered_orders": 20, "net_sales": 400.0}],
                ("Year 2020 tagged: delivered orders=8; net sales=200",
                 "Year 2021 tagged: delivered orders=9; net sales=220",
                 "Year 2022 tagged: delivered orders=10; net sales=250.5",
                 "Year 2022 untagged", "not causal"),
            ),
            (
                "nationwide_logistics",
                "In 2022 which region has the highest average transit time? Should the network change?",
                "logistics_by_year_region",
                [{"year": 2022, "region": "East", "avg_transit_days": 4.52},
                 {"year": 2022, "region": "West", "avg_transit_days": 4.51}],
                ("Year 2022 East: avg_transit_days=4.52", "Year 2022 West: avg_transit_days=4.51", "East=4.52 days"),
            ),
        )
        for domain, question, observation, rows, expected in examples:
            evidence = [Evidence(
                citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
                content=f"{observation} aggregate observations: {json.dumps(rows)}",
            )]
            with self.subTest(domain=domain):
                answer = _commerce_safe_fallback(domain, question, evidence)
                for fragment in expected:
                    self.assertIn(fragment, answer)
                self.assertIn("[C1]", answer)

    def test_inventory_fallback_preserves_dynamic_sql_category_aliases(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Question-specific inventory SQL",
                content=("question_specific_query question-specific SQL observations: " + json.dumps([
                    {"group_label": "Streetwear", "stockout_count": 134, "overstock_count": 162},
                    {"group_label": "Outdoor", "stockout_count": 95, "overstock_count": 113},
                ])),
                metadata={"sql_query": "SELECT category AS group_label, COUNT(*) FILTER (WHERE stockout_flag) AS stockout_count FROM commerce.inventory WHERE snapshot_date = '2022-12-31' GROUP BY category"},
            ),
            Evidence(
                citation_id="C2", source_type="commerce_sql", source="Latest inventory overlap",
                content=("inventory_latest_flag_overlap aggregate observations: " + json.dumps([
                    {"snapshot_date": "2022-12-31", "both_flagged_rows": 232},
                ])),
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Synthetic inventory policy",
                content="OCR policy source",
                metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True,
                          "text_extraction_method": "tesseract",
                          "source_notes": "Đối chiếu SKU, tồn khả dụng, nhu cầu, lead time và chi phí."},
            ),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "Trong snapshot tồn kho mới nhất, nhóm hàng nào có nhiều sản phẩm bị gắn cờ stockout nhất? Có nên chuyển hàng từ nhóm overstock sang không?",
            evidence,
        )

        self.assertIn("Streetwear=134", answer)
        self.assertIn("Outdoor=95", answer)
        self.assertIn("snapshot 2022-12-31", answer)
        self.assertIn("232", answer)
        self.assertIn("Chưa điều chuyển tồn kho", answer)
        self.assertIn("[C1]", answer)

    def test_commerce_promotion_fallback_localizes_and_omits_unrequested_columns(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce promotion SQL",
            content=("promotions_by_year aggregate observations: " + json.dumps([
                {"year": 2020, "used_promotion": True, "delivered_orders": 10305, "units": 49756,
                 "net_sales": 235597280.59, "discounts": 39488236.4, "catalog_cogs": 256788462.46,
                 "merchandise_gross_margin_proxy": -0.08},
            ])),
        )]

        answer = _commerce_safe_fallback(
            "promotion_planning",
            "Đơn hàng delivered gắn khuyến mãi thay đổi thế nào? So sánh delivered orders, units, net sales và discounts.",
            evidence,
        )

        for fragment in (
            "Năm 2020 gắn khuyến mãi", "đơn hàng đã giao=10.305", "số lượng bán=49.756",
            "doanh thu thuần=235.597.280,59", "mức giảm giá=39.488.236,4", "không chứng minh quan hệ nhân quả",
        ):
            self.assertIn(fragment, answer)
        self.assertNotIn("catalog_cogs", answer)
        self.assertNotIn("gross-margin proxy", answer)
        self.assertIn("[C1]", answer)

    def test_promotion_outcome_fallback_handles_hyphenated_metrics_and_negated_roi(self):
        question = (
            "Compare campaign performance using available sales and gross-profit proxy. "
            "Do not infer incrementality or ROI; what evidence is needed before reallocating budget?"
        )
        self.assertFalse(_asks_for_unavailable_promotion_roi(question))
        self.assertTrue(_asks_for_unavailable_promotion_roi("Which campaign has the highest ROI?"))

        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce promotion SQL",
            content=("promotions_by_year aggregate observations: " + json.dumps([{
                "year": 2022, "used_promotion": True, "delivered_orders": 10173,
                "units": 48768, "net_sales": 245344841.2, "discounts": 41728464.79,
                "catalog_cogs": 278908639.37, "merchandise_gross_profit_proxy": -33563798.17,
                "merchandise_gross_margin_proxy": -0.1368,
            }])),
            metadata={"commerce_domain": "promotion_planning"},
        )]

        answer = _commerce_question_safe_fallback(question, evidence, decision_request=True)

        self.assertIn("Net Sales", answer)
        self.assertIn("Merchandise Gross Profit Proxy", answer)
        self.assertNotIn("Catalog Cogs", answer)
        self.assertNotIn("Discounts", answer)
        self.assertNotIn("Delivered Orders", answer)
        self.assertNotIn("Gross Margin Proxy", answer)
        self.assertIn("[C1]", answer)

    def test_commerce_safe_fallback_does_not_substitute_stockout_for_low_stock(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce inventory SQL",
            content=("inventory_latest_by_category aggregate observations: "
                     '[{"category":"Streetwear","stockout_products":134,"overstock_products":40}]'),
        )]

        answer = _commerce_safe_fallback(
            "inventory_allocation", "What is the low-stock alert count by category?", evidence,
        )

        self.assertNotIn("Streetwear=134", answer)
        self.assertIn("Category aggregates", answer)
        self.assertIn("[C1]", answer)

    def test_commerce_safe_fallback_preserves_requested_inventory_years(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce inventory SQL",
            content=("inventory_by_year aggregate observations: " + json.dumps([
                {"year": 2020, "avg_fill_rate": 0.9656, "stockout_snapshots": 3795},
                {"year": 2021, "avg_fill_rate": 0.9619, "stockout_snapshots": 3788},
                {"year": 2022, "avg_fill_rate": 0.9635, "stockout_snapshots": 3490},
            ])),
        )]

        answer = _commerce_safe_fallback(
            "inventory_allocation", "Tình trạng availability thay đổi trong 2020–2022 thế nào?", evidence,
        )

        for fragment in ("Năm 2020", "Fill rate TB=96,56%", "Năm 2021", "Fill rate TB=96,19%",
                         "Năm 2022", "Fill rate TB=96,35%", "[C1]"):
            self.assertIn(fragment, answer)
        self.assertNotIn("0.9656", answer)
        self.assertNotIn("service target", answer)

    def test_service_target_fallback_explains_non_monotonic_fill_rate_and_snapshot_denominator(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce inventory SQL",
            content=("inventory_by_year aggregate observations: " + json.dumps([
                {"year": 2020, "avg_fill_rate": 0.9656, "stockout_snapshots": 3795, "sku_snapshots": 5686},
                {"year": 2021, "avg_fill_rate": 0.9619, "stockout_snapshots": 3788, "sku_snapshots": 5609},
                {"year": 2022, "avg_fill_rate": 0.9635, "stockout_snapshots": 3490, "sku_snapshots": 5232},
            ])),
        )]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "Trong từng năm 2020–2022, fill rate thay đổi thế nào; có thể đặt service target mới không?",
            evidence,
        )

        self.assertIn("Fill rate không đơn điệu (giảm 2020–2021; tăng 2021–2022)", answer)
        self.assertIn("Số snapshot có cờ stockout và tổng snapshot đều giảm", answer)
        self.assertIn("quy mô snapshot cũng thay đổi", answer)
        self.assertIn("Dữ liệu không có service-level target đã được phê duyệt", answer)
        self.assertIn("[C1]. Số snapshot", answer)
        self.assertIn("[C1]. Dữ liệu", answer)
        self.assertIn("[C1]", answer)

    def test_dynamic_service_target_fallback_formats_trend_citations_and_sentences(self):
        rows = [
            {"year": 2020, "avg_fill_rate": "0.9656", "stockout_snapshots": 3795, "total_snapshots": 5686},
            {"year": 2021, "avg_fill_rate": "0.9619", "stockout_snapshots": 3788, "total_snapshots": 5609},
            {"year": 2022, "avg_fill_rate": "0.9635", "stockout_snapshots": 3490, "total_snapshots": 5232},
        ]
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Inventory query",
                content=f"question_specific_query question-specific SQL observations: {json.dumps(rows)}",
                metadata={"commerce_domain": "inventory_allocation", "commerce_observations": rows},
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Schema limits",
                content="No approved service-level target is available.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Synthetic Demo policy",
                content="OCR policy excerpt", metadata={
                    "evidence_class": "company_policy_reference", "synthetic_company_policy": True,
                    "document_id": "CD-POL-INV-001", "page_number": 2,
                    "text_extraction_method": "tesseract",
                },
            ),
        ]

        answer = _commerce_question_safe_fallback(
            "Trong từng năm 2020–2022, fill rate thay đổi thế nào; có thể đặt service target mới không?",
            evidence,
            decision_request=True,
        )

        self.assertIn("[C1]. Fill rate không đơn điệu", answer)
        self.assertIn("[C1]. Số snapshot", answer)
        self.assertIn("[C1]. Kết luận:", answer)
        self.assertNotIn("[[C1]]", answer)

    def test_commerce_inventory_transfer_question_does_not_add_unrequested_availability_history(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Commerce inventory SQL",
                content=("inventory_by_year aggregate observations: " + json.dumps([
                    {"year": 2020, "avg_fill_rate": 0.9656, "stockout_snapshots": 3795},
                    {"year": 2021, "avg_fill_rate": 0.9619, "stockout_snapshots": 3788},
                    {"year": 2022, "avg_fill_rate": 0.9635, "stockout_snapshots": 3490},
                ])),
            ),
            Evidence(
                citation_id="C2", source_type="commerce_sql", source="Commerce category SQL",
                content=("inventory_latest_by_category aggregate observations: " + json.dumps([
                    {"category": "Outdoor", "stockout_products": 95, "overstock_products": 113},
                ])),
            ),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation",
            "Dựa trên tình trạng tồn kho mới nhất, có nên điều chuyển hàng từ nhóm overstock sang nhóm stockout không?",
            evidence,
        )

        self.assertIn("Chưa điều chuyển tồn kho", answer)
        self.assertNotIn("FY2020", answer)
        self.assertNotIn("service target", answer)
        self.assertNotIn("Không thể đặt", answer)

    def test_commerce_service_target_fallback_does_not_switch_to_stock_transfer(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce inventory SQL",
            content=("inventory_by_year aggregate observations: " + json.dumps([
                {"year": 2022, "avg_fill_rate": 0.9635, "stockout_snapshots": 3490},
            ])),
        ), Evidence(
            citation_id="L1", source_type="commerce_schema", source="Commerce schema coverage",
            content="The supplied data has no supplier lead time, demand forecast, ordering cost, holding cost, warehouse location, or approved service-level target.",
        )]

        answer = _commerce_safe_fallback(
            "inventory_allocation", "Tình trạng availability thay đổi thế nào, có thể đặt service target mới không?", evidence,
        )

        self.assertIn("Chưa thể đặt service target mới", answer)
        self.assertIn("mục tiêu đã được phê duyệt", answer)
        self.assertIn("[L1]", answer)
        self.assertNotIn("điều chuyển tồn kho", answer)

    def test_commerce_safe_fallback_returns_only_requested_campaign_winner(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce campaign SQL",
            content=("promotions_by_campaign aggregate observations: " + json.dumps([
                {"year": 2022, "campaign": "Spring Sale 2022", "campaign_start": "2022-03-01",
                 "campaign_end": "2022-03-31", "net_item_sales": 90345105.91, "delivered_orders": 3473},
                {"year": 2022, "campaign": "Fall Launch 2022", "campaign_start": "2022-09-01",
                 "campaign_end": "2022-09-30", "net_item_sales": 55424932.90, "delivered_orders": 1899},
            ])),
        )]

        answer = _commerce_safe_fallback(
            "promotion_planning", "Trong các campaign 2022, campaign nào có net sales cao nhất?", evidence,
        )

        self.assertIn("Spring Sale 2022", answer)
        self.assertIn("doanh thu thuần=90.345.105,91", answer)
        self.assertNotIn("net_item_sales", answer)
        self.assertNotIn("Fall Launch 2022", answer)
        self.assertIn("doanh thu thuần mặt hàng gắn tag trong thời gian chạy", answer)
        self.assertNotIn("delivered_orders", answer)
        self.assertNotIn("merchandise_gross_profit_proxy", answer)
        self.assertIn("[C1]", answer)

    def test_commerce_campaign_fallback_respects_named_campaign_scope(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce campaign SQL",
            content=("promotions_by_campaign aggregate observations: " + json.dumps([
                {"year": 2020, "campaign": "Spring Sale 2020", "net_item_sales": 90175249.90},
                {"year": 2021, "campaign": "Spring Sale 2021", "net_item_sales": 81474493.06},
                {"year": 2022, "campaign": "Spring Sale 2022", "net_item_sales": 90345105.91},
                {"year": 2022, "campaign": "Fall Launch 2022", "net_item_sales": 55424932.90},
            ])),
        )]

        across_years = _commerce_safe_fallback(
            "promotion_planning",
            "Should we increase the Spring Sale promotion budget based on the available campaign evidence?",
            evidence,
        )
        self.assertIn("Spring Sale 2020", across_years)
        self.assertIn("Spring Sale 2021", across_years)
        self.assertIn("Spring Sale 2022", across_years)
        self.assertNotIn("Fall Launch", across_years)

        one_year = _commerce_safe_fallback(
            "promotion_planning", "What were Spring Sale 2022 campaign outcomes?", evidence,
        )
        self.assertIn("Spring Sale 2022", one_year)
        self.assertNotIn("Spring Sale 2020", one_year)
        self.assertNotIn("Fall Launch", one_year)

    def test_descriptive_commerce_answer_gate_flags_unsolicited_action_advice(self):
        self.assertTrue(_has_unsolicited_commerce_recommendation(
            "Spring Sale ranked first. Recommended next move: run a holdout test [C1]."
        ))
        self.assertFalse(_has_unsolicited_commerce_recommendation(
            "Spring Sale ranked first by net sales; this is descriptive, not causal [C1]."
        ))

    def test_service_target_absence_requires_schema_limitation_citation(self):
        evidence = [Evidence(
            citation_id="L1", source_type="commerce_schema", source="Commerce schema",
            content="The supplied data has no approved service-level target.",
        )]
        question = "Can we set a new service target from historical fill rate?"
        self.assertTrue(_commerce_schema_gap_citation_failure(
            "Historical observations do not establish an approved service target [C1].", evidence, question,
        ))
        self.assertFalse(_commerce_schema_gap_citation_failure(
            "Historical observations do not establish an approved service target [L1].", evidence, question,
        ))

    def test_descriptive_campaign_question_keeps_hybrid_retrieval_but_rejects_unsolicited_advice(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "promotion_planning", "domain_label": "Promotion planning",
            "source_tables": ["commerce.promotions", "commerce.order_items"],
            "observations": {"promotions_by_campaign": [
                {"year": 2022, "campaign": "Spring Sale", "campaign_start": "2022-03-01",
                 "campaign_end": "2022-03-31", "net_item_sales": 90, "units": 12},
                {"year": 2022, "campaign": "Fall Launch", "campaign_start": "2022-09-01",
                 "campaign_end": "2022-09-30", "net_item_sales": 50, "units": 8},
            ]},
            "limitations": ["The synthetic campaign data has no randomized holdout."],
            "dataset_note": "Synthetic competition dataset.",
        }
        knowledge, llm = Mock(), Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="Campaign measurement method",
            content="Use a holdout to estimate incremental campaign outcomes.", metadata={
                "evidence_class": "management_cookbook_reference", "source_publisher": "IAB",
            },
        )])
        llm.generate.side_effect = [
            "Spring Sale had the highest net sales [C1]. Recommended next move: run a holdout test [C1].",
            "Spring Sale had the highest net sales [C1]. Recommended next move: run an experiment [C1].",
        ]
        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Trong các campaign 2022, campaign nào có net sales cao nhất?",
            metadata={"business_decision_domain": "promotion_planning", "commerce_decision_support": True, "role": "analyst"},
        ))

        knowledge.run.assert_called_once()
        self.assertTrue(result.metadata["decision_fallback_used"])
        self.assertIn("Spring Sale", result.answer)
        self.assertNotIn("holdout", result.answer.casefold())
        self.assertNotIn("Fall Launch", result.answer)
        self.assertNotIn("units=", result.answer)
        self.assertNotIn("recommend", result.answer.casefold())

    def test_promotion_fallback_without_applicable_reference_does_not_invent_experiment_method(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce promotion SQL",
            content=("promotions_by_year aggregate observations: " + json.dumps([
                {"year": 2022, "used_promotion": True, "net_sales": 245344841.20},
            ])),
        )]
        answer = _commerce_safe_fallback(
            "promotion_planning", "Should we increase campaign budget?", evidence,
        )
        self.assertIn("not enough evidence to expand", answer)
        self.assertNotIn("holdout", answer.casefold())
        self.assertNotIn("experiment", answer.casefold())

    def test_commerce_service_target_answer_retries_uncited_schema_gap_then_falls_back_with_l_citation(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "observations": {"inventory_by_year": [
                {"year": 2020, "avg_fill_rate": 0.9656},
                {"year": 2021, "avg_fill_rate": 0.9619},
                {"year": 2022, "avg_fill_rate": 0.9635},
            ]},
            "limitations": [
                "The supplied data has no supplier lead time, demand forecast, ordering cost, holding cost, warehouse location, or approved service-level target.",
            ],
            "dataset_note": "Synthetic competition dataset.",
        }
        knowledge, llm = Mock(), Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[])
        unsupported = (
            "Fill rate không đơn điệu: 0.9656, 0.9619, 0.9635 [C1]. "
            "Dữ liệu không có service-level target đã được phê duyệt [L1]."
        )
        llm.generate.side_effect = [unsupported, unsupported]
        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Tình trạng availability thay đổi trong 2020–2022 thế nào, có thể đặt service target mới không?",
            metadata={"business_decision_domain": "inventory_allocation", "role": "analyst"},
        ))

        self.assertEqual(llm.generate.call_count, 2)
        self.assertTrue(result.metadata["decision_fallback_used"])
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertIn("Fill rate TB=96,56%", result.answer)
        self.assertIn("Dữ liệu không có service-level target đã được phê duyệt [L1]", result.answer)
        self.assertIn("ratio multiplied by 100", llm.generate.call_args_list[1].args[0])

    def test_commerce_safe_fallback_can_rank_campaigns_by_gross_profit_proxy(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce campaign SQL",
            content=("promotions_by_campaign aggregate observations: " + json.dumps([
                {"year": 2022, "campaign": "Largest Sales", "campaign_start": "2022-03-01",
                 "campaign_end": "2022-03-31", "net_item_sales": 1000,
                 "merchandise_gross_profit_proxy": -20, "delivered_orders": 10},
                {"year": 2022, "campaign": "Higher Proxy Profit", "campaign_start": "2022-06-01",
                 "campaign_end": "2022-06-30", "net_item_sales": 700,
                 "merchandise_gross_profit_proxy": 35, "delivered_orders": 8},
            ])),
        )]

        answer = _commerce_safe_fallback(
            "promotion_planning", "Chiến dịch nào có lãi gộp ước tính cao nhất?", evidence,
        )

        self.assertIn("Higher Proxy Profit", answer)
        self.assertNotIn("Largest Sales", answer)
        self.assertIn("proxy lãi gộp hàng hóa=35", answer)
        self.assertIn("không phải biên lợi nhuận đóng góp, ROI", answer)
        self.assertIn("lợi nhuận tăng thêm do chiến dịch", answer)
        self.assertIn("[C1]", answer)

    def test_campaign_winner_fallback_uses_a_localized_metric_label(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce campaign SQL",
            content="promotions_by_campaign aggregate observations: " + json.dumps([
                {"year": 2022, "campaign": "Spring Sale 2022", "campaign_start": "2022-03-18",
                 "campaign_end": "2022-04-17", "net_item_sales": 90345105.91},
            ]),
        )]

        answer = _commerce_safe_fallback(
            "promotion_planning",
            "Trong campaign 2022 nào doanh thu thuần cao nhất?",
            evidence,
            decision_request=False,
        )

        self.assertIn("doanh thu thuần=90.345.105,91", answer)
        self.assertNotIn("net_item_sales", answer)

    def test_commerce_safe_fallback_compares_winners_for_multiple_campaign_metrics(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce campaign SQL",
            content=("promotions_by_campaign aggregate observations: " + json.dumps([
                {"year": 2021, "campaign": "Old Winner", "net_item_sales": 9000,
                 "merchandise_gross_profit_proxy": 900},
                {"year": 2022, "campaign": "Largest Sales", "net_item_sales": 1000,
                 "merchandise_gross_profit_proxy": -20},
                {"year": 2022, "campaign": "Higher Proxy Profit", "net_item_sales": 700,
                 "merchandise_gross_profit_proxy": 35},
            ])),
        )]

        questions = (
            "Trong 2022, campaign nào cao nhất về net sales và campaign nào có proxy lãi gộp cao nhất? Hai bên có cùng campaign không?",
            "In 2022, does the campaign with the highest net sales also have the highest gross-profit proxy?",
        )
        for question in questions:
            with self.subTest(question=question):
                answer = _commerce_safe_fallback("promotion_planning", question, evidence)

                self.assertIn("Largest Sales", answer)
                self.assertIn("1000", answer)
                self.assertIn("Higher Proxy Profit", answer)
                self.assertIn("35", answer)
                self.assertIn("different campaigns" if question.startswith("In 2022") else "khác nhau", answer.casefold())
                self.assertNotIn("Old Winner", answer)
                self.assertIn("[C1]", answer)

        comparison = _commerce_safe_fallback(
            "promotion_planning", "Compare net sales and gross-profit proxy for campaigns in 2022.", evidence,
        )
        self.assertIn("Largest Sales: campaign-window tagged net item sales=1,000", comparison)
        self.assertIn("merchandise gross-profit proxy=-20", comparison)
        self.assertIn("Higher Proxy Profit", comparison)
        self.assertNotIn("Old Winner", comparison)
        self.assertIn("[C1]", comparison)

    def test_commerce_safe_fallback_keeps_year_and_both_requested_logistics_metrics(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce logistics SQL",
            content=("logistics_by_year_region aggregate observations: " + json.dumps([
                {"year": 2020, "region": "East", "avg_transit_days": 4.50, "avg_shipping_fee": 4.27},
                {"year": 2021, "region": "East", "avg_transit_days": 4.51, "avg_shipping_fee": 4.07},
                {"year": 2022, "region": "East", "avg_transit_days": 4.52, "avg_shipping_fee": 3.98},
            ])),
        )]

        answer = _commerce_safe_fallback(
            "nationwide_logistics", "Trong 2020–2022, shipping fee và transit time theo vùng thay đổi ra sao?", evidence,
        )

        for fragment in ("East", "Năm 2020 4.5 → Năm 2022 4.52 (tăng)",
                         "Năm 2020 4.27 → Năm 2022 3.98 (giảm)",
                         "không cho biết nguyên nhân", "[C1]"):
            self.assertIn(fragment, answer)
        self.assertNotIn("Năm 2021", answer)
        self.assertNotIn("Highest average transit time", answer)
        self.assertIsNone(_report_validation_failure(answer, evidence, {"C1"},
                                                      "Trong 2020–2022, shipping fee và transit time theo vùng thay đổi ra sao?"))

    def test_commerce_roi_question_does_not_substitute_tagged_sales(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce promotion SQL",
            content=("promotions_by_year aggregate observations: " + json.dumps([
                {"year": 2022, "used_promotion": True, "net_sales": 245344841.20},
                {"year": 2022, "used_promotion": False, "net_sales": 615242495.15},
            ])),
        )]

        answer = _commerce_safe_fallback(
            "promotion_planning", "Kênh khuyến mãi nào có ROI cao nhất để dồn ngân sách?", evidence,
        )

        self.assertIn("Không thể tính ROI theo kênh/chiến dịch", answer)
        self.assertIn("chi phí chiến dịch", answer)
        self.assertIn("proxy lãi gộp hàng hóa", answer)
        self.assertNotIn("net_sales=245344841.2", answer)
        self.assertIn("[C1]", answer)

    def test_commerce_roi_request_skips_generated_sql_when_campaign_cost_is_unavailable(self):
        analytics = object.__new__(SQLAnalyticsAgent)
        analytics.commerce_decision_snapshot = Mock(return_value={
            "domain": "promotion_planning", "domain_label": "Promotion planning",
            "source_tables": ["commerce.orders", "commerce.order_items", "commerce.promotions"],
            "observations": {"promotions_by_year": [{"year": 2022, "net_sales": 200.0, "total_discount": 10.0}]},
            "limitations": ["Campaign spend and campaign-attributed traffic are unavailable; ROI cannot be established."],
            "dataset_note": "Synthetic competition data.",
        })
        analytics.commerce_question_observations = Mock()
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="Promotion measurement guide",
            content="Estimate incremental outcomes with a valid holdout before changing campaign budgets.",
            metadata={"evidence_class": "management_cookbook_reference", "source_publisher": "Example Publisher"},
        )])
        llm = Mock()

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Kênh khuyến mãi nào có ROI cao nhất để dồn ngân sách?",
            metadata={"business_decision_domain": "promotion_planning", "role": "analyst"},
        ))

        analytics.commerce_decision_snapshot.assert_called_once_with("promotion_planning")
        analytics.commerce_question_observations.assert_not_called()
        llm.generate.assert_not_called()
        self.assertEqual(result.metadata["question_sql_fallback"], "unsupported_measure")
        self.assertEqual(result.metadata["answer_fallback_reason"], "unsupported_measure")
        self.assertTrue(result.metadata["decision_fallback_used"])
        self.assertIn("Không thể tính ROI", result.answer)
        self.assertIn("campaign", result.answer.casefold())
        self.assertIn("[C1]", result.answer)
        self.assertIn("[L1]", result.answer)
        self.assertIn("[S1]", result.answer)

    def test_commerce_logistics_decision_uses_latest_year_without_unasked_ranking(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce logistics SQL",
            content=("logistics_by_year_region aggregate observations: " + json.dumps([
                {"year": 2020, "region": "East", "avg_transit_days": 4.50},
                {"year": 2021, "region": "East", "avg_transit_days": 4.51},
                {"year": 2022, "region": "East", "avg_transit_days": 4.52},
            ])),
        )]

        answer = _commerce_safe_fallback(
            "nationwide_logistics", "Should delivery capacity be moved between regions?", evidence,
        )

        self.assertIn("Year 2022 East", answer)
        self.assertNotIn("Year 2020", answer)
        self.assertNotIn("Highest average transit time", answer)

    def test_commerce_logistics_fallback_ranks_requested_delivery_delay_signal(self):
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce logistics SQL",
            content=("logistics_by_year_region aggregate observations: " + json.dumps([
                {"year": 2022, "region": "Central", "avg_transit_days": 4.51},
                {"year": 2022, "region": "East", "avg_transit_days": 4.52},
                {"year": 2022, "region": "West", "avg_transit_days": 4.51},
            ])),
        )]

        answer = _commerce_safe_fallback(
            "nationwide_logistics",
            "Which region shows the strongest delivery-delay signal in the latest available data?",
            evidence,
            decision_request=True,
        )

        self.assertIn("Highest average transit time in 2022: East=4.52 days", answer)
        self.assertIn("[C1]", answer)
        self.assertNotIn("unacceptable", answer.casefold())

    def test_commerce_report_uses_cited_safe_fallback_after_unsupported_network_actions(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "nationwide_logistics", "domain_label": "Nationwide logistics",
            "source_tables": ["commerce.shipments"],
            "observations": {"logistics_by_year_region": [{"year": 2022, "region": "West", "avg_transit_days": 4.5}]},
            "limitations": ["No carrier, route capacity, promised SLA, or controllable transport-cost breakdown."],
            "dataset_note": "Synthetic competition data.",
        }
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="Amazon shareholder letter",
            content="Amazon describes regional fulfillment in its network.",
            metadata={"evidence_class": "company_practice_reference", "source_publisher": "Amazon.com, Inc."},
        )])
        llm = Mock()
        llm.generate.side_effect = [
            "Add a warehouse in West and switch carriers to reduce delivery time [C1][S1].",
            "Collect warehouse processing time and regional coverage before deciding [L1][S1].",
        ]

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Should we change the nationwide delivery network?",
            metadata={"business_decision_domain": "nationwide_logistics", "role": "operations"},
        ))

        self.assertTrue(result.metadata["decision_fallback_used"])
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertIn("Do not redesign the delivery network", result.answer)
        self.assertIn("[C1]", result.answer)
        self.assertIn("[S1]", result.answer)

    def test_logistics_fallback_uses_catalog_note_without_repeating_ocr_as_advice(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
                content='logistics_by_year_region question-specific SQL observations: [{"year":2022,"region":"East","avg_transit_days":4.52}]',
                metadata={"commerce_domain": "nationwide_logistics", "commerce_observations": [
                    {"year": 2022, "region": "East", "avg_transit_days": 4.52},
                ]},
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Commerce schema",
                content="Route and carrier dimensions are unavailable.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Commerce Demo policy page 1",
                content="OCR policy excerpt", metadata={
                    "evidence_class": "company_policy_reference",
                    "synthetic_company_policy": True,
                    "source_publisher": "Commerce Demo",
                    "ocr": {"engine": "tesseract"},
                    "source_notes": (
                        "Yêu cầu bằng chứng trước khi thiết kế lại mạng lưới. "
                        "Không đề xuất đổi carrier chỉ từ trung bình vùng."
                    ),
                },
            ),
        ]

        answer = _commerce_safe_fallback(
            "nationwide_logistics", "Có nên thiết kế lại mạng lưới giao hàng?", evidence,
        )

        self.assertIn("Tóm tắt biên mục", answer)
        self.assertIn("Yêu cầu bằng chứng trước khi thiết kế lại mạng lưới", answer)
        self.assertIn("Không đề xuất đổi carrier chỉ từ trung bình vùng", answer)
        self.assertIn("đối chiếu trang PDF gốc", answer)
        self.assertFalse(_has_unsupported_logistics_intervention(answer, evidence))

    def test_logistics_intervention_guard_allows_refusal_but_rejects_specific_actions(self):
        self.assertTrue(_has_unsupported_logistics_intervention(
            "Add a warehouse in West or change carriers to reduce delivery time."
        ))
        self.assertFalse(_has_unsupported_logistics_intervention(
            "Do not add a warehouse or change carriers from regional averages alone."
        ))
        self.assertFalse(_has_unsupported_logistics_intervention(
            "Bổ sung điểm đi/đến, hãng vận chuyển, năng lực tuyến và chi phí trước khi so sánh."
        ))
        self.assertTrue(_has_unprovided_logistics_fields(
            "Thu thập thời gian xử lý tại kho và độ phủ vùng."
        ))
        self.assertFalse(_has_unprovided_logistics_fields(
            "Thu thập origin/destination, carrier, service type, SLA, route capacity, and cost."
        ))

    def test_logistics_intervention_guard_ignores_only_a_cited_verbatim_source_quote(self):
        answer = "Chưa chuyển năng lực vùng. Shopify mô tả: “Move fulfillment to the nearest location in the network.” [S1]"
        source = Evidence(
            citation_id="S1", source_type="document", source="Shopify routing guide",
            content="Move fulfillment to the nearest location in the network.",
        )
        self.assertFalse(_has_unsupported_logistics_intervention(answer, [source]))
        self.assertTrue(_has_unsupported_logistics_intervention(answer))
        self.assertTrue(_has_unsupported_logistics_intervention(answer.replace("[S1]", "[C1]"), [source]))

    def test_logistics_recommendation_must_explain_the_cited_source_method(self):
        reference = Evidence(
            citation_id="S1", source_type="document", source="Shopify Smart Order Routing",
            content="Prioritize inventory availability, the closest location, and minimizing split fulfillments.",
            metadata={"evidence_class": "company_practice_reference"},
        )
        vague = "Chưa thiết kế lại mạng lưới; hãy bổ sung dữ liệu tuyến và chi phí [L1][S1]."
        grounded = "Shopify mô tả ưu tiên tồn kho khả dụng, vị trí gần nhất và giảm tách đơn; hãy kiểm tra các tiêu chí này khi có dữ liệu tuyến [S1][L1]."

        self.assertTrue(_omits_cited_logistics_method(vague, [reference]))
        self.assertFalse(_omits_cited_logistics_method(grounded, [reference]))

    def test_logistics_safe_fallback_quotes_the_decision_method_not_the_intro(self):
        evidence = [
            Evidence(citation_id="C1", source_type="commerce_sql", source="SQL", content="FY2022 East 4.52 days."),
            Evidence(citation_id="L1", source_type="commerce_schema", source="Schema", content="No route or carrier fields."),
            Evidence(
                citation_id="S1", source_type="document", source="Shopify routing guide",
                content=("With thousands of orders, manual routing is difficult. "
                         "Prioritize inventory availability, the closest location, and minimizing split fulfillments."),
                metadata={"evidence_class": "company_practice_reference", "source_publisher": "Shopify"},
            ),
        ]

        answer = _commerce_safe_fallback(
            "nationwide_logistics", "Có nên đổi mạng lưới giao hàng?", evidence, decision_request=True,
        )

        self.assertIn("closest location", answer)
        self.assertIn("[S1]", answer)

    def test_commerce_fallback_does_not_quote_unverified_ocr_reference_text(self):
        malformed_ocr = "Bổsung kho hàng sớm cho biết SKU sắp hết hàng."
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="SQL",
                content="Category aggregates do not identify SKU/location mismatches.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Shopee Uni inventory guide",
                content=malformed_ocr,
                metadata={
                    "evidence_class": "company_practice_reference",
                    "source_publisher": "Shopee Uni",
                    "ocr": {"engine": "tesseract"},
                    "text_extraction_method": "pymupdf+tesseract",
                },
            ),
        ]

        answer = _commerce_safe_fallback(
            "inventory_allocation", "Có nên điều chuyển hàng theo cảnh báo tồn kho?",
            evidence, decision_request=True,
        )

        self.assertIn("Shopee Uni", answer)
        self.assertIn("OCR chưa được xác minh", answer)
        self.assertIn("trang PDF gốc", answer)
        self.assertIn("[S1]", answer)
        self.assertNotIn(malformed_ocr, answer)

    def test_commerce_promotion_expansion_rejects_invented_pilot_duration_and_threshold(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "promotion_planning", "domain_label": "Promotion planning",
            "source_tables": ["commerce.order_items"],
            "observations": {"promotion_by_year": [{"year": 2022, "used_promotion": True,
                                                       "delivered_orders": 10, "net_sales": 200}]},
            "limitations": ["No randomized holdout or campaign contribution margin."],
            "dataset_note": "Synthetic competition data.",
        }
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="DoorDash Ads incrementality guide",
            content=("Compare treatment and control groups using holdout tests to measure incremental sales; "
                     "campaign cost is separately required to assess contribution margin."),
            metadata={"evidence_class": "company_practice_reference", "source_publisher": "DoorDash Ads"},
        )])
        unsupported = (
            "Run a pilot for 3 months. If promotion orders achieve at least 5% higher sales per order, "
            "then expand the campaign [C1]. Walmart describes its own pricing practices as an example, "
            "not Commerce Demo policy [S1]."
        )
        llm = Mock()
        llm.generate.side_effect = [unsupported, unsupported]

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="How do promotion-tagged orders compare, and is that enough evidence to expand promotions?",
            metadata={"business_decision_domain": "promotion_planning", "role": "analyst"},
        ))

        self.assertEqual(llm.generate.call_count, 2)
        self.assertTrue(result.metadata["decision_fallback_used"])
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertNotIn("5%", result.answer)
        self.assertNotIn("3 months", result.answer)
        self.assertIn("holdout", result.answer)
        self.assertIn("estimate incremental sales", result.answer)
        self.assertIn("assess incremental contribution margin", result.answer)
        self.assertIn("[C1]", result.answer)
        self.assertIn("[S1]", result.answer)
        self.assertIn("ROAS requires both attributed revenue and advertising spend", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("do not claim that the experiment alone measures contribution margin", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("do not assume the marketing team already has one", llm.generate.call_args.kwargs["instructions"])

    def test_commerce_decision_returns_cited_fallback_when_llm_returns_no_text(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "promotion_planning", "domain_label": "Promotion planning",
            "source_tables": ["commerce.order_items"],
            "observations": {"promotions_by_year": [
                {"year": 2022, "used_promotion": True, "delivered_orders": 8, "net_sales": 200.0},
                {"year": 2022, "used_promotion": False, "delivered_orders": 12, "net_sales": 300.0},
            ]},
            "limitations": ["Promotion-tagged and untagged orders are descriptive, not a causal comparison."],
            "dataset_note": "Synthetic competition data.",
        }
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="DoorDash Ads incrementality guide",
            content="A randomized holdout or treatment/control comparison estimates incremental sales.",
            metadata={"evidence_class": "company_practice_reference", "source_publisher": "DoorDash Ads"},
        )])
        llm = Mock()
        llm.generate.side_effect = EmptyLLMResponseError("Groq returned empty output")

        with patch.dict(os.environ, {"HUGGINGFACE_LLM_FALLBACK": "false"}):
            result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
                question="Có nên tăng ngân sách khuyến mãi không?",
                metadata={"business_decision_domain": "promotion_planning", "role": "analyst"},
            ))

        self.assertTrue(result.metadata["decision_fallback_used"])
        self.assertEqual(result.metadata["generation_provider"], "deterministic_safety_fallback")
        self.assertEqual(result.metadata["answer_fallback_reason"], "provider_unavailable")
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertIn("[C1]", result.answer)
        self.assertNotRegex(result.answer, r"\[C1\] \[C1\]")
        self.assertIn("[S1]", result.answer)
        self.assertIn("không chứng minh quan hệ nhân quả", result.answer)

    def test_promotion_fallback_does_not_claim_a_two_group_comparison_from_tagged_only_rows(self):
        evidence = [
            Evidence(
                citation_id="C1", source_type="commerce_sql", source="Commerce promotion SQL",
                content=("promotions_by_year: " + json.dumps([
                    {"year": 2022, "used_promotion": True, "delivered_orders": 8, "net_sales": 200.0},
                ])),
            ),
            Evidence(
                citation_id="L1", source_type="commerce_schema", source="Commerce schema",
                content="The data has no randomized holdout or campaign-attributed costs.",
            ),
            Evidence(
                citation_id="S1", source_type="document", source="Synthetic Commerce Demo policy",
                content="Use holdout evidence before expanding a campaign.",
                metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True},
            ),
        ]

        answer = _commerce_safe_fallback(
            "promotion_planning", "Có nên mở rộng campaign dựa trên các số liệu này?", evidence,
        )

        self.assertIn("doanh số hoặc đơn hàng quan sát được", answer)
        self.assertIn("không cho biết phần kết quả tăng thêm", answer)
        self.assertNotIn("so sánh đơn có và không có", answer)

    def test_commerce_decision_degrades_transparently_when_reference_retrieval_is_rate_limited(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "promotion_planning", "domain_label": "Promotion planning",
            "source_tables": ["commerce.promotions"],
            "observations": {"promotions_by_year": [{"year": 2022, "net_sales": 200.0}]},
            "limitations": ["Campaign spend and a control outcome are unavailable."],
            "dataset_note": "Synthetic competition data.",
        }
        knowledge = Mock()
        knowledge.run.side_effect = RateLimitError(
            "rate limited", response=httpx.Response(429, request=httpx.Request("POST", "https://embed.test")), body=None,
        )
        llm = Mock()
        llm.generate.return_value = "Chưa tăng ngân sách vì dữ liệu không chứng minh hiệu quả gia tăng [C1][L1]."

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Should we increase the campaign budget?",
            metadata={"business_decision_domain": "promotion_planning", "role": "analyst"},
        ))

        self.assertTrue(result.metadata["decision_reference_retrieval_limited"])
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertNotIn("[S1]", result.answer)
        self.assertIn("document-backed", llm.generate.call_args.kwargs["instructions"])

    def test_commerce_suggestion_prompt_allows_multiple_conditional_actions(self):
        analytics = object.__new__(SQLAnalyticsAgent)
        analytics.commerce_decision_snapshot = Mock(return_value={
            "domain": "promotion_planning", "domain_label": "Promotion planning",
            "source_tables": ["commerce.promotions"],
            "observations": {"promotions_by_year": [{"year": 2022, "net_sales": 200}]},
            "limitations": ["Campaign cost and holdout outcomes are unavailable."],
            "dataset_note": "Synthetic Commerce competition data.",
        })
        analytics.commerce_question_observations = Mock()
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="Promotion measurement guide",
            content="Use a holdout to estimate incremental campaign outcomes.",
            metadata={"evidence_class": "management_cookbook_reference", "source_publisher": "Example Publisher"},
        )])
        llm = Mock()
        llm.generate.return_value = (
            "If a future holdout supports the approved business hurdle, then run a bounded follow-up; "
            "otherwise retain current spend and collect cost data. [C1][S1][L1]"
        )

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Suggest up to three conditional actions for promotion planning.",
            metadata={"business_decision_domain": "promotion_planning"},
        ))

        analytics.commerce_decision_snapshot.assert_called_once_with("promotion_planning")
        analytics.commerce_question_observations.assert_not_called()
        self.assertTrue(result.metadata["decision_suggestions"])
        instructions = llm.generate.call_args.kwargs["instructions"]
        self.assertIn("unless the user explicitly asks for multiple suggestions", instructions)
        self.assertIn("Generate at most three distinct conditional actions", instructions)

    def test_intent_classified_decision_support_retrieves_operating_reference(self):
        analytics = object.__new__(SQLAnalyticsAgent)
        analytics.commerce_question_observations = Mock(return_value={
            "domain": "inventory_allocation", "domain_label": "Inventory allocation",
            "source_tables": ["commerce.inventory"],
            "sql_query": "SELECT category, COUNT(*) AS rows FROM commerce.inventory GROUP BY category",
            "observations": [{"category": "Shoes", "rows": 20}],
            "limitations": ["The schema has no warehouse location or stock transfer cost."],
            "dataset_note": "Synthetic Commerce competition dataset.",
        })
        analytics.commerce_latest_inventory_flag_overlap = Mock(return_value=[])
        policy = Evidence(
            citation_id="S1", source_type="document", source="Commerce Demo inventory guide",
            content="Compare current stockout and overstock flags before deciding whether to replenish.",
            metadata={"evidence_class": "company_policy_reference", "synthetic_company_policy": True},
        )
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[policy])
        llm = Mock()
        llm.generate.return_value = (
            "Shoes has 20 inventory rows in the supplied comparison [C1]. "
            "Review the flags before replenishment under the fictional demo guide [S1]. "
            "The data has no warehouse location or transfer cost, so it cannot support transfer planning [L1]."
        )

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Explain the steps to review stockout and overstock flags before replenishment.",
            metadata={"business_decision_domain": "inventory_allocation", "decision_support": True,
                      "role": "analyst"},
        ))

        analytics.commerce_question_observations.assert_called_once()
        knowledge.run.assert_called_once()
        self.assertIn("Commerce Demo inventory guide", llm.generate.call_args.args[0])
        self.assertIn("Do not invent what qualifies as 'many'", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("[S1]", result.answer)

    def test_commerce_logistics_report_repairs_false_regional_equality_claim(self):
        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "nationwide_logistics", "domain_label": "Nationwide logistics",
            "source_tables": ["commerce.shipments"],
            "observations": {"logistics_by_year_region": [
                {"year": 2022, "region": "Central", "avg_transit_days": 4.51},
                {"year": 2022, "region": "East", "avg_transit_days": 4.52},
                {"year": 2022, "region": "West", "avg_transit_days": 4.51},
            ]},
            "limitations": ["No carrier or route-cost detail."],
            "dataset_note": "Synthetic competition data.",
        }
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[Evidence(
            citation_id="S1", source_type="document", source="Amazon shareholder letter",
            content="Amazon describes regional fulfillment in its network.",
            metadata={"evidence_class": "company_practice_reference", "source_publisher": "Amazon.com, Inc."},
        )])
        llm = Mock()
        llm.generate.side_effect = [
            "Transit averages are identical across regions, so there is no variation [C1]. "
            "Amazon describes regional fulfillment as an example, not local policy [S1].",
            "The regional averages differ slightly, and these summaries do not identify why [C1]. "
            "Amazon describes regional fulfillment in its own network; this is a practice example, not Commerce Demo policy [S1].",
        ]

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Should we change the nationwide delivery network based on transit times?",
            metadata={"business_decision_domain": "nationwide_logistics", "role": "operations"},
        ))

        self.assertEqual(llm.generate.call_count, 2)
        self.assertFalse(result.metadata["citation_validation_failed"])
        self.assertFalse(result.metadata["decision_fallback_used"])
        self.assertIn("regional averages differ slightly", result.answer)
        self.assertIn("do not call them identical", llm.generate.call_args_list[1].args[0])
        self.assertIn("Do not claim a region has an unacceptable service or cost level", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("unless the passage explicitly does so", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("Do not invent or list possible delay causes", llm.generate.call_args.kwargs["instructions"])
        self.assertIn("unless the user explicitly asks for one", llm.generate.call_args.kwargs["instructions"])

    def test_commerce_time_series_repairs_monotonic_claim_when_group_reverses(self):
        rows = [
            {"year": 2020, "region": "West", "avg_shipping_fee": 4.11},
            {"year": 2021, "region": "West", "avg_shipping_fee": 4.36},
            {"year": 2022, "region": "West", "avg_shipping_fee": 3.89},
        ]
        evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
            content=f"logistics_by_year_region observations: {json.dumps(rows)}",
        )]
        self.assertTrue(_has_unsupported_monotonic_commerce_trend(
            "Phí vận chuyển West giảm dần mỗi năm [C1].", evidence,
        ))
        self.assertFalse(_has_unsupported_monotonic_commerce_trend(
            "Phí vận chuyển West giảm ở hai đầu kỳ nhưng tăng năm 2021 [C1].", evidence,
        ))
        string_rows = [
            {"year": "2020", "region": "West", "avg_shipping_fee": "4.1144616477272727",
             "avg_transit_time_days": "4.5066761363636364"},
            {"year": "2021", "region": "West", "avg_shipping_fee": "4.3564401343921808",
             "avg_transit_time_days": "4.4980146609651802"},
            {"year": "2022", "region": "West", "avg_shipping_fee": "3.8924595973915509",
             "avg_transit_time_days": "4.5099234476892543"},
        ]
        string_evidence = [Evidence(
            citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
            content=f"question_specific_query question-specific SQL observations: {json.dumps(string_rows)}",
        )]
        self.assertTrue(_has_unsupported_monotonic_commerce_trend(
            "Phí vận chuyển West giảm dần mỗi năm [C1].", string_evidence,
        ))

        analytics = Mock()
        analytics.commerce_decision_snapshot.return_value = {
            "domain": "nationwide_logistics", "domain_label": "Nationwide logistics",
            "source_tables": ["commerce.shipments", "commerce.geography"],
            "observations": {"logistics_by_year_region": rows},
            "limitations": [], "dataset_note": "Synthetic Commerce data.",
        }
        knowledge, llm = Mock(), Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[])
        llm.generate.side_effect = [
            "Phí vận chuyển West giảm dần mỗi năm từ 4.11 xuống 3.89 [C1].",
            "Phí vận chuyển West giảm giữa hai đầu kỳ, nhưng tăng từ 4.11 năm 2020 lên 4.36 năm 2021 rồi còn 3.89 năm 2022 [C1].",
        ]
        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(AgentRequest(
            question="Trong 2020–2022 phí vận chuyển ở West thay đổi ra sao?",
            metadata={"business_decision_domain": "nationwide_logistics", "role": "analyst"},
        ))
        self.assertEqual(llm.generate.call_count, 2)
        self.assertIn("intermediate reversal", llm.generate.call_args.args[0])
        self.assertFalse(result.metadata.get("citation_validation_failed", False))
        self.assertIn("tăng từ 4.11", result.answer)

    def test_natural_language_conditional_recommendation_stays_a_question(self):
        question = (
            "Should Example Retailer prioritize preventing waste at source or improving recovery? "
            "Give a conditional recommendation: test prevention where avoidable loss is confirmed."
        )
        self.assertFalse(_is_decision_suggestions_request(question))
        self.assertTrue(_is_decision_suggestions_request(
            "Generate conditional management actions from verified annual KPIs."
        ))

    def test_report_prompt_formats_verified_metrics_compactly(self):
        item = Evidence(
            citation_id="M1", source_type="verified_metric", source="Example Retailer 2025 · OEE target",
            content="x" * 10000,
            metadata={"metric_label": "OEE target", "fiscal_year": 2025,
                      "metric_value": 99, "unit": "%", "page_number": 86,
                      "value_qualifier": "more_than", "reporting_period": "H1",
                      "source_url": "https://example.test/long-url"},
        )
        formatted = _format_prompt_evidence(item)
        self.assertIn("H1 2025 = more than 99 %", formatted)
        self.assertIn("page 86", formatted)
        self.assertNotIn("source_url", formatted)
        self.assertLess(len(formatted), 200)

    def test_report_prompt_labels_external_company_practice_as_reference(self):
        item = Evidence(
            citation_id="S1", source_type="document", source="2022 Letter to Shareholders",
            content="Amazon regionalized inventory placement.",
            metadata={"evidence_class": "company_practice_reference", "source_publisher": "Amazon.com, Inc.",
                      "reference_applicability": "External platform example only."},
        )
        formatted = _format_prompt_evidence(item)
        self.assertIn("External operating reference published by Amazon.com, Inc.", formatted)
        self.assertIn("not Commerce Demo policy", formatted)
        self.assertIn("Scope: External platform example only.", formatted)

    def test_knowledge_agent_fails_closed_without_authenticated_role(self):
        rag = Mock()

        for metadata in ({}, {"role": ""}, {"role": None}):
            with self.subTest(metadata=metadata), self.assertRaisesRegex(ValueError, "authenticated role"):
                KnowledgeAgent(rag).run(AgentRequest(question="restricted policy", metadata=metadata))

        rag.generate_answer.assert_not_called()
        rag.retrieve_contexts.assert_not_called()

    def test_metric_ontology_resolves_bilingual_aliases_and_prefers_specific_phrase(self):
        self.assertEqual(resolve_metric_names("Revenue and profit after tax"), {"net_revenue", "profit_after_tax"})
        self.assertEqual(resolve_metric_names("Total revenue"), {"total_consolidated_revenue"})
        self.assertEqual(resolve_metric_names("Net revenue"), {"net_revenue"})
        self.assertEqual(resolve_metric_names("Tổng doanh thu hợp nhất năm 2024"), {"total_consolidated_revenue"})
        self.assertEqual(resolve_metric_names("Doanh thu 2024 là 32.576.991"), {"net_revenue"})

    def test_generic_how_many_question_stays_document_qa(self):
        intent = IntentClassifier.fallback("Trong 100 ml sữa có bao nhiêu năng lượng và protein?")
        self.assertEqual(intent.intent, "knowledge")
        self.assertFalse(intent.needs_sql)

    def test_employee_policy_lookup_stays_document_qa_but_headcount_analysis_uses_sql(self):
        policy_intent = IntentClassifier.fallback("Search for the employee access policy")
        metric_intent = IntentClassifier.fallback("Compare employee headcount and training hours over time")

        self.assertEqual(policy_intent.intent, "knowledge")
        self.assertFalse(policy_intent.needs_sql)
        self.assertEqual(metric_intent.intent, "analytics")
        self.assertTrue(metric_intent.needs_sql)
        self.assertFalse(metric_intent.needs_knowledge)

    def test_commerce_inventory_decision_question_gets_hybrid_intent(self):
        intent = IntentClassifier.fallback("Should we rebalance inventory based on stockout and overstock indicators?")
        self.assertEqual(intent.intent, "hybrid")
        self.assertTrue(intent.needs_sql)
        self.assertTrue(intent.needs_knowledge)

    def test_sql_analytics_agent_filters_using_canonical_vietnamese_metric(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"metric_name": "total_consolidated_revenue", "metric_label": "Doanh thu hợp nhất",
                         "fiscal_year": 2024, "metric_value": 61824, "unit": "tỷ đồng",
                         "evidence_metric_ids": [1]}],
            "evidence": [{"metric_name": "total_consolidated_revenue", "metric_label": "Doanh thu hợp nhất",
                          "fiscal_year": 2024, "metric_value": 61824, "unit": "tỷ đồng",
                          "company": "Example Retailer", "metric_id": 1, "document_id": "AR24", "page_number": 12,
                          "source_url": "https://example.test/ar24", "source_quote": "Doanh thu 18.624 tỷ đồng"}],
            "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, metric_label, fiscal_year, metric_value, unit, '
            'ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids '
            'FROM authorized_financial_metrics WHERE fiscal_year = 2024 AND '
            "metric_name = 'total_consolidated_revenue' GROUP BY metric_name, metric_label, fiscal_year, metric_value, unit" + '"}'
        )
        agent = SQLAnalyticsAgent(repository, llm)
        result = agent.run(AgentRequest(question="Doanh thu hợp nhất năm 2024", metadata={"role": "finance_analyst"}))
        repository.execute_authorized_analytics.assert_called_once()
        self.assertEqual(repository.execute_authorized_analytics.call_args.args[1:], ("finance_analyst", "", None))
        self.assertEqual([row["metric_name"] for row in result.data["financial"]], ["total_consolidated_revenue"])

    def test_dashboard_sql_prompt_requests_individual_source_observations(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [], "evidence": [], "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, fiscal_year, ARRAY_AGG(DISTINCT metric_id) '
            'AS evidence_metric_ids FROM authorized_financial_metrics '
            'GROUP BY metric_name, fiscal_year LIMIT 10"}'
        )
        agent = SQLAnalyticsAgent(repository, llm)

        agent.run(AgentRequest(
            question="Revenue by year", metadata={"role": "finance_analyst", "dashboard_visualization": True},
        ))

        prompt = llm.generate.call_args.args[0]
        self.assertIn("return individual observations only", prompt.lower())
        self.assertIn("metric_value, unit, and document_id directly", prompt)
        self.assertIn("without summing or averaging values", prompt)

    def test_classifier_fallback_routes_summary_request_to_report_agent(self):
        intent = IntentClassifier.fallback("Summarize Example Retailer revenue and profit for 2024")
        self.assertEqual(intent.intent, "report")
        self.assertTrue(intent.needs_sql)
        self.assertTrue(intent.needs_knowledge)

    def test_classifier_accepts_explicit_report_intent(self):
        llm = Mock()
        llm.generate.return_value = (
            '{"intent":"report","needs_knowledge":true,"needs_sql":true,'
            '"output_mode":"answer","confidence":0.9}'
        )
        intent = IntentClassifier(llm).classify("Summarize these company documents")
        self.assertEqual(intent.intent, "report")

    def test_commerce_domain_classifier_uses_profile_context_and_supported_ids(self):
        llm = Mock()
        llm.generate.return_value = '{"domain":"nationwide_logistics","confidence":0.92}'
        domain = IntentClassifier(llm).classify_commerce_domain(
            "Should we move delivery capacity between regions?"
        )
        self.assertEqual(domain, "nationwide_logistics")
        prompt = llm.generate.call_args.args[0]
        self.assertIn("commerce.shipments", prompt)
        self.assertIn("inventory_allocation", prompt)
        self.assertIn("stock availability stockout overstock replenishment", prompt)

    def test_commerce_domain_classifier_abstains_on_low_confidence_and_uses_clear_fallback(self):
        llm = Mock()
        llm.generate.return_value = '{"domain":"promotion_planning","confidence":0.4}'
        classifier = IntentClassifier(llm)
        self.assertEqual(classifier.classify_commerce_domain("Should we repeat the campaign?"), "promotion_planning")
        llm.generate.return_value = '{"domain":null,"confidence":0.91}'
        self.assertIsNone(classifier.classify_commerce_domain("What business decision should we make?"))

    def test_product_availability_paraphrases_resolve_to_inventory_domain(self):
        self.assertEqual(
            resolve_commerce_decision_domain("What changes could reduce products being unavailable for customers?"),
            "inventory_allocation",
        )

    def test_domain_fallback_matches_common_english_inflections_without_guessing_ambiguous_questions(self):
        self.assertEqual(
            resolve_commerce_decision_domain(
                "Which products repeatedly appear at risk, and what should we verify before replenishing?"
            ),
            "inventory_allocation",
        )
        self.assertIsNone(resolve_commerce_decision_domain("What should the business prioritize next quarter?"))

    def test_report_intent_falls_back_to_hybrid_when_report_agent_is_not_configured(self):
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback("Summarize these company documents")
        hybrid = Mock()
        hybrid.run.return_value = AgentResult(answer="grounded summary", agent="hybrid")
        unused = Mock()
        router = AgentRouter(classifier, unused, unused, hybrid, unused)

        result = router.route(AgentRequest(question="Summarize these company documents"))

        self.assertEqual(result.agent, "hybrid")
        hybrid.run.assert_called_once()

    def test_explicit_dashboard_output_is_not_rewritten_to_report(self):
        llm = Mock()
        llm.generate.return_value = (
            '{"intent":"dashboard","needs_knowledge":false,"needs_sql":true,'
            '"output_mode":"dashboard","confidence":0.9}'
        )
        intent = IntentClassifier(llm).classify("Summarize these metrics in a dashboard")
        self.assertEqual(intent.intent, "dashboard")
        self.assertEqual(intent.output_mode, "dashboard")

    def test_router_sends_commerce_chart_requests_to_dashboard_agent(self):
        report, dashboard, classifier = Mock(), Mock(), Mock()
        dashboard.run.return_value = AgentResult(
            answer="Dashboard chart [C1]", agent="dashboard",
        )
        router = AgentRouter(classifier, Mock(), Mock(), Mock(), dashboard, report)
        request = AgentRequest(question="Show a chart of inventory fill rate by year")

        result = router.route(request)

        self.assertEqual(result.agent, "dashboard")
        self.assertEqual(request.metadata["business_decision_domain"], "inventory_allocation")
        dashboard.run.assert_called_once_with(request)
        report.run.assert_not_called()
        classifier.classify.assert_not_called()

    def test_document_metadata_counts_are_analytics_even_if_llm_says_knowledge(self):
        llm = Mock()
        llm.generate.return_value = (
            '{"intent":"knowledge","needs_knowledge":true,"needs_sql":false,'
            '"output_mode":"answer","confidence":0.9}'
        )

        intent = IntentClassifier(llm).classify("Compare document counts by business domain")

        self.assertEqual(intent.intent, "analytics")
        self.assertFalse(intent.needs_knowledge)
        self.assertTrue(intent.needs_sql)

        report_count_intent = IntentClassifier(llm).classify(
            "How many annual reports were published each year?"
        )
        self.assertEqual(report_count_intent.intent, "analytics")
        self.assertTrue(report_count_intent.needs_sql)

    def test_report_counts_are_analytics_not_document_summaries(self):
        intent = IntentClassifier.fallback("How many annual reports were published each year?")
        self.assertEqual(intent.intent, "analytics")
        self.assertFalse(intent.needs_knowledge)
        self.assertTrue(intent.needs_sql)

        report = Mock()
        unused = Mock()
        unused.run.return_value = AgentResult(answer="count", agent="analytics")
        classifier = Mock()
        classifier.classify.return_value = intent
        router = AgentRouter(classifier, unused, unused, unused, unused, report)
        result = router.route(AgentRequest(question="How many annual reports were published each year?"))

        self.assertEqual(result.agent, "analytics")
        unused.run.assert_called_once()
        report.run.assert_not_called()

    def test_financial_fact_questions_use_both_verified_analytics_and_documents(self):
        intent = IntentClassifier.fallback("What was Example Retailer's revenue in 2024?")
        self.assertEqual(intent.intent, "hybrid")
        self.assertTrue(intent.needs_sql)
        self.assertTrue(intent.needs_knowledge)

    def test_single_period_revenue_and_profit_summary_uses_guarded_report_agent(self):
        summary = IntentClassifier.fallback(
            "What were Example Retailer's revenue and profit after tax in 2024?"
        )
        self.assertEqual(summary.intent, "report")
        comparison = IntentClassifier.fallback(
            "Compare Example Retailer's revenue and profit after tax across years"
        )
        self.assertEqual(comparison.intent, "hybrid")
        year_comparison = IntentClassifier.fallback(
            "What were Example Retailer's revenue and profit after tax in 2024 vs 2023?"
        )
        self.assertEqual(year_comparison.intent, "hybrid")
        multiple_periods = IntentClassifier.fallback(
            "What were Example Retailer's revenue and profit after tax in 2024 and 2023?"
        )
        self.assertEqual(multiple_periods.intent, "hybrid")

    def test_why_financial_change_question_uses_grounded_report_route(self):
        intent = IntentClassifier.fallback(
            "tại sao total assets của 2021 lại tăng so với 2020"
        )
        self.assertEqual(intent.intent, "report")
        self.assertTrue(intent.needs_knowledge)
        self.assertTrue(intent.needs_sql)

    def test_why_financial_change_bypasses_intent_llm_call(self):
        llm = Mock()
        result = IntentClassifier(llm).classify(
            "tại sao total assets của 2021 lại tăng so với 2020"
        )
        self.assertEqual(result.intent, "report")
        llm.generate.assert_not_called()

    def test_knowledge_agent_passes_trusted_role_and_maps_source_id(self):
        rag = Mock()
        rag.generate_answer.return_value = RAGResult(
            answer="Reported result [S1]", source_ids=["S1"],
            generation_provider="huggingface_inference",
            token_usage={"input_tokens": 24, "output_tokens": 8, "total_tokens": 32},
            contexts=[{"source_id": "S1", "document_name": "Annual report", "chunk_index": 2,
                       "content": "Net revenue 100", "metadata": {"page_number": 4},
                       "retrieval_score": 0.9, "retrieval_method": "hybrid"}],
        )
        agent = KnowledgeAgent(rag)
        result = agent.run(AgentRequest(question="revenue", user_id="analyst", metadata={"role": "finance_analyst"}))
        rag.generate_answer.assert_called_once_with("revenue", limit=10, company=None, roles=["finance_analyst"])
        self.assertEqual(result.evidence[0].citation_id, "S1")
        self.assertEqual(result.metadata["generation_provider"], "huggingface_inference")
        self.assertEqual(result.metadata["token_usage"]["total"]["total_tokens"], 32)

    def test_policy_qa_retrieval_is_limited_to_the_resolved_commerce_domain(self):
        rag = Mock()
        rag.retrieve_contexts.return_value = []
        rag.generate_answer.return_value = RAGResult(answer="Policy answer [S1]", source_ids=["S1"])
        question = "What does the inventory policy require before transferring stock?"

        KnowledgeAgent(rag).run(AgentRequest(
            question=question,
            metadata={"role": "analyst", "business_decision_domain": "inventory_allocation",
                      "policy_reference_only": True},
        ))

        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["metadata_filter"], {
            "commerce_reference_active": True,
            "knowledge_domains": ["inventory_allocation"],
            "evidence_class": "company_policy_reference",
        })
        self.assertEqual(rag.generate_answer.call_args.kwargs["retrieved_contexts"], [])

    def test_knowledge_agent_filters_explicit_page_before_ranking(self):
        rag = Mock()
        rag.retrieve_contexts.return_value = []
        rag.generate_answer.return_value = RAGResult(answer="No matching passage [S1]")
        question = "What exact restocking prompt appears in the screenshot on page 11 of the Shopee inventory guide?"

        KnowledgeAgent(rag).run(AgentRequest(
            question=question,
            metadata={"role": "analyst", "business_decision_domain": "inventory_allocation"},
        ))

        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["metadata_filter"], {
            "page_number": 11,
            "commerce_reference_active": True,
            "knowledge_domains": ["inventory_allocation"],
        })

    def test_commerce_document_qa_reranks_scoped_policy_before_external_methods(self):
        policy = {
            "source_id": "S2", "document_name": "Inventory policy", "chunk_index": 1,
            "content": "The policy requires checking stockout and overstock flags before replenishment.",
            "metadata": {"document_id": "CD-POL-INV-001", "commerce_reference_active": True,
                         "knowledge_domains": ["inventory_allocation"],
                         "evidence_class": "company_policy_reference", "synthetic_company_policy": True},
            "retrieval_score": 0.8, "retrieval_method": "bm25",
        }
        cookbook = {
            "source_id": "S1", "document_name": "Inventory guide", "chunk_index": 0,
            "content": "General inventory management guidance.",
            "metadata": {"document_id": "AUS-BUSINESS-INVENTORY-MANAGEMENT",
                         "commerce_reference_active": True, "knowledge_domains": ["inventory_allocation"],
                         "evidence_class": "management_cookbook_reference"},
            "retrieval_score": 0.9, "retrieval_method": "bm25",
        }
        rag = Mock()
        rag.retrieve_contexts.return_value = [cookbook, policy]
        rag.generate_answer.return_value = RAGResult(answer="Check flags before replenishment [S1]")
        question = "Explain the steps to review stockout and overstock flags before replenishment."

        KnowledgeAgent(rag).run(AgentRequest(
            question=question,
            metadata={"role": "admin", "company": "Commerce Demo",
                      "business_decision_domain": "inventory_allocation"},
        ))

        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["limit"], 50)
        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["metadata_filter"], {
            "commerce_reference_active": True,
            "knowledge_domains": ["inventory_allocation"],
        })
        selected = rag.generate_answer.call_args.kwargs["retrieved_contexts"]
        self.assertEqual(selected[0]["metadata"]["document_id"], "CD-POL-INV-001")

    def test_knowledge_agent_preserves_the_user_query_without_company_specific_rewrites(self):
        rag = Mock()
        rag.generate_answer.return_value = RAGResult(answer="Reported result [S1]", source_ids=["S1"])
        question = "What were the 2024 revenue and profit after tax?"
        KnowledgeAgent(rag).run(AgentRequest(
            question=question,
            metadata={"role": "analyst", "company": "Commerce Demo"},
        ))
        call = rag.generate_answer.call_args
        self.assertEqual(call.args[0], question)
        self.assertNotIn("retrieval_query", call.kwargs)

    def test_knowledge_agent_preserves_uncited_retrieved_context_for_report_stage(self):
        rag = Mock()
        rag.generate_answer.return_value = RAGResult(
            answer="Revenue was 32.6 trillion VND [S1]", source_ids=["S1"],
            contexts=[
                {"source_id": "S1", "chunk_id": "AR-2024::chunk::2", "document_name": "Annual report", "chunk_index": 2,
                 "content": "Audited statement revenue 32.6T", "metadata": {"page_number": 92},
                 "retrieval_score": 0.9, "retrieval_method": "hybrid"},
                {"source_id": "S7", "document_name": "Annual report", "chunk_index": 27,
                 "content": "Headline total consolidated revenue 18.624T", "metadata": {"page_number": 12},
                 "retrieval_score": 0.8, "retrieval_method": "hybrid"},
            ],
        )
        result = KnowledgeAgent(rag).run(AgentRequest(
            question="Summarize revenue", metadata={"role": "finance_analyst"}
        ))
        self.assertEqual([item.citation_id for item in result.evidence], ["S1", "S7"])
        self.assertEqual(result.evidence[0].metadata["retrieval_chunk_id"], "AR-2024::chunk::2")

    def test_report_knowledge_path_retrieves_evidence_without_first_generation(self):
        rag = Mock()
        rag.retrieve_contexts.return_value = [{
            "source_id": "S1", "document_name": "Annual report", "chunk_index": 2,
            "content": "Annual report metric", "metadata": {"page_number": 4},
            "retrieval_score": 0.9, "retrieval_method": "hybrid",
        }]
        result = KnowledgeAgent(rag).run(AgentRequest(
            question="Summarize annual report",
            metadata={"role": "finance_analyst", "evidence_only": True},
        ))
        rag.retrieve_contexts.assert_called_once()
        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["limit"], 5)
        rag.generate_answer.assert_not_called()
        self.assertEqual(result.evidence[0].citation_id, "S1")

    def test_decision_support_report_limits_retrieved_passages_for_provider_tpm(self):
        rag = Mock()
        rag.retrieve_contexts.return_value = []

        KnowledgeAgent(rag).run(AgentRequest(
            question="Should Example Retailer allocate more capital to overseas markets?",
            metadata={"role": "admin", "evidence_only": True, "decision_support": True},
        ))

        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["limit"], 3)

    def test_commerce_decision_retrieval_filters_active_sources_by_domain_before_ranking(self):
        rag = Mock()
        rag.retrieve_contexts.return_value = []

        KnowledgeAgent(rag).run(AgentRequest(
            question="Should we rebalance inventory across locations?",
            metadata={"role": "analyst", "evidence_only": True,
                      "decision_support": True, "business_decision_domain": "inventory_allocation"},
        ))

        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["metadata_filter"], {
            "commerce_reference_active": True,
            "knowledge_domains": ["inventory_allocation"],
        })

    def test_knowledge_agent_routes_explicit_parent_retrieval(self):
        rag = Mock()
        rag.generate_answer.return_value = RAGResult(answer="answer", source_ids=[])
        KnowledgeAgent(rag).run(AgentRequest(
            question="revenue", metadata={"role": "finance_analyst", "retrieval_method": "parent"}
        ))
        rag.generate_answer.assert_called_once_with(
            "revenue", limit=10, company=None, roles=["finance_analyst"], retrieval_method="parent"
        )

    def test_router_uses_report_for_summary_requests(self):
        for question in ("Summarize revenue", "Tóm tắt doanh thu năm 2024"):
            with self.subTest(question=question):
                report = Mock()
                report.run.return_value = AgentResult(answer="report result", agent="report")
                unused = Mock()
                classifier = Mock()
                classifier.classify.return_value = IntentClassifier.fallback(question)
                router = AgentRouter(classifier, unused, unused, unused, unused, report)
                result = router.route(AgentRequest(question=question))
                self.assertEqual(result.agent, "report")
                report.run.assert_called_once()
                unused.run.assert_not_called()

    def test_router_sends_conditional_decision_suggestions_directly_to_report(self):
        question = "Generate conditional management actions from verified annual KPIs."
        classifier, report = Mock(), Mock()
        report.run.return_value = AgentResult(answer="conditional actions", agent="report")
        unused = Mock()
        router = AgentRouter(classifier, unused, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question, metadata={"decision_suggestions": True}))

        self.assertEqual(result.agent, "report")
        self.assertEqual(router.last_destination, "report")
        classifier.classify.assert_not_called()
        report.run.assert_called_once()

    def test_router_marks_natural_conditional_actions_as_suggestion_mode(self):
        question = "Suggest up to three conditional next actions for nationwide logistics."
        classifier, report = Mock(), Mock()
        report.run.return_value = AgentResult(answer="bounded actions", agent="report")
        unused = Mock()
        request = AgentRequest(question=question)
        result = AgentRouter(classifier, unused, unused, unused, unused, report).route(request)

        self.assertEqual(result.agent, "report")
        self.assertTrue(report.run.call_args.args[0].metadata["decision_suggestions"])
        classifier.classify.assert_not_called()

    def test_router_auto_detects_domain_before_commerce_decision_analysis(self):
        classifier, report = Mock(), Mock()
        classifier.classify_commerce_domain.return_value = "promotion_planning"
        report.run.return_value = AgentResult(answer="promotion evidence", agent="report")
        unused = Mock()
        request = AgentRequest(
            question="Should we repeat the campaign?",
            metadata={"commerce_decision_support": True},
        )
        router = AgentRouter(classifier, unused, unused, unused, unused, report)

        result = router.route(request)

        classifier.classify_commerce_domain.assert_called_once_with(request.question)
        self.assertEqual(report.run.call_args.args[0].metadata["business_decision_domain"], "promotion_planning")
        self.assertTrue(result.metadata["business_domain_auto_detected"])

    def test_router_asks_for_domain_when_commerce_question_is_ambiguous(self):
        classifier, report = Mock(), Mock()
        classifier.classify_commerce_domain.return_value = None
        unused = Mock()
        router = AgentRouter(classifier, unused, unused, unused, unused, report)

        result = router.route(AgentRequest(
            question="What should we improve?",
            metadata={"commerce_decision_support": True},
        ))

        self.assertEqual(result.agent, "commerce_domain_router")
        self.assertTrue(result.metadata["needs_domain_clarification"])
        report.run.assert_not_called()
        unused.run.assert_not_called()

    def test_selected_domain_policy_questions_use_knowledge_agent(self):
        question = "What does the inventory policy require before a stock transfer?"
        classifier, knowledge, report = Mock(), Mock(), Mock()
        knowledge.run.return_value = AgentResult(answer="Review SKU and location evidence [S1]", agent="knowledge")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question, metadata={
            "business_decision_domain": "inventory_allocation",
        }))

        self.assertEqual(result.agent, "knowledge")
        self.assertTrue(knowledge.run.call_args.args[0].metadata["policy_reference_only"])
        report.run.assert_not_called()

    def test_source_framed_promotion_planning_question_uses_knowledge_agent(self):
        question = "Theo tài liệu, nên lập và theo dõi kế hoạch khuyến mãi như thế nào?"
        classifier, knowledge, report = Mock(), Mock(), Mock()
        knowledge.run.return_value = AgentResult(answer="Review the planning guidance [S1]", agent="knowledge")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question, metadata={
            "business_decision_domain": "promotion_planning",
        }))

        self.assertEqual(result.agent, "knowledge")
        self.assertEqual(router.last_destination, "knowledge")
        self.assertEqual(
            knowledge.run.call_args.args[0].metadata["business_decision_domain"],
            "promotion_planning",
        )
        report.run.assert_not_called()
        classifier.classify.assert_not_called()

    def test_source_framed_decision_criteria_question_stays_on_knowledge_path(self):
        question = "Theo tài liệu, cần so sánh những yếu tố nào trước khi đổi mạng lưới giao hàng toàn quốc?"
        classifier, knowledge, report = Mock(), Mock(), Mock()
        knowledge.run.return_value = AgentResult(answer="Compare published criteria [S1]", agent="knowledge")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question, metadata={
            "business_decision_domain": "nationwide_logistics",
        }))

        self.assertEqual(result.agent, "knowledge")
        self.assertEqual(router.last_destination, "knowledge")
        self.assertEqual(
            knowledge.run.call_args.args[0].metadata["business_decision_domain"],
            "nationwide_logistics",
        )
        report.run.assert_not_called()
        classifier.classify.assert_not_called()

    def test_explicit_commerce_decision_form_keeps_how_to_question_on_report_path(self):
        question = "Theo tài liệu, cần làm gì để đánh giá hiệu quả trước khi mở rộng khuyến mãi?"
        classifier, knowledge, report = Mock(), Mock(), Mock()
        report.run.return_value = AgentResult(answer="SQL plus source guidance [C1][S1]", agent="report")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question, metadata={
            "business_decision_domain": "promotion_planning",
            "commerce_decision_support": True,
        }))

        self.assertEqual(result.agent, "report")
        self.assertEqual(router.last_destination, "report")
        report.run.assert_called_once()
        knowledge.run.assert_not_called()
        classifier.classify.assert_not_called()

    def test_unseen_commerce_method_question_uses_shared_intent_and_domain_filtered_knowledge(self):
        question = "Explain how regional delivery coordination works."
        classifier, knowledge, report = Mock(), Mock(), Mock()
        classifier.classify.return_value = IntentClassifier.fallback(question)
        knowledge.run.return_value = AgentResult(answer="Review the relevant evidence [S1]", agent="knowledge")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question))

        self.assertEqual(result.agent, "knowledge")
        self.assertEqual(router.last_destination, "knowledge")
        self.assertEqual(
            knowledge.run.call_args.args[0].metadata["business_decision_domain"],
            "nationwide_logistics",
        )
        self.assertTrue(result.metadata["business_domain_auto_detected"])
        report.run.assert_not_called()

    def test_commerce_method_applied_to_current_flags_routes_to_sql_and_retrieved_policy(self):
        question = "Explain the steps to review stockout and overstock flags before replenishment."
        classifier, knowledge, report = Mock(), Mock(), Mock()
        classifier.classify.return_value = IntentResult(
            intent="knowledge", needs_knowledge=True, needs_sql=False,
            output_mode="answer", confidence=0.9,
        )
        report.run.return_value = AgentResult(answer="Use current flags with policy limits [C1][S1]", agent="report")
        unused = Mock()
        result = AgentRouter(classifier, knowledge, unused, unused, unused, report).route(
            AgentRequest(question=question),
        )

        self.assertEqual(result.agent, "report")
        classifier.classify.assert_not_called()
        self.assertTrue(report.run.call_args.args[0].metadata["decision_support"])
        knowledge.run.assert_not_called()

    def test_pre_action_data_question_routes_through_commerce_report_without_special_ui_mode(self):
        question = "Trước khi chuyển hàng giữa các nhóm có stockout và overstock, cần kiểm tra dữ liệu nào?"
        classifier, knowledge, report = Mock(), Mock(), Mock()
        classifier.classify.return_value = IntentClassifier.fallback(question)
        report.run.return_value = AgentResult(answer="Cần đối chiếu dữ liệu theo SKU [C1][L1]", agent="report")
        unused = Mock()

        result = AgentRouter(classifier, knowledge, unused, unused, unused, report).route(
            AgentRequest(question=question),
        )

        self.assertEqual(result.agent, "report")
        self.assertEqual(result.metadata["business_decision_domain"], "inventory_allocation")
        report.run.assert_called_once()
        knowledge.run.assert_not_called()

    def test_router_keeps_general_inventory_method_question_on_knowledge_path(self):
        question = "Explain the steps for an inventory stocktake."
        classifier, knowledge, report = Mock(), Mock(), Mock()
        classifier.classify.return_value = IntentClassifier.fallback(question)
        knowledge.run.return_value = AgentResult(answer="Follow the published steps [S1]", agent="knowledge")
        report.run.return_value = AgentResult(answer="unexpected SQL route", agent="report")
        unused = Mock()

        result = AgentRouter(classifier, knowledge, unused, unused, unused, report).route(
            AgentRequest(question=question),
        )

        self.assertEqual(result.agent, "knowledge")
        self.assertEqual(
            knowledge.run.call_args.args[0].metadata["business_decision_domain"],
            "inventory_allocation",
        )
        report.run.assert_not_called()

    def test_commerce_aggregation_fallback_keeps_sql_questions_on_report_path(self):
        question = "Which category had the most stockout rows?"
        classifier, knowledge, report = Mock(), Mock(), Mock()
        classifier.classify.return_value = IntentClassifier.fallback(question)
        report.run.return_value = AgentResult(answer="SQL comparison [C1]", agent="report")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question))

        self.assertEqual(result.agent, "report")
        self.assertTrue(classifier.classify.return_value.needs_sql)
        knowledge.run.assert_not_called()

    def test_explicit_commerce_decision_ui_keeps_report_route_when_intent_says_knowledge(self):
        classifier, knowledge, report = Mock(), Mock(), Mock()
        classifier.classify.return_value = IntentResult(
            intent="knowledge", needs_knowledge=True, needs_sql=False,
            output_mode="answer", confidence=0.91,
        )
        report.run.return_value = AgentResult(answer="Decision synthesis", agent="report")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question="How can we review inventory?", metadata={
            "business_decision_domain": "inventory_allocation",
            "commerce_decision_support": True,
        }))

        self.assertEqual(result.agent, "report")
        classifier.classify.assert_not_called()
        knowledge.run.assert_not_called()

    def test_router_sends_implicit_commerce_decision_questions_to_report(self):
        questions = (
            "Trong snapshot tồn kho mới nhất, nhóm hàng nào có nhiều sản phẩm bị gắn cờ stockout nhất? "
            "Có nên chuyển hàng từ nhóm overstock sang không?",
            "Đơn hàng delivered gắn với khuyến mãi so với nhóm không gắn tag thay đổi ra sao? "
            "Điều này có chứng minh uplift để tăng ngân sách không?",
            "Trong 2022, vùng nào có average transit time cao nhất và có nên thiết kế lại mạng lưới giao hàng không?",
            "Trong các campaign 2022, campaign nào có net sales gắn tag cao nhất trong thời gian chạy?",
            "Trong 2020–2022, shipping fee và transit time theo vùng thay đổi ra sao?",
        )
        for question in questions:
            with self.subTest(question=question):
                report, unused, classifier = Mock(), Mock(), Mock()
                report.run.return_value = AgentResult(answer="decision synthesis", agent="report")
                router = AgentRouter(classifier, unused, unused, unused, unused, report)

                result = router.route(AgentRequest(question=question))

                self.assertEqual(result.agent, "report")
                self.assertEqual(router.last_destination, "report")
                report.run.assert_called_once()
                unused.run.assert_not_called()

    def test_router_keeps_named_source_how_to_question_on_knowledge_path(self):
        question = "What does Shopify say about inventory transfers between locations?"
        classifier, knowledge, report = Mock(), Mock(), Mock()
        classifier.classify.return_value = IntentClassifier.fallback(question)
        knowledge.run.return_value = AgentResult(answer="Shopify guidance", agent="knowledge")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question))

        self.assertEqual(result.agent, "knowledge")
        self.assertEqual(router.last_destination, "knowledge")
        knowledge.run.assert_called_once()
        report.run.assert_not_called()

    def test_router_keeps_exact_source_page_text_question_on_knowledge_path(self):
        question = "What exact restocking prompt appears in the screenshot on page 11 of the Shopee inventory guide?"
        classifier, knowledge, report = Mock(), Mock(), Mock()
        classifier.classify.return_value = IntentResult(
            intent="report", needs_knowledge=True, needs_sql=True,
            output_mode="answer", confidence=0.9,
        )
        knowledge.run.return_value = AgentResult(answer="The screenshot says ... [S1]", agent="knowledge")
        report.run.return_value = AgentResult(answer="Unexpected SQL route [C1]", agent="report")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question))

        self.assertEqual(result.agent, "knowledge")
        self.assertEqual(router.last_destination, "knowledge")
        self.assertEqual(
            knowledge.run.call_args.args[0].metadata["business_decision_domain"],
            "inventory_allocation",
        )
        classifier.classify.assert_not_called()
        report.run.assert_not_called()

    def test_source_method_applied_to_current_inventory_data_still_uses_report(self):
        question = "According to Amazon, based on current inventory flags, what should we verify before replenishing?"
        classifier, knowledge, report = Mock(), Mock(), Mock()
        report.run.return_value = AgentResult(answer="Check the current data with the guide [C1][S1]", agent="report")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question))

        self.assertEqual(result.agent, "report")
        self.assertEqual(router.last_destination, "report")
        report.run.assert_called_once()
        knowledge.run.assert_not_called()

    def test_router_sends_policy_only_questions_to_knowledge_not_commerce_sql(self):
        question = "Theo chính sách giả lập về tồn kho, cần kiểm tra điều gì trước khi đề xuất điều chuyển?"
        classifier, knowledge, report = Mock(), Mock(), Mock()
        classifier.classify.return_value = IntentClassifier.fallback(question)
        knowledge.run.return_value = AgentResult(answer="Policy answer [S1]", agent="knowledge")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question))

        self.assertEqual(result.agent, "knowledge")
        self.assertEqual(router.last_destination, "knowledge")
        self.assertEqual(knowledge.run.call_args.args[0].metadata["business_decision_domain"], "inventory_allocation")
        self.assertTrue(knowledge.run.call_args.args[0].metadata["policy_reference_only"])
        knowledge.run.assert_called_once()
        report.run.assert_not_called()
        classifier.classify.assert_not_called()

    def test_router_keeps_policy_based_business_decisions_on_report_path(self):
        question = "Có nên điều chuyển hàng theo chính sách tồn kho để giảm stockout không?"
        report, knowledge, classifier = Mock(), Mock(), Mock()
        report.run.return_value = AgentResult(answer="Decision synthesis", agent="report")
        router = AgentRouter(classifier, knowledge, Mock(), Mock(), Mock(), report)

        result = router.route(AgentRequest(question=question))

        self.assertEqual(result.agent, "report")
        report.run.assert_called_once()
        knowledge.run.assert_not_called()

    def test_decision_suggestion_rejects_numeric_comparator_not_reported_as_a_hurdle(self):
        evidence = [Evidence(citation_id="M1", source_type="verified_metric",
                             source="FY2025 overseas revenue growth", content="Overseas growth was 15.5%.")]
        unsupported = "If growth exceeds 15.5%, then start a pilot. [M1]"
        grounded = "If growth continues, then review a bounded pilot against the approved hurdle. [M1]"
        self.assertTrue(_has_unsupported_numeric_decision_gate(unsupported, evidence))
        self.assertFalse(_has_unsupported_numeric_decision_gate(grounded, evidence))

        threshold_evidence = [Evidence(citation_id="M2", source_type="verified_metric",
                                       source="FY2025 approved target", content="The approved target is 15.5%.")]
        self.assertFalse(_has_unsupported_numeric_decision_gate(
            "If growth exceeds the approved target of 15.5%, then start a pilot. [M2]", threshold_evidence,
        ))
        self.assertTrue(_has_unsupported_numeric_decision_gate(
            "Increase fill rate above the current 0.9635 after the pilot [C1].", [
                Evidence(citation_id="C1", source_type="commerce_sql", source="inventory",
                         content="avg_fill_rate: 0.9635")
            ],
        ))

    def test_general_decision_report_rejects_invented_numeric_condition(self):
        evidence = [Evidence(
            citation_id="M1", source_type="verified_metric", source="FY2024 channel revenue",
            content="Direct export revenue grew 16.5%; overseas subsidiary revenue grew 12.9%.",
        )]
        unsupported = (
            "If subsidiary revenue grows faster than exports by 5% for two years, then rebalance investment; "
            "otherwise continue monitoring [M1]."
        )
        sourced_policy = [Evidence(
            citation_id="M2", source_type="document", source="Approved investment policy",
            content="The approved threshold is 5% for two years.",
        )]
        supported = (
            "If subsidiary revenue grows faster than exports by more than the approved threshold of 5% for two years, "
            "then review allocation; otherwise continue monitoring [M2]."
        )
        question = "Should we prioritize one international sales channel over another?"

        self.assertEqual(
            _report_validation_failure(unsupported, evidence, {"M1"}, question),
            "decision_gate_uses_an_unsourced_numeric_threshold",
        )
        self.assertIsNone(_report_validation_failure(supported, sourced_policy, {"M2"}, question))

    def test_general_decision_report_rejects_calculated_number_absent_from_source(self):
        evidence = [Evidence(
            citation_id="M1", source_type="verified_metric", source="FY2024 domestic net revenue",
            content="Domestic segment net revenue was VND 50,964 billion.",
            metadata={"metric_value": 50964, "fiscal_year": 2024},
        ), Evidence(
            citation_id="M2", source_type="verified_metric", source="FY2024 domestic gross profit",
            content="Domestic segment gross profit was VND 20,675 billion.",
            metadata={"metric_value": 20675, "fiscal_year": 2024},
        )]
        unsupported_calculation = "Domestic gross margin was 40.57% in FY2024 [M1][M2]."
        reported_values = "Domestic net revenue was VND 50,964 billion in FY2024 [M1]."
        question = "Should we prioritize domestic or overseas investment?"

        self.assertEqual(
            _report_validation_failure(unsupported_calculation, evidence, {"M1", "M2"}, question),
            "decision_numeric_claim_not_present_in_cited_evidence",
        )
        self.assertIsNone(_report_validation_failure(reported_values, evidence, {"M1"}, question))

    def test_decision_threshold_must_be_in_the_cited_evidence_for_that_action(self):
        evidence = [
            Evidence(citation_id="M1", source_type="verified_metric", source="FY2025 waste",
                     content="Waste reduction was 15.5%."),
            Evidence(citation_id="M2", source_type="verified_metric", source="Approved energy target",
                     content="The target is 15.5%."),
        ]
        self.assertTrue(_has_unsupported_numeric_decision_gate(
            "If waste reduction exceeds 15.5%, then expand the waste pilot; otherwise audit the source [M1].",
            evidence,
        ))
        self.assertFalse(_has_unsupported_numeric_decision_gate(
            "If energy savings exceed 15.5%, then expand the energy pilot; otherwise audit the source [M2].",
            evidence,
        ))
        observed_target_result = [Evidence(
            citation_id="M3", source_type="verified_metric", source="FY2025 OEE target KPI",
            content="96% of production lines met their OEE targets.",
        )]
        self.assertTrue(_has_unsupported_numeric_decision_gate(
            "If OEE exceeds 96%, then expand the program. [M3]", observed_target_result,
        ))





    def test_mentioning_an_annual_report_does_not_force_report_generation(self):
        question = "What does the annual report say about governance?"
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback(question)
        knowledge, unused, report = Mock(), Mock(), Mock()
        knowledge.run.return_value = AgentResult(answer="source answer", agent="knowledge")
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question))

        self.assertEqual(result.agent, "knowledge")
        knowledge.run.assert_called_once()
        report.run.assert_not_called()

    def test_router_keeps_selected_destination_when_agent_raises(self):
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback("What does the policy say?")
        knowledge = Mock()
        knowledge.run.side_effect = RuntimeError("provider unavailable")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused)

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            router.route(AgentRequest(question="What does the policy say?"))
        self.assertEqual(router.last_destination, "knowledge")

    def test_langgraph_routes_to_each_intent_agent(self):
        cases = [
            ("What does the product policy say?", "knowledge"),
            ("Compare document counts by domain", "analytics"),
            ("What was revenue in 2024?", "hybrid"),
            ("Show the dashboard", "dashboard"),
            ("Generate conditional management actions for inventory allocation", "report"),
        ]
        for question, selected_agent in cases:
            with self.subTest(selected_agent=selected_agent):
                classifier = Mock()
                classifier.classify.return_value = IntentClassifier.fallback(question)
                agents = {
                    name: Mock(run=Mock(return_value=AgentResult(answer=name, agent=name)))
                    for name in ("knowledge", "analytics", "hybrid", "dashboard", "report")
                }
                router = AgentRouter(
                    classifier,
                    agents["knowledge"],
                    agents["analytics"],
                    agents["hybrid"],
                    agents["dashboard"],
                    report_agent=agents["report"],
                )
                result = router.route(AgentRequest(question=question))
                self.assertEqual(result.agent, selected_agent)
                agents[selected_agent].run.assert_called_once()
                for name, agent in agents.items():
                    if name != selected_agent:
                        agent.run.assert_not_called()

    def test_report_rejects_unprovided_citation_ids(self):
        hybrid = Mock()
        source = AgentResult(answer="A source answer [S1]", agent="hybrid", evidence=[
            Evidence(citation_id="S1", source_type="document", source="report", content="Revenue data")
        ])
        hybrid.run.return_value = source
        llm = Mock()
        llm.generate.return_value = "Unsupported figure [S9]"
        result = ReportAgent(knowledge=hybrid, llm=llm).run(AgentRequest(question="summarize report"))
        self.assertEqual(result.answer, "The answer was withheld because it could not be validated against the verified evidence. Please retry the question.")
        self.assertEqual(result.agent, "report")
        self.assertTrue(result.metadata["citation_validation_failed"])
        self.assertEqual(llm.generate.call_count, 2)

    def test_report_repairs_one_missing_citation_without_weakening_validation(self):
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[
            Evidence(
                citation_id="S1", source_type="document", source="annual report, page 12",
                content="The report describes the company's strategy and initiatives.",
            )
        ])
        llm = Mock()
        llm.generate.side_effect = [
            "The report describes its strategy.",
            "The report describes its strategy [S1].",
        ]

        result = ReportAgent(knowledge=knowledge, llm=llm).run(
            AgentRequest(question="Summarize the strategy")
        )

        self.assertEqual(result.answer, "The report describes its strategy [S1].")
        self.assertTrue(result.metadata["citation_repair_attempted"])
        self.assertEqual(llm.generate.call_count, 2)
        self.assertIn("missing_or_unknown_citations", llm.generate.call_args.args[0])

    def test_executive_report_distinguishes_documented_initiatives_from_inferred_risks(self):
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="Source passages", agent="knowledge", evidence=[
            Evidence(
                citation_id="S1", source_type="document", source="2025 report, page 104",
                content="The company reported leadership training and a 360-degree assessment.",
            )
        ])
        llm = Mock()
        llm.generate.return_value = "The report describes leadership training and a 360-degree assessment [S1]."

        result = ReportAgent(knowledge=knowledge, llm=llm).run(
            AgentRequest(question="Summarize the options and risks for leadership")
        )

        prompt = llm.generate.call_args.args[0]
        self.assertIn("distinguish report-stated initiatives from actual alternatives", prompt)
        self.assertIn("List a risk only when the cited evidence explicitly identifies it", prompt)
        self.assertIn("say so clearly", prompt)
        self.assertEqual(result.agent, "report")

    def test_financial_change_report_combines_metric_rows_and_cited_causes(self):
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[
            Evidence(citation_id="S1", source_type="document", source="2021 annual report, p. 55",
                     content="The company expanded dairy farms and invested in a new production facility.")
        ])
        analytics = Mock()
        analytics.run.return_value = AgentResult(answer="", agent="analytics", evidence=[
            Evidence(citation_id="M1", source_type="verified_metric", source="Example Retailer 2021 · Total assets",
                     content="Total assets increased from 10 to 12 billion VND.",
                     metadata={"metric_name": "total_assets", "fiscal_year": 2021})
        ], data={"financial": []})
        llm = Mock()
        llm.generate.return_value = "Tổng tài sản tăng từ 10 lên 12 tỷ đồng [M1]. Báo cáo nêu công ty đầu tư cơ sở sản xuất [S1], nhưng không xác nhận đây là nguyên nhân trực tiếp."

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question="tại sao total assets của 2021 lại tăng so với 2020")
        )

        analytics.run.assert_called_once()
        self.assertIn("do not establish why", llm.generate.call_args.args[0])
        self.assertIn("[S1]", result.answer)
        self.assertIn("[M1]", result.answer)
        self.assertEqual({item.citation_id for item in result.evidence}, {"S1", "M1"})

    def test_report_financial_summary_uses_matching_metric_without_inventing_reconciliation(self):
        hybrid = Mock()
        hybrid.run.return_value = AgentResult(answer="Revenue [S1]", agent="hybrid", evidence=[
            Evidence(citation_id="S1", source_type="document", source="report", content="Audited-statement revenue 32.6T"),
            Evidence(citation_id="S7", source_type="document", source="report", content="Headline total consolidated revenue 18.624T and consolidated profit after tax 2.453T"),
        ])
        llm = Mock()
        llm.generate.return_value = "Example Retailer reported total consolidated revenue of 18.624 trillion VND and consolidated profit after tax of 2.453 trillion VND [1]."
        result = ReportAgent(knowledge=hybrid, llm=llm).run(AgentRequest(question="Summarize revenue and profit"))
        self.assertIn("18.624T", llm.generate.call_args.args[0])
        self.assertIn("return exactly two concise bullets", llm.generate.call_args.args[0])
        self.assertIn("do not invent an accounting basis or reconciliation", llm.generate.call_args.args[0])
        self.assertIn("never convert or rescale values", llm.generate.call_args.args[0])
        self.assertIn("tỷ to triệu", llm.generate.call_args.args[0])
        self.assertNotIn("Include both headline and statement figures for every requested metric", llm.generate.call_args.args[0])
        self.assertIn("Vietnamese periods group thousands", llm.generate.call_args.args[0])
        self.assertIn("Priority IDs: [S7]", llm.generate.call_args.args[0])
        self.assertEqual(result.answer, "Example Retailer reported total consolidated revenue of 18.624 trillion VND and consolidated profit after tax of 2.453 trillion VND [S7].")
        self.assertTrue(hybrid.run.call_args.args[0].metadata["evidence_only"])

    def test_financial_report_rejects_rescaled_or_rounded_cited_values(self):
        evidence = [Evidence(
            citation_id="S3", source_type="document", source="annual report",
            content="Total consolidated revenue 2024; profit after tax 2024; tỷ đồng tỷ đồng 2.453 18.624",
        )]

        self.assertTrue(_financial_facts_match_cited_evidence(
            "Revenue 18.624 tỷ đồng and profit 2.453 tỷ đồng [S3]", evidence,
        ))
        self.assertFalse(_financial_facts_match_cited_evidence(
            "Revenue 18.624 triệu đồng and profit 2.453 triệu đồng [S3]", evidence,
        ))
        self.assertFalse(_financial_facts_match_cited_evidence(
            "Revenue 61.8 tỷ đồng and profit 2.453 tỷ đồng [S3]", evidence,
        ))
        self.assertFalse(_financial_facts_match_cited_evidence(
            "Revenue 18.624 billion USD and profit 2.453 billion USD [S3]", evidence,
        ))

    def test_report_withholds_a_financial_answer_with_a_cited_unit_mismatch(self):
        hybrid = Mock()
        hybrid.run.return_value = AgentResult(answer="Revenue [S1]", agent="hybrid", evidence=[
            Evidence(
                citation_id="S1", source_type="document", source="annual report",
                content="Revenue 2024; profit 2024; tỷ đồng tỷ đồng 2.453 18.624",
            )
        ])
        llm = Mock()
        llm.generate.return_value = "Revenue 18.624 triệu đồng and profit 2.453 triệu đồng [S1]"

        result = ReportAgent(knowledge=hybrid, llm=llm).run(
            AgentRequest(question="Summarize revenue and profit")
        )

        self.assertTrue(result.metadata["financial_evidence_validation_failed"])
        self.assertEqual(result.agent, "report")
        self.assertIn("withheld", result.answer)

    def test_numeric_report_citations_map_to_prompt_evidence_and_reject_out_of_range(self):
        evidence = [
            Evidence(citation_id="S1", source_type="document", source="report"),
            Evidence(citation_id="S7", source_type="document", source="report"),
        ]
        answer = _normalize_numeric_citations("Headline 【2】, audited [1], year [2024], invalid [3]", evidence)
        self.assertEqual(answer, "Headline [S7], audited [S1], year [2024], invalid [3]")

if __name__ == "__main__":
    unittest.main()
