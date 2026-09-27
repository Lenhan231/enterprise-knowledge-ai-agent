from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.analytics.metric_candidates import candidates


class MetricCandidateTest(unittest.TestCase):
    def test_layout_pairs_large_kpi_figures_with_nearby_labels(self):
        rows = candidates(
            [],
            {
                "company": "Vinamilk",
                "fiscal_year": 2024,
                "document_id": "VNM-AR-2024-VI",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
            visual_pages=[{
                "page_number": 12,
                "spans": [
                    {"text": "Tổng doanh thu hợp nhất năm 2024", "bbox": [10, 10, 100, 20], "font_size": 14},
                    {"text": "61.824", "bbox": [10, 20, 150, 80], "font_size": 70},
                    {"text": "Lợi nhuận sau thuế hợp nhất năm 2024", "bbox": [10, 90, 120, 100], "font_size": 14},
                    {"text": "9.453", "bbox": [10, 100, 150, 160], "font_size": 70},
                    {"text": "2024", "bbox": [300, 10, 330, 20], "font_size": 14},
                ],
            }],
        )

        self.assertEqual(
            {row["metric_name"]: row["candidate_values"] for row in rows},
            {"total_consolidated_revenue": ["61.824"], "profit_after_tax": ["9.453"]},
        )
        self.assertTrue(all(row["page_number"] == 12 and row["status"] == "needs_review" for row in rows))

    def test_consolidated_net_revenue_is_not_duplicated_as_net_revenue(self):
        rows = candidates(
            [{"metadata": {"page_number": 46}, "text": "Consolidated net revenue 59,723 billion VND."}],
            {
                "company": "Vinamilk",
                "fiscal_year": 2020,
                "document_id": "VNM-AR-2020-VI",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual([row["metric_name"] for row in rows], ["total_consolidated_revenue"])
        self.assertEqual(rows[0]["candidate_values"], ["59,723"])

    def test_domestic_net_revenue_is_not_mislabeled_as_total_net_revenue(self):
        rows = candidates(
            [{"metadata": {"page_number": 46}, "text": "Doanh thu thuần trong nước hợp nhất năm 2024 50.799 tỷ đồng."}],
            {
                "company": "Vinamilk",
                "fiscal_year": 2024,
                "document_id": "VNM-AR-2024-VI",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertNotIn("net_revenue", {row["metric_name"] for row in rows})

    def test_candidate_keeps_page_evidence_pending_review(self):
        rows = candidates(
            [{"metadata": {"page_number": 12}, "text": "Doanh thu thuần 60.479 tỷ đồng"}],
            {
                "company": "Example JSC",
                "fiscal_year": 2025,
                "document_id": "DOC-2025",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric_name"], "net_revenue")
        self.assertEqual(rows[0]["page_number"], 12)
        self.assertEqual(rows[0]["candidate_values"], ["60.479"])
        self.assertEqual(rows[0]["status"], "needs_review")
        self.assertEqual(rows[0]["company"], "Example JSC")
        self.assertTrue(rows[0]["source_quote_hash"])

    def test_candidate_without_page_evidence_is_ignored(self):
        rows = candidates(
            [{"metadata": {}, "text": "Doanh thu thuần 60.479 tỷ đồng"}],
            {"company": "Example JSC", "fiscal_year": 2025},
        )

        self.assertEqual(rows, [])

    def test_ocr_report_label_keeps_consolidated_revenue_distinct(self):
        rows = candidates(
            [{
                "metadata": {"page_number": 2},
                "text": "2023 HIGHLIGHTS Total consolidated revenue 60,479 billion VND",
            }],
            {
                "company": "Example JSC",
                "fiscal_year": 2023,
                "document_id": "DOC-2023",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric_name"], "total_consolidated_revenue")
        self.assertEqual(rows[0]["candidate_values"], ["60,479"])
        self.assertEqual(rows[0]["status"], "needs_review")

    def test_additional_financial_statement_labels_are_review_candidates(self):
        rows = candidates(
            [{
                "metadata": {"page_number": 18},
                "text": "Giá vốn hàng bán 40.000 tỷ đồng\nLợi nhuận gộp 20.479 tỷ đồng\n"
                "Cash and cash equivalents 2,111 billion VND\nInventories 8,500 billion VND",
            }],
            {
                "company": "Example JSC",
                "fiscal_year": 2024,
                "document_id": "DOC-2024",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(
            {row["metric_name"] for row in rows},
            {"cost_of_goods_sold", "gross_profit", "cash_and_equivalents", "inventory"},
        )
        self.assertTrue(all(row["status"] == "needs_review" for row in rows))
        self.assertTrue(all(row["page_number"] == 18 and row["source_quote"] for row in rows))

    def test_employees_and_state_budget_labels_are_review_candidates(self):
        rows = candidates(
            [{
                "metadata": {"page_number": 7},
                "text": "The whole group has 9,877 employees as of December 31, 2023.\n"
                "Contribution to the state budget 1,234 billion VND",
            }],
            {
                "company": "Example JSC",
                "fiscal_year": 2023,
                "document_id": "DOC-2023",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual({row["metric_name"] for row in rows}, {"employees", "state_budget_contribution"})
        self.assertTrue(all(row["status"] == "needs_review" for row in rows))

    def test_ignores_distant_numbers_and_merges_chunks_from_same_page(self):
        rows = candidates(
            [
                {"metadata": {"page_number": 4}, "text": "Net revenue grew substantially during the year."},
                {"metadata": {"page_number": 4}, "text": "Net revenue 60,479 billion VND."},
            ],
            {
                "company": "Example JSC",
                "fiscal_year": 2024,
                "document_id": "DOC-2024",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["candidate_values"], ["60,479"])
        self.assertIn("60,479", rows[0]["source_quote"])

    def test_uses_structured_table_row_values_and_rejects_narrative_guess(self):
        rows = candidates(
            [{
                "metadata": {"page_number": 9},
                "text": "Net revenue grew through acquisitions to reach 60,479 billion VND.",
            }],
            {
                "company": "Example JSC",
                "fiscal_year": 2024,
                "document_id": "DOC-2024",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
            tables=[{
                "page_number": 9,
                "rows": [{"label": "Net revenue", "2024": "60,479", "2023": "56,400"}],
            }],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric_name"], "net_revenue")
        self.assertEqual(rows[0]["candidate_values"], ["60,479", "56,400"])
        self.assertIn("Net revenue", rows[0]["source_quote"])

    def test_rejects_ratio_percentages_and_narrative_connectors(self):
        rows = candidates(
            [{
                "metadata": {"page_number": 10},
                "text": "Profit after tax / Net revenue 19%. Net revenue grew to 60,479 billion VND.",
            }],
            {
                "company": "Example JSC",
                "fiscal_year": 2024,
                "document_id": "DOC-2024",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(rows, [])

    def test_table_rows_exclude_ratios_and_inventory_subtotals(self):
        rows = candidates(
            [],
            {
                "company": "Example JSC",
                "fiscal_year": 2024,
                "document_id": "DOC-2024",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
            tables=[{
                "page_number": 10,
                "rows": [
                    {"label": "Equity/Total assets", "2024": "69%"},
                    {"label": "Inventory turnover", "2024": "6.4 times"},
                    {"label": "Change in inventories", "2024": "-270"},
                    {"label": "Total assets", "2024": "48,432"},
                ],
            }],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric_name"], "total_assets")
        self.assertEqual(rows[0]["candidate_values"], ["48,432"])

    def test_prefers_first_structured_value_and_keeps_one_candidate_per_metric(self):
        rows = candidates(
            [{"metadata": {"page_number": 2}, "text": "Net revenue 60,479 billion VND."}],
            {
                "company": "Example JSC",
                "fiscal_year": 2024,
                "document_id": "DOC-2024",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
            tables=[{
                "page_number": 5,
                "rows": [{"label": "Net revenue", "2024": "60,479", "2023": "56,400"}],
            }],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["page_number"], 5)
        self.assertEqual(rows[0]["candidate_values"], ["60,479", "56,400"])

    def test_table_candidate_drops_accounting_formula_codes(self):
        rows = candidates(
            [],
            {
                "company": "Example JSC",
                "fiscal_year": 2024,
                "document_id": "DOC-2024",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
            tables=[{
                "page_number": 11,
                "rows": [{
                    "label": "Net revenue (10 = 01 - 02)",
                    "code": "10 = 01 - 02",
                    "note": "VI.1",
                    "2024": "60,479",
                    "2023": "56,400",
                }],
            }],
        )

        self.assertEqual(rows[0]["candidate_values"], ["60,479", "56,400"])

    def test_skips_count_after_state_budget_label_when_followed_by_years(self):
        rows = candidates(
            [{
                "metadata": {"page_number": 2},
                "text": "3,820 billion VND Contribution to the state budget 47 Years of partnership.",
            }],
            {
                "company": "Example JSC",
                "fiscal_year": 2023,
                "document_id": "DOC-2023",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(rows, [])

    def test_skips_formula_codes_but_keeps_financial_statement_value(self):
        rows = candidates(
            [{
                "metadata": {"page_number": 112},
                "text": "TOTAL ASSETS (270 = 100 + 200) 270 52,673,371,104,460 48,482,664,236,200",
            }],
            {
                "company": "Example JSC",
                "fiscal_year": 2023,
                "document_id": "DOC-2023",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(rows[0]["metric_name"], "total_assets")
        self.assertEqual(rows[0]["candidate_values"], ["52,673,371,104,460"])

    def test_skips_change_in_inventories_financial_flow_rows(self):
        rows = candidates(
            [{
                "metadata": {"page_number": 117},
                "text": "Change in inventories 10 (1,021,313,389,573) 851,263,069,739",
            }],
            {
                "company": "Example JSC",
                "fiscal_year": 2023,
                "document_id": "DOC-2023",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(rows, [])

    def test_skips_merchandise_inventory_component_as_total_inventory(self):
        rows = candidates(
            [{
                "metadata": {"page_number": 145},
                "text": "Merchandise inventories 143,368,330,354.",
            }],
            {
                "company": "Example JSC",
                "fiscal_year": 2023,
                "document_id": "DOC-2023",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(rows, [])

    def test_selects_total_inventory_after_an_allowance_row(self):
        rows = candidates(
            [{
                "metadata": {"page_number": 111},
                "text": "Allowance for doubtful debts 137 V.2 (14,901,098,023) "
                "(13,445,724,800) Inventories 140 V.5 6,128,081,805,088 5,537,563,396,117",
            }],
            {
                "company": "Example JSC",
                "fiscal_year": 2023,
                "document_id": "DOC-2023",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(rows[0]["metric_name"], "inventory")
        self.assertEqual(rows[0]["candidate_values"], ["6,128,081,805,088"])


if __name__ == "__main__":
    unittest.main()
