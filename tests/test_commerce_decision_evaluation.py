import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agents.evaluate_commerce_decision_support import (
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
            "answer": "Snapshot stockout counts were Streetwear=134 and Outdoor=95 [C1]. 232 rows carried both flags [C2]. Do not transfer stock before validation [S1].",
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
            {"year": 2020, "sku_snapshots": 5686, "stockout_snapshots": 3795, "avg_fill_rate": 0.9656},
            {"year": 2021, "sku_snapshots": 5609, "stockout_snapshots": 3788, "avg_fill_rate": 0.9619},
            {"year": 2022, "sku_snapshots": 5232, "stockout_snapshots": 3490, "avg_fill_rate": 0.9635},
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
