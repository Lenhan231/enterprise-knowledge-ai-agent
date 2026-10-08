import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.agents.evaluate_commerce_decision_support import (
    load_cases, missing_gold_numeric_facts, missing_gold_observations, score_case,
)


ROOT = Path(__file__).resolve().parents[1]


class CommerceDecisionEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.benchmark = json.loads((ROOT / "data/evaluation/commerce_decision_benchmark.json").read_text())
        cls.cases = load_cases(cls.benchmark)

    def test_benchmark_covers_all_three_commerce_decision_domains(self):
        self.assertEqual(len(self.cases), 9)
        self.assertEqual({case["domain"] for case in self.cases}, {
            "inventory_allocation", "promotion_planning", "nationwide_logistics",
        })
        self.assertTrue(all(case.get("gold_observations") and case.get("expected_behavior") for case in self.cases))

    def test_composite_policy_and_sql_answer_passes_mechanical_checks(self):
        case = next(case for case in self.cases if case["id"] == "INV-01")
        payload = {
            "answer": "Snapshot stockout counts were Streetwear=134 and Outdoor=95 [C1]. 232 rows carried both flags [C2]. Chưa điều chuyển tồn kho until SKU-level validation [S1].",
            "token_usage": {
                "sql_generation": {"input_tokens": 80, "output_tokens": 14, "total_tokens": 94},
                "answer_generation": {"input_tokens": 120, "output_tokens": 25, "total_tokens": 145},
                "total": {"input_tokens": 200, "output_tokens": 39, "total_tokens": 239},
            },
            "citations": [
                {"id": "C1", "source_type": "commerce_sql", "commerce_domain": "inventory_allocation",
                 "source_tables": ["commerce.inventory"], "dataset_note": "Synthetic Kaggle Commerce data.",
                 "sql_query": "SELECT i.category, COUNT(*) FROM commerce.inventory i GROUP BY i.category",
                 "sql_generation_provider": "groq", "commerce_observations": [
                     {"snapshot_date": "2022-12-31", "category": "Streetwear", "products": 196,
                      "stockout_count": 134, "overstock_count": 162},
                     {"snapshot_date": "2022-12-31", "category": "Outdoor", "products": 144,
                      "stockout_count": 95, "overstock_count": 113},
                 ]},
                {"id": "C2", "source_type": "commerce_sql", "commerce_domain": "inventory_allocation",
                 "source_tables": ["commerce.inventory"], "dataset_note": "Synthetic Kaggle Commerce data.",
                 "sql_query": "SELECT COUNT(*) FILTER (WHERE i.stockout_flag AND i.overstock_flag) AS both_flagged_rows FROM commerce.inventory i"},
                {"id": "S1", "source_type": "document", "document_id": "CD-POL-INV-001",
                 "page_number": 2, "evidence_class": "company_policy_reference",
                 "reference_applicability": "Synthetic demo policy only."},
            ],
        }

        result = score_case(case, payload, {"commerce.inventory", "commerce.products"})

        self.assertTrue(result["passed"], result["checks"])
        self.assertTrue(result["gold_observation_coverage_passed"])
        self.assertEqual(result["token_usage"]["total"]["total_tokens"], 239)

    def test_inv01_snapshot_answer_does_not_require_second_generated_query(self):
        case = next(case for case in self.cases if case["id"] == "INV-01")
        payload = {
            "answer": (
                "Trong snapshot mới nhất, stockout: Streetwear 134; Outdoor 95 [C2]. "
                "232 sản phẩm có cả hai cờ [C3]. Chưa điều chuyển tồn kho khi chưa có đối chiếu SKU và nhu cầu [L1][S1]."
            ),
            "citations": [
                {"id": "C2", "source_type": "commerce_sql", "commerce_domain": "inventory_allocation",
                 "commerce_observation_group": "inventory_latest_by_category",
                 "commerce_observations": [
                     {"snapshot_date": "2022-12-31", "category": "Streetwear", "stockout_products": 134},
                     {"snapshot_date": "2022-12-31", "category": "Outdoor", "stockout_products": 95},
                 ], "source_tables": ["commerce.inventory"],
                 "dataset_note": "Synthetic Kaggle Commerce data."},
                {"id": "C3", "source_type": "commerce_sql", "commerce_domain": "inventory_allocation",
                 "commerce_observation_group": "inventory_latest_flag_overlap",
                 "commerce_observations": [{"snapshot_date": "2022-12-31", "both_flagged_rows": 232}],
                 "source_tables": ["commerce.inventory"],
                 "dataset_note": "Synthetic Kaggle Commerce data."},
                {"id": "L1", "source_type": "commerce_schema", "commerce_domain": "inventory_allocation"},
                {"id": "S1", "source_type": "document", "document_id": "CD-POL-INV-001",
                 "page_number": 2, "evidence_class": "company_policy_reference",
                 "reference_applicability": "Synthetic demo policy only."},
            ],
        }

        result = score_case(case, payload, {"commerce.inventory", "commerce.products"})

        self.assertTrue(result["passed"], result["checks"])
        self.assertFalse(result["question_specific_sql_used"])

    def test_log01_snapshot_answer_abstains_from_network_redesign(self):
        case = next(case for case in self.cases if case["id"] == "LOG-01")
        observations = [
            {"year": 2022, "region": "Central", "deliveries": 9593, "avg_transit_days": 4.51,
             "median_transit_days": 5.0, "avg_shipping_fee": 4.10},
            {"year": 2022, "region": "East", "deliveries": 14120, "avg_transit_days": 4.52,
             "median_transit_days": 5.0, "avg_shipping_fee": 3.98},
            {"year": 2022, "region": "West", "deliveries": 7054, "avg_transit_days": 4.51,
             "median_transit_days": 5.0, "avg_shipping_fee": 3.89},
        ]
        payload = {
            "answer": (
                "East có average transit time cao nhất: 4.52 ngày, so với 4.51 ở Central và West [C1]. Chưa thiết kế lại mạng lưới giao hàng; "
                "cần điểm đi/đến, carrier, SLA và năng lực tuyến trước khi quyết định [L1][S1]."
            ),
            "citations": [
                {"id": "C1", "source_type": "commerce_sql", "commerce_domain": "nationwide_logistics",
                 "source_tables": ["commerce.shipments", "commerce.orders", "commerce.geography"],
                 "dataset_note": "Synthetic Kaggle Commerce data.", "commerce_observations": observations},
                {"id": "L1", "source_type": "commerce_schema", "commerce_domain": "nationwide_logistics"},
                {"id": "S1", "source_type": "document", "document_id": "LOG-REFERENCE",
                 "page_number": 2, "evidence_class": "company_practice_reference",
                 "reference_applicability": "External example only."},
            ],
        }

        result = score_case(case, payload, set(self.benchmark["domains"]["nationwide_logistics"]["source_tables"]))

        self.assertTrue(result["passed"], result["checks"])
        self.assertFalse(result["question_specific_sql_used"])

    def test_numeric_values_in_answer_do_not_pass_when_sql_rows_swap_category_values(self):
        case = next(case for case in self.cases if case["id"] == "INV-01")
        citations = [{
            "id": "C1", "source_type": "commerce_sql", "commerce_domain": "inventory_allocation",
            "source_tables": ["commerce.inventory"], "dataset_note": "Synthetic Kaggle Commerce data.",
            "commerce_observations": [
                {"snapshot_date": "2022-12-31", "category": "Streetwear", "products": 196,
                 "stockout_count": 95, "overstock_count": 162},
                {"snapshot_date": "2022-12-31", "category": "Outdoor", "products": 144,
                 "stockout_count": 134, "overstock_count": 113},
            ],
        }, {
            "id": "C2", "source_type": "commerce_sql", "commerce_domain": "inventory_allocation",
            "source_tables": ["commerce.inventory"], "dataset_note": "Synthetic Kaggle Commerce data.",
        }, {
            "id": "S1", "source_type": "document", "document_id": "policy",
            "page_number": 2, "evidence_class": "company_policy_reference",
            "reference_applicability": "Synthetic demo only.",
        }]

        missing = missing_gold_observations(case, citations)
        result = score_case(case, {
            "answer": "Streetwear=134, Outdoor=95, overlap=232 [C1][C2][S1].",
            "citations": citations,
        }, {"commerce.inventory", "commerce.products"})

        self.assertEqual(len(missing), 2)
        self.assertTrue(result["gold_numeric_coverage_passed"])
        self.assertFalse(result["gold_observation_coverage_passed"])

    def test_gold_observations_accept_live_group_category_sql_alias(self):
        case = next(case for case in self.cases if case["id"] == "INV-01")
        citation = {
            "source_type": "commerce_sql",
            "sql_query": "SELECT ... WHERE i.snapshot_date = '2022-12-31' GROUP BY i.category",
            "commerce_observations": [
                {"group_category": "Streetwear", "stockout_count": 134, "overstock_count": 162},
                {"group_category": "Outdoor", "stockout_count": 95, "overstock_count": 113},
            ],
        }

        self.assertEqual(missing_gold_observations(case, [citation]), [])

    def test_gold_observation_evaluator_flattens_yearly_region_measure_rows(self):
        case = next(case for case in self.cases if case["id"] == "LOG-02")
        sql_rows = [
            {"region": region, "year": year, "avg_transit_days": days, "avg_shipping_fee": fee}
            for region, values in {
                "Central": [(2020, 4.51, 4.17), (2021, 4.52, 4.13), (2022, 4.51, 4.10)],
                "East": [(2020, 4.50, 4.27), (2021, 4.51, 4.07), (2022, 4.52, 3.98)],
                "West": [(2020, 4.51, 4.11), (2021, 4.50, 4.36), (2022, 4.51, 3.89)],
            }.items()
            for year, days, fee in values
        ]

        self.assertEqual(missing_gold_observations(case, [{
            "source_type": "commerce_sql", "commerce_observations": sql_rows,
        }]), [])

    def test_log02_numeric_gold_matches_endpoint_only_answer_contract(self):
        case = next(case for case in self.cases if case["id"] == "LOG-02")
        answer = (
            "FY2020 4.51 and 4.17 → FY2022 4.51 and 4.10; "
            "FY2020 4.50 and 4.27 → FY2022 4.52 and 3.98; "
            "FY2020 4.51 and 4.11 → FY2022 4.51 and 3.89."
        )

        self.assertEqual(missing_gold_numeric_facts(case, answer), [])

    def test_gold_observations_accept_year_proven_by_single_year_sql_filter(self):
        case = next(case for case in self.cases if case["id"] == "LOG-01")
        citation = {
            "source_type": "commerce_sql",
            "sql_query": (
                "SELECT g.region, AVG(s.delivery_date - s.ship_date) AS avg_transit_time_days "
                "FROM commerce.shipments s JOIN commerce.orders o ON s.order_id = o.order_id "
                "JOIN commerce.geography g ON o.zip = g.zip "
                "WHERE EXTRACT(YEAR FROM s.delivery_date) = 2022 "
                "GROUP BY g.region ORDER BY avg_transit_time_days DESC LIMIT 100"
            ),
            "commerce_observations": [
                {"region": "East", "avg_transit_time_days": "4.5200424929"},
                {"region": "Central", "avg_transit_time_days": "4.5137079120"},
                {"region": "West", "avg_transit_time_days": "4.5099234476"},
            ],
        }

        self.assertEqual(missing_gold_observations(case, [citation]), [])

    def test_gold_observations_accept_snapshot_date_proven_by_sql_filter(self):
        case = next(case for case in self.cases if case["id"] == "INV-01")
        citation = {
            "source_type": "commerce_sql",
            "sql_query": (
                "SELECT i.category, COUNT(*) FILTER (WHERE i.stockout_flag) AS stockout_count "
                "FROM commerce.inventory i WHERE i.snapshot_date = '2022-12-31' "
                "GROUP BY i.category"
            ),
            "commerce_observations": [
                {"category": "Streetwear", "stockout_count": 134},
                {"category": "Outdoor", "stockout_count": 95},
            ],
        }

        self.assertEqual(missing_gold_observations(case, [citation]), [])

    def test_year_is_not_inferred_from_a_mixed_year_or_predicate(self):
        case = next(case for case in self.cases if case["id"] == "LOG-01")
        citation = {
            "source_type": "commerce_sql",
            "sql_query": (
                "SELECT g.region, AVG(s.delivery_date - s.ship_date) AS avg_transit_time_days "
                "FROM commerce.shipments s JOIN commerce.geography g ON TRUE "
                "WHERE EXTRACT(YEAR FROM s.delivery_date) = 2022 OR g.region = 'East' "
                "GROUP BY g.region"
            ),
            "commerce_observations": [
                {"region": "East", "avg_transit_time_days": "4.5200424929"},
            ],
        }

        self.assertTrue(missing_gold_observations(case, [citation]))

    def test_gold_observation_evaluator_accepts_schema_aliases_and_campaign_year_label(self):
        inventory_case = next(case for case in self.cases if case["id"] == "INV-02")
        inventory_rows = [
            {"year": 2020, "total_snapshots": 5686, "stockout_snapshots": 3795, "avg_fill_rate": 0.9656},
            {"year": 2021, "total_snapshots": 5609, "stockout_snapshots": 3788, "avg_fill_rate": 0.9619},
            {"year": 2022, "total_snapshots": 5232, "stockout_snapshots": 3490, "avg_fill_rate": 0.9635},
        ]
        self.assertEqual(missing_gold_observations(inventory_case, [{
            "source_type": "commerce_sql", "commerce_observations": inventory_rows,
        }]), [])

        promotion_case = next(case for case in self.cases if case["id"] == "PROMO-02")
        promotion_rows = [
            {"promo_name": "Spring Sale 2022", "net_sales": 90345105.91},
            {"promo_name": "Fall Launch 2022"},
            {"promo_name": "Mid-Year Sale 2022"},
        ]
        self.assertEqual(missing_gold_observations(promotion_case, [{
            "source_type": "commerce_sql", "commerce_observations": promotion_rows,
        }]), [])

        logistics_case = next(case for case in self.cases if case["id"] == "LOG-02")
        logistics_rows = [
            {"region": "Central", "year": 2020, "avg_transit_time": 4.5103, "avg_shipping_fee": 4.1748},
            {"region": "Central", "year": 2021, "avg_transit_time": 4.5160, "avg_shipping_fee": 4.1266},
            {"region": "Central", "year": 2022, "avg_transit_time": 4.5137, "avg_shipping_fee": 4.1010},
            {"region": "East", "year": 2020, "avg_transit_time": 4.5039, "avg_shipping_fee": 4.2673},
            {"region": "East", "year": 2021, "avg_transit_time": 4.5099, "avg_shipping_fee": 4.0739},
            {"region": "East", "year": 2022, "avg_transit_time": 4.5200, "avg_shipping_fee": 3.9791},
            {"region": "West", "year": 2020, "avg_transit_time": 4.5067, "avg_shipping_fee": 4.1145},
            {"region": "West", "year": 2021, "avg_transit_time": 4.4980, "avg_shipping_fee": 4.3564},
            {"region": "West", "year": 2022, "avg_transit_time": 4.5099, "avg_shipping_fee": 3.8925},
        ]
        self.assertEqual(missing_gold_observations(logistics_case, [{
            "source_type": "commerce_sql", "commerce_observations": logistics_rows,
        }]), [])

    def test_inventory_category_gold_matches_group_label_from_live_sql(self):
        case = next(case for case in self.cases if case["id"] == "INV-01")
        rows = [
            {"snapshot_date": "2022-12-31", "group_label": "Streetwear", "stockout_count": 134},
            {"snapshot_date": "2022-12-31", "group_label": "Outdoor", "stockout_count": 95},
        ]
        self.assertEqual(missing_gold_observations(case, [{
            "source_type": "commerce_sql", "commerce_observations": rows,
        }]), [])

    def test_promo01_accepts_generated_measure_aliases_without_losing_grouping(self):
        case = next(case for case in self.cases if case["id"] == "PROMO-01")
        rows = [
            {"year": year, "used_promotion": used, "delivered_orders": orders,
             "total_quantity": units, "net_sales": sales, "total_discount": discounts}
            for year, used, orders, units, sales, discounts in [
                (2020, False, 17670, 84029, 570817418.55, 0.0),
                (2020, True, 10305, 49756, 235597280.59, 39488236.40),
                (2021, False, 14928, 70747, 493703251.83, 0.0),
                (2021, True, 11824, 56795, 272380807.80, 39846428.26),
                (2022, False, 17515, 82665, 615242495.15, 0.0),
                (2022, True, 10173, 48768, 245344841.20, 41728464.79),
            ]
        ]

        missing = missing_gold_observations(case, [{
            "source_type": "commerce_sql", "commerce_observations": rows,
        }])

        self.assertEqual(missing, [])

    def test_schema_gap_gold_observations_do_not_require_sql_rows(self):
        case = next(case for case in self.cases if case["id"] == "INV-03")

        result = score_case(case, {
            "answer": "No location dimension is available [L1].",
            "citations": [{"id": "L1", "source_type": "commerce_schema"}],
        }, {"commerce.inventory"})

        self.assertFalse(result["gold_observation_coverage_applicable"])
        self.assertIsNone(result["gold_observation_coverage_passed"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["operating_reference_present"])

    def test_expected_schema_gap_passes_with_schema_and_operating_citations_without_sql(self):
        case = next(case for case in self.cases if case["id"] == "INV-03")
        payload = {
            "answer": "Chưa đủ dữ liệu theo vùng để kết luận [L1]. Policy giả lập yêu cầu đối chiếu SKU và nhu cầu trước khi điều chuyển [S1].",
            "question_sql_fallback": "requested_dimension_unavailable",
            "citations": [
                {"id": "L1", "source_type": "commerce_schema", "commerce_domain": "inventory_allocation"},
                {"id": "S1", "source_type": "document", "document_id": "CD-POL-INV-001",
                 "page_number": 2, "evidence_class": "company_policy_reference",
                 "reference_applicability": "Fictional demo policy only."},
            ],
        }

        result = score_case(case, payload, {"commerce.inventory"})

        self.assertTrue(result["passed"], result["checks"])
        self.assertFalse(result["question_specific_sql_used"])
        self.assertTrue(result["checks"]["question_specific_sql_requirement_met"])

    def test_promo03_requires_roi_abstention_and_rejects_roi_as_a_numeric_sql_measure(self):
        case = next(case for case in self.cases if case["id"] == "PROMO-03")
        payload = {
            "answer": "Không thể tính ROI khi thiếu chi phí chiến dịch và holdout [C1][L1][S1].",
            "question_sql_fallback": "unsupported_measure",
            "citations": [
                {"id": "C1", "source_type": "commerce_sql", "commerce_domain": "promotion_planning",
                 "source_tables": ["commerce.promotions", "commerce.orders", "commerce.order_items"],
                 "dataset_note": "Synthetic Kaggle Commerce data."},
                {"id": "L1", "source_type": "commerce_schema", "commerce_domain": "promotion_planning"},
                {"id": "S1", "source_type": "document", "document_id": "CD-POL-PROMO-001",
                 "page_number": 2, "evidence_class": "company_policy_reference",
                 "reference_applicability": "Synthetic demo policy only."},
            ],
        }

        result = score_case(case, payload, {
            "commerce.promotions", "commerce.orders", "commerce.order_items", "commerce.products",
        })
        self.assertTrue(result["passed"], result["checks"])
        self.assertFalse(result["question_specific_sql_used"])

        payload["answer"] = "| Channel | ROI |\n| email | 8.28 | [C1][L1][S1]"
        result = score_case(case, payload, {
            "commerce.promotions", "commerce.orders", "commerce.order_items", "commerce.products",
        })
        self.assertFalse(result["checks"]["answer_contract"])
        self.assertFalse(result["passed"])

    def test_promo02_ranking_contract_rejects_unsolicited_recommendation(self):
        case = next(case for case in self.cases if case["id"] == "PROMO-02")
        payload = {"answer": "Spring Sale 2022 ranked first by tagged net sales [C1]."}
        result = score_case(case, payload, {"commerce.promotions", "commerce.orders", "commerce.order_items"})
        self.assertTrue(result["checks"]["answer_contract"])

        payload["answer"] = "Spring Sale 2022 ranked first [C1]. Khuyến nghị: tăng ngân sách."
        result = score_case(case, payload, {"commerce.promotions", "commerce.orders", "commerce.order_items"})
        self.assertFalse(result["checks"]["answer_contract"])

    def test_inv01_numeric_coverage_detects_missing_flag_overlap_fact(self):
        case = next(case for case in self.cases if case["id"] == "INV-01")

        self.assertEqual(missing_gold_numeric_facts(case, "Streetwear=134, Outdoor=95"), ["232"])

    def test_required_policy_reference_and_correct_domain_are_checked(self):
        case = next(case for case in self.cases if case["id"] == "INV-01")
        payload = {
            "answer": "Inventory counts [C1].",
            "citations": [{
                "id": "C1", "source_type": "commerce_sql", "commerce_domain": "promotion_planning",
                "source_tables": ["commerce.inventory"], "dataset_note": "Synthetic Kaggle Commerce data.",
            }],
        }

        result = score_case(case, payload, {"commerce.inventory", "commerce.products"})

        self.assertFalse(result["checks"]["domain_sql_evidence"])
        self.assertFalse(result["checks"]["operating_reference_present"])

    def test_score_records_snapshot_fallback_reason_separately_from_answer_provider(self):
        case = next(case for case in self.cases if case["id"] == "INV-03")
        payload = {
            "answer": "Do not rebalance without location-level inventory and destination demand [C1][S1].",
            "question_sql_fallback": "provider_rate_limited",
            "generation_provider": "deterministic_safety_fallback",
            "citations": [
                {"id": "C1", "source_type": "commerce_sql", "commerce_domain": "inventory_allocation",
                 "source_tables": ["commerce.inventory"], "dataset_note": "Synthetic Kaggle Commerce data."},
                {"id": "S1", "source_type": "document", "document_id": "CD-POL-INV-001",
                 "page_number": 2, "evidence_class": "company_policy_reference",
                 "reference_applicability": "Synthetic demo policy only."},
            ],
        }

        result = score_case(case, payload, {"commerce.inventory", "commerce.products"})

        self.assertEqual(result["question_sql_fallback"], "provider_rate_limited")
        self.assertEqual(result["answer_generation_provider"], "deterministic_safety_fallback")
        self.assertFalse(result["question_specific_sql_used"])

    def test_non_decision_descriptive_case_does_not_require_policy_citation(self):
        case = next(case for case in self.cases if case["id"] == "LOG-02")
        observations = [
            {"region": region, "year": year, "avg_transit_days": days, "avg_shipping_fee": fee}
            for region, values in {
                "Central": [(2020, 4.51, 4.17), (2021, 4.52, 4.13), (2022, 4.51, 4.10)],
                "East": [(2020, 4.50, 4.27), (2021, 4.51, 4.07), (2022, 4.52, 3.98)],
                "West": [(2020, 4.51, 4.11), (2021, 4.50, 4.36), (2022, 4.51, 3.89)],
            }.items()
            for year, days, fee in values
        ]
        result = score_case(case, {"answer": (
            "Central: 2020 4.51/4.17, 2021 4.52/4.13, 2022 4.51/4.10; "
            "East: 2020 4.50/4.27, 2021 4.51/4.07, 2022 4.52/3.98; "
            "West: 2020 4.51/4.11, 2021 4.50/4.36, 2022 4.51/3.89 [C1]."
        ), "citations": [
            {"id": "C1", "source_type": "commerce_sql", "commerce_domain": "nationwide_logistics",
             "source_tables": ["commerce.shipments"], "dataset_note": "Synthetic Kaggle Commerce data.",
             "sql_query": "SELECT EXTRACT(YEAR FROM s.ship_date) FROM commerce.shipments s",
             "sql_generation_provider": "huggingface_inference",
             "commerce_observations": observations},
        ]}, {"commerce.shipments", "commerce.orders", "commerce.geography"})

        self.assertTrue(result["passed"], result["checks"])

    def test_snapshot_fallback_separates_grounding_from_sql_generation(self):
        case = next(case for case in self.cases if case["id"] == "LOG-03")
        result = score_case(case, {
            "answer": "Chưa đủ dữ liệu theo năng lực tuyến để quyết định chuyển vùng [L1]. Policy logistics giả lập yêu cầu kiểm tra tuyến, SLA, năng lực và chi phí trước khi điều chỉnh [S1].",
            "question_sql_fallback": "requested_dimension_unavailable",
            "citations": [
                {"id": "L1", "source_type": "commerce_schema", "commerce_domain": "nationwide_logistics"},
                {"id": "S1", "source_type": "document", "document_id": "CD-POL-LOG-001",
                 "page_number": 2, "evidence_class": "company_policy_reference",
                 "reference_applicability": "Synthetic demo policy only."},
            ],
        }, {"commerce.shipments", "commerce.orders", "commerce.geography"})

        self.assertFalse(result["checks"]["question_specific_sql_available"])
        self.assertTrue(result["checks"]["question_specific_sql_requirement_met"])
        self.assertTrue(result["citation_domain_checks_passed"])
        self.assertFalse(result["question_specific_sql_passed"])
        self.assertTrue(result["passed"], result["checks"])

    def test_optional_question_sql_may_include_a_cited_diagnostic_query(self):
        case = next(case for case in self.cases if case["id"] == "LOG-03")
        result = score_case(case, {
            "answer": "Regional transit observations are diagnostic only [C1]. The schema lacks route capacity [L1]; use the cited routing method only after collecting lane-level evidence [S1].",
            "citations": [
                {"id": "C1", "source_type": "commerce_sql", "commerce_domain": "nationwide_logistics",
                 "source_tables": ["commerce.shipments", "commerce.orders", "commerce.geography"],
                 "sql_query": "SELECT g.region, AVG(s.delivery_date - s.ship_date) FROM commerce.shipments s JOIN commerce.orders o ON s.order_id = o.order_id JOIN commerce.geography g ON o.zip = g.zip GROUP BY g.region",
                 "dataset_note": "Synthetic Kaggle Datathon 2026 Commerce data."},
                {"id": "L1", "source_type": "commerce_schema", "commerce_domain": "nationwide_logistics"},
                {"id": "S1", "source_type": "document", "document_id": "CD-POL-LOG-001",
                 "page_number": 2, "evidence_class": "company_policy_reference",
                 "reference_applicability": "Synthetic demo policy only."},
            ],
        }, {"commerce.shipments", "commerce.orders", "commerce.geography"})

        self.assertTrue(result["checks"]["question_specific_sql_available"])
        self.assertTrue(result["checks"]["question_specific_sql_requirement_met"])
        self.assertTrue(result["checks"]["domain_sql_evidence"])
        self.assertTrue(result["passed"], result["checks"])

    def test_precomputed_promotion_aggregate_is_valid_without_question_sql(self):
        case = next(case for case in self.cases if case["id"] == "PROMO-01")
        result = score_case(case, {
            "answer": "Observed annual groups are compared here [C1].",
            "citations": [{
                "id": "C1", "source_type": "commerce_sql",
                "commerce_domain": "promotion_planning",
                "source_tables": ["commerce.orders", "commerce.order_items", "commerce.products"],
                "dataset_note": "Synthetic Kaggle Commerce data.",
                "commerce_observations": [{"year": 2020, "used_promotion": True}],
            }],
        }, {"commerce.orders", "commerce.order_items", "commerce.products", "commerce.promotions"})

        self.assertFalse(result["checks"]["question_specific_sql_available"])
        self.assertTrue(result["checks"]["question_specific_sql_requirement_met"])
        self.assertTrue(result["checks"]["domain_sql_evidence"])

    def test_gold_numeric_coverage_accepts_vietnamese_number_format(self):
        case = {"required_numeric_facts": [235597280.59, 0.9656, 10305]}

        self.assertEqual(
            missing_gold_numeric_facts(case, "Doanh thu 235.597.280,59; fill rate 0,9656; orders 10,305."),
            [],
        )

    def test_gold_numeric_coverage_accepts_thin_space_grouping(self):
        case = {"required_numeric_facts": ["90345105.91"]}

        self.assertEqual(
            missing_gold_numeric_facts(case, "90\u202f345\u202f105.91 USD"),
            [],
        )

    def test_gold_numeric_coverage_reports_omitted_required_measure(self):
        case = {"required_numeric_facts": [10305, 235597280.59, 39488236.4]}

        self.assertEqual(
            missing_gold_numeric_facts(case, "orders=10,305; sales=235597280.59"),
            ["39488236.4"],
        )

    def test_gold_numeric_coverage_uses_precision_declared_by_benchmark(self):
        case = {"required_numeric_facts": ["4.51", "4.52"]}

        self.assertEqual(missing_gold_numeric_facts(case, "4.5114567133 4.515"), [])
        self.assertEqual(missing_gold_numeric_facts(case, "4.5114567133 4.5085324232"), ["4.52"])


if __name__ == "__main__":
    unittest.main()
