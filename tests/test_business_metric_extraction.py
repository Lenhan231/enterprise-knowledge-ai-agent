import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.analytics.business_metric_extraction import (
    build_business_metric_extraction_run,
    extract_business_metric_candidates,
    select_business_metric_chunks,
)
from core.analytics.business_metric_catalog import BUSINESS_DECISION_PROFILES, BUSINESS_METRIC_CATALOG


class FakeLLM:
    model_name = "test-model"

    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.response, list):
            return self.response.pop(0)
        return self.response


class BusinessMetricExtractionTests(unittest.TestCase):
    def setUp(self):
        self.page = "Dairy cattle managed by Vinamilk reached 130,000 cows in 2024."
        self.chunks = [{
            "text": self.page,
            "metadata": {"page_number": 6, "chunk_index": 3,
                         "section_title": "Milk supply", "layout_type": "table"},
        }]
        self.document = {
            "company": "Vinamilk", "document_id": "UPLOAD-1", "fiscal_year": 2024,
            "business_decision_domain": "milk_supply",
            "source_url": "https://example.org/report.pdf",
            "rbac": {"allowed_roles": ["admin"]},
        }

    def test_primary_metrics_belong_to_their_decision_profile_domain(self):
        for domain, profile in BUSINESS_DECISION_PROFILES.items():
            for metric_name in profile["primary_metrics"]:
                self.assertIn(metric_name, BUSINESS_METRIC_CATALOG)
                self.assertEqual(BUSINESS_METRIC_CATALOG[metric_name]["domain"], domain)
        self.assertIn(
            "market_share_lead_over_runner_up",
            BUSINESS_DECISION_PROFILES["market_performance"]["primary_metrics"],
        )

    def test_sends_parser_table_chunk_to_model_and_keeps_catalog_key(self):
        tables = [{
            "page_number": 6, "table_index": 2,
            "context": {"table_title": "Milk supply indicators"},
        }]
        table_chunk = {
            "text": "Columns: Metric | 2024\nRow 1: Metric: Dairy cattle managed | 2024: 130,000 cows",
            "metadata": {"page_number": 6, "chunk_index": 4, "table_index": 2,
                         "layout_type": "table", "section_title": "Milk supply"},
        }
        selected = select_business_metric_chunks([*self.chunks, table_chunk], tables)
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["layout_type"], "table")
        llm = FakeLLM(json.dumps({"metrics": [{
            "metric_name": "dairy_cattle_herd_size", "metric_value": "130,000",
            "unit": "cows", "fiscal_year": 2024,
            "source_quote": "Metric: Dairy cattle managed | 2024: 130,000 cows",
        }]}))

        candidates, selected = extract_business_metric_candidates(
            [table_chunk], tables, self.document, llm,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["metric_value"], 130000)
        self.assertEqual(candidates[0]["extraction_method"], "llm_parser")
        self.assertEqual(candidates[0]["extraction_config"]["model"], "test-model")
        self.assertEqual(candidates[0]["source_chunk_index"], 4)
        self.assertIn("Milk supply indicators", llm.prompts[0])
        self.assertIn("Parser-produced source chunks:", llm.prompts[0])
        self.assertIn("Milk sourcing resilience", llm.prompts[0])
        self.assertIn("Decision domain: milk_supply", llm.prompts[0])
        self.assertNotIn("Distribution reach", llm.prompts[0])
        self.assertNotIn("commercial_export_revenue", llm.prompts[0])
        self.assertIn("dairy_cattle_herd_size", llm.prompts[0])
        self.assertEqual(selected[0]["layout_type"], "table")

    def test_rejects_value_or_quote_not_grounded_in_parsed_page(self):
        llm = FakeLLM(json.dumps({"metrics": [{
            "metric_name": "dairy_cattle_herd_size", "metric_value": "130,001",
            "unit": "cows", "fiscal_year": 2024,
            "source_quote": "Dairy cattle managed reached 130,001 cows in 2024.",
        }]}))
        candidates, selected = extract_business_metric_candidates(self.chunks, [], self.document, llm)
        self.assertEqual(candidates, [])
        self.assertEqual(selected[0]["validation_rejections"]["quote_not_grounded"], 1)

    def test_rejects_catalog_metric_outside_the_selected_decision_profile(self):
        llm = FakeLLM(json.dumps({"metrics": [{
            "metric_name": "export_net_revenue_growth", "metric_value": "12.6",
            "unit": "%", "fiscal_year": 2024,
            "source_quote": "Export net revenue grew by 12.6% in 2024.",
        }]}))

        candidates, selected = extract_business_metric_candidates(self.chunks, [], self.document, llm)

        self.assertEqual(candidates, [])
        self.assertEqual(
            selected[0]["validation_rejections"]["metric_outside_decision_profile_or_empty_field"], 1,
        )

    def test_selected_metric_scopes_prompt_and_rejects_other_metrics_in_same_domain(self):
        self.chunks[0]["text"] = (
            "Dairy cattle managed by Vinamilk reached 130,000 cows in 2024; "
            "milk volume purchased from farmers was 1,000 tonnes."
        )
        self.document["business_decision_domain"] = "milk_supply"
        llm = FakeLLM(json.dumps({"metrics": [
            {"metric_name": "dairy_cattle_herd_size", "metric_value": "130,000",
             "unit": "cows", "fiscal_year": 2024,
             "source_quote": "Dairy cattle managed by Vinamilk reached 130,000 cows in 2024"},
            {"metric_name": "raw_milk_purchases_from_farmers", "metric_value": "1,000",
             "unit": "tonnes", "fiscal_year": 2024,
             "source_quote": "milk volume purchased from farmers was 1,000 tonnes"},
        ]}))

        candidates, pages = extract_business_metric_candidates(
            self.chunks, [], self.document, llm,
            metric_names=["dairy_cattle_herd_size"],
        )

        self.assertEqual([item["metric_name"] for item in candidates], ["dairy_cattle_herd_size"])
        self.assertIn('"dairy_cattle_herd_size"', llm.prompts[0])
        self.assertNotIn('"raw_milk_purchases_from_farmers"', llm.prompts[0])
        self.assertEqual(pages[0]["validation_rejections"][
            "metric_outside_decision_profile_or_empty_field"], 1)
        run = build_business_metric_extraction_run(
            self.chunks, pages, candidates,
            {**self.document, "selected_metric_names": ["dairy_cattle_herd_size"]}, llm,
        )
        self.assertEqual(run["audit"]["selected_metric_names"], ["dairy_cattle_herd_size"])

    def test_requires_one_configured_business_decision_domain(self):
        llm = FakeLLM('{"metrics":[]}')
        self.document.pop("business_decision_domain")
        with self.assertRaisesRegex(ValueError, "business_decision_domain"):
            extract_business_metric_candidates(self.chunks, [], self.document, llm)
        self.assertEqual(llm.prompts, [])

    def test_extraction_audit_distinguishes_checked_empty_and_unselected_chunks(self):
        chunks = [
            {"text": "Dairy cattle managed reached 130,000 cows in 2024.",
             "metadata": {"page_number": 6, "chunk_index": 3, "layout_type": "text"}},
            {"text": "Operations overview with no numeric evidence.",
             "metadata": {"page_number": 7, "chunk_index": 4, "layout_type": "text"}},
        ]
        llm = FakeLLM('{"metrics":[]}')
        candidates, pages = extract_business_metric_candidates(chunks, [], self.document, llm)

        run = build_business_metric_extraction_run(chunks, pages, candidates, self.document, llm)

        decisions = {item["chunk_index"]: item for item in run["audit"]["chunk_decisions"]}
        self.assertEqual(decisions[3]["status"], "checked_no_candidate")
        self.assertEqual(decisions[4]["status"], "not_selected")
        self.assertEqual(decisions[4]["selection_reason"], "no_numeric_evidence")
        self.assertEqual(run["status"], "completed")
        self.assertNotIn("text", decisions[3])

    def test_provider_unavailable_audit_does_not_claim_chunks_were_checked(self):
        run = build_business_metric_extraction_run(
            self.chunks, [], [], self.document, None, execution_error="provider_unavailable",
        )
        self.assertEqual(run["status"], "provider_unavailable")
        self.assertEqual(run["audit"]["chunk_decisions"][0]["status"], "not_evaluated")

    def test_accepts_string_fiscal_year_from_manifest(self):
        self.document["fiscal_year"] = "2024"
        llm = FakeLLM(json.dumps({"metrics": [{
            "metric_name": "dairy_cattle_herd_size", "metric_value": "130,000",
            "unit": "cows", "fiscal_year": 2024, "source_quote": self.page,
        }]}))

        candidates, _ = extract_business_metric_candidates(self.chunks, [], self.document, llm)

        self.assertEqual(len(candidates), 1)

    def test_preserves_source_quote_exactly_when_model_changes_only_letter_case(self):
        llm = FakeLLM(json.dumps({"metrics": [{
            "metric_name": "dairy_cattle_herd_size", "metric_value": "130,000",
            "unit": "cows", "fiscal_year": 2024,
            "source_quote": self.page.lower(),
        }]}))

        candidates, _ = extract_business_metric_candidates(self.chunks, [], self.document, llm)

        self.assertEqual(candidates[0]["source_quote"], self.page)

    def test_report_year_can_supply_context_when_source_quote_omits_annual_period(self):
        self.page = "Dairy cattle managed by Vinamilk reached 130,000 cows."
        self.chunks[0]["text"] = self.page
        llm = FakeLLM(json.dumps({"metrics": [{
            "metric_name": "dairy_cattle_herd_size", "metric_value": "130,000",
            "unit": "cows", "fiscal_year": 2024, "source_quote": self.page,
        }]}))

        candidates, _ = extract_business_metric_candidates(self.chunks, [], self.document, llm)

        self.assertEqual(len(candidates), 1)

    def test_selects_numeric_parser_table_without_metric_alias_match(self):
        chunks = [{
            "text": "Columns: Indicator | 2024\nRow 1: Indicator: New product launches | 2024: 12 products",
            "metadata": {"page_number": 8, "chunk_index": 9, "layout_type": "table"},
        }]
        selected = select_business_metric_chunks(chunks)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["selection_signals"]["parser_layout"], "table")

    def test_domain_selection_filters_unrelated_numeric_tables_before_numeric_layout_ranking(self):
        chunks = [
            {"text": "Columns: Employees | 2024\nRow 1: Employees: 8,000",
             "metadata": {"page_number": 2, "chunk_index": 1, "layout_type": "table"}},
            {"text": "Columns: Metric | 2024\nRow 1: Dairy cattle managed: 130,000 cows",
             "metadata": {"page_number": 8, "chunk_index": 2, "layout_type": "table"}},
            {"text": "Dairy cattle managed by Vinamilk reached 130,000 cows in 2024.",
             "metadata": {"page_number": 9, "chunk_index": 3, "layout_type": "text"}},
        ]

        selected = select_business_metric_chunks(
            chunks, max_chunks=2, decision_domain="milk_supply",
        )

        self.assertEqual([chunk["page_number"] for chunk in selected], [8, 9])
        self.assertEqual(selected[0]["layout_type"], "table")
        self.assertEqual(
            selected[0]["selection_signals"]["matched_primary_metrics"],
            ["dairy_cattle_herd_size"],
        )

    def test_domain_selector_keeps_numeric_table_candidates_without_alias_match_for_llm_review(self):
        chunks = [{
            "text": "Columns: K | 2024\nRow 1: K: 402,000 tonnes",
            "metadata": {"page_number": 10, "chunk_index": 7, "layout_type": "table"},
        }]

        selected = select_business_metric_chunks(chunks, decision_domain="milk_supply")

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["selection_signals"]["domain_relevance_score"], 0)
        self.assertEqual(selected[0]["selection_signals"]["parser_layout"], "table")

    def test_selects_numeric_narrative_chunk_for_non_table_kpis(self):
        chunks = [{
            "text": "Premium product sales grew 18% in 2025; 12 products launched.",
            "metadata": {"page_number": 9, "chunk_index": 10, "layout_type": "text"},
        }]
        selected = select_business_metric_chunks(chunks)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["layout_type"], "text")

    def test_selection_spreads_request_budget_across_pages(self):
        chunks = [
            {"text": f"Row {index}: KPI value 2025: {100 + index}",
             "metadata": {"page_number": 4, "chunk_index": index, "layout_type": "table"}}
            for index in range(3)
        ] + [{
            "text": "Channel growth 2025: 18% and 12 stores opened",
            "metadata": {"page_number": 5, "chunk_index": 3, "layout_type": "text"},
        }]
        selected = select_business_metric_chunks(chunks, max_chunks=3)
        self.assertEqual(len(selected), 3)
        self.assertEqual([chunk["page_number"] for chunk in selected], [4, 4, 5])

    def test_ignores_table_header_without_numeric_rows(self):
        chunks = [{
            "text": "Columns: Indicator | Value\nRow 1: Indicator: Product quality | Value: pending",
            "metadata": {"page_number": 8, "chunk_index": 9, "layout_type": "table"},
        }]
        self.assertEqual(select_business_metric_chunks(chunks), [])

    def test_does_not_collapse_distinct_same_period_values_into_one_metric(self):
        page_text = (
            "Dairy cattle managed by Vinamilk reported 130,000 cows in 2024. "
            "Dairy cattle managed by Vinamilk reported 129,000 cows in 2024."
        )
        self.chunks[0]["text"] = page_text
        llm = FakeLLM(json.dumps({"metrics": [
            {
                "metric_name": "dairy_cattle_herd_size", "metric_value": "130,000",
                "unit": "cows", "fiscal_year": 2024,
                "source_quote": "Dairy cattle managed by Vinamilk reported 130,000 cows in 2024.",
            },
            {
                "metric_name": "dairy_cattle_herd_size", "metric_value": "129,000",
                "unit": "cows", "fiscal_year": 2024,
                "source_quote": "Dairy cattle managed by Vinamilk reported 129,000 cows in 2024.",
            },
        ]}))

        candidates, selected = extract_business_metric_candidates(self.chunks, [], self.document, llm)

        self.assertEqual(candidates, [])
        self.assertEqual(selected[0]["ambiguous_metric_periods"], 1)

    def test_withholds_conflicting_values_across_table_chunks(self):
        chunks = [
            {"text": "Row 1: Dairy cattle managed | 2024: 130,000 cows",
             "metadata": {"page_number": 6, "chunk_index": 20, "layout_type": "table"}},
            {"text": "Row 2: Dairy cattle managed | 2024: 129,000 cows",
             "metadata": {"page_number": 7, "chunk_index": 21, "layout_type": "table"}},
        ]
        responses = [
            json.dumps({"metrics": [{
                "metric_name": "dairy_cattle_herd_size", "metric_value": "130,000",
                "unit": "cows", "fiscal_year": 2024,
                "source_quote": "Dairy cattle managed | 2024: 130,000 cows",
            }]}),
            json.dumps({"metrics": [{
                "metric_name": "dairy_cattle_herd_size", "metric_value": "129,000",
                "unit": "cows", "fiscal_year": 2024,
                "source_quote": "Dairy cattle managed | 2024: 129,000 cows",
            }]}),
        ]

        candidates, selected = extract_business_metric_candidates(
            chunks, [], self.document, FakeLLM(responses),
        )

        self.assertEqual(candidates, [])
        self.assertTrue(all(chunk["ambiguous_metric_periods"] == 1 for chunk in selected))


if __name__ == "__main__":
    unittest.main()
