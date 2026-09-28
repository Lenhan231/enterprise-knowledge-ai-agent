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

    def test_layout_does_not_pair_narrative_growth_sentence_with_large_number(self):
        rows = candidates(
            [],
            {"company": "Example", "fiscal_year": 2021, "document_id": "DOC-2021",
             "official_url": "https://example.test/report", "rbac": {"allowed_roles": ["finance_analyst"]}},
            visual_pages=[{
                "page_number": 53,
                "spans": [
                    {"text": "Net revenue from overseas subsidiaries reached", "bbox": [0, 0, 170, 20], "font_size": 12},
                    {"text": "2.2", "bbox": [175, 0, 220, 50], "font_size": 36},
                    {"text": "MCM specifically brought in VND 2,926 billion in net revenue, a 3.6% year-over-year increase", "bbox": [0, 100, 260, 120], "font_size": 12},
                    {"text": "94.6", "bbox": [175, 120, 220, 160], "font_size": 36},
                ],
            }],
        )

        self.assertEqual(rows, [])

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

    def test_ambiguous_revenue_and_net_profit_labels_are_not_financial_candidates(self):
        rows = candidates(
            [{"metadata": {"page_number": 92}, "text": "Doanh thu 52.576.991 tỷ đồng. Lợi nhuận thuần 8.686.245 tỷ đồng."}],
            {
                "company": "Vinamilk", "fiscal_year": 2024,
                "document_id": "VNM-AR-2024-VI",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertEqual(rows, [])

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
        self.assertEqual(rows[0]["unit"], "tỷ đồng")
        self.assertEqual(rows[0]["status"], "needs_review")
        self.assertEqual(rows[0]["company"], "Example JSC")
        self.assertTrue(rows[0]["source_quote_hash"])

    def test_candidate_without_page_evidence_is_ignored(self):
        rows = candidates(
            [{"metadata": {}, "text": "Doanh thu thuần 60.479 tỷ đồng"}],
            {"company": "Example JSC", "fiscal_year": 2025},
        )

        self.assertEqual(rows, [])

    def test_restricted_financial_fallback_does_not_mine_narrative_pages(self):
        rows = candidates(
            [{"metadata": {"page_number": 4}, "text": "Net revenue 60,479 billion VND."}],
            {"company": "Example", "fiscal_year": 2024, "document_id": "DOC-2024",
             "official_url": "https://example.test/report", "rbac": {"allowed_roles": ["finance_analyst"]}},
            text_evidence_page_numbers=set(),
        )

        self.assertEqual(rows, [])

    def test_page_scale_completes_a_bare_vnd_table_header(self):
        rows = candidates(
            [{"metadata": {"page_number": 5}, "text": "Total assets 60,000 billion\\nVND."}],
            {"company": "Example", "fiscal_year": 2024, "document_id": "DOC-2024",
             "official_url": "https://example.test/report", "rbac": {"allowed_roles": ["finance_analyst"]}},
            tables=[{
                "page_number": 5, "columns": ["Metric", "2024 VND"],
                "rows": [{"Metric": "Total assets", "2024 VND": "60,000"}],
            }],
        )

        self.assertEqual(rows[0]["unit"], "billion VND")

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
        self.assertEqual(rows[0]["unit"], "billion VND")
        self.assertEqual(rows[0]["status"], "needs_review")

    def test_audited_income_statement_revenue_labels_create_review_candidates(self):
        common = {
            "company": "Vinamilk",
            "fiscal_year": 2023,
            "document_id": "VNM-AR-2023-EN",
            "official_url": "https://example.vn/report.pdf",
            "rbac": {"allowed_roles": ["finance_analyst"]},
        }
        rows = candidates(
            [{"metadata": {"page_number": 115}, "text": "2023 VND 2022 VND"}],
            common,
            tables=[{
                "page_number": 115,
                "columns": ["label", "code", "note", "2023 VND", "2022 VND"],
                "rows": [{
                    "label": "Revenue from sales of goods and provision of services",
                    "code": "01", "note": "VI.1",
                    "2023 VND": "60,478,912,566,740",
                    "2022 VND": "60,074,730,223,299",
                }],
            }],
        )

        revenue = next(row for row in rows if row["metric_name"] == "total_consolidated_revenue")
        self.assertEqual(revenue["candidate_values"], ["60,478,912,566,740"])
        self.assertEqual(revenue["unit"], "VND")
        self.assertEqual(revenue["status"], "needs_review")

    def test_vietnamese_audited_income_statement_revenue_label_is_supported(self):
        rows = candidates(
            [{"metadata": {"page_number": 111}, "text": "2022 VND 2021 VND"}],
            {
                "company": "Vinamilk", "fiscal_year": 2022,
                "document_id": "VNM-AR-2022-VI",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
            tables=[{
                "page_number": 111,
                "columns": ["label", "code", "note", "2022 VND", "2021 VND"],
                "rows": [{
                    "label": "Doanh thu bán hàng và cung cấp dịch vụ",
                    "code": "01", "note": "VI.1",
                    "2022 VND": "60.074.730.223.299",
                    "2021 VND": "61.012.074.147.764",
                }],
            }],
        )

        revenue = next(row for row in rows if row["metric_name"] == "total_consolidated_revenue")
        self.assertEqual(revenue["candidate_values"], ["60.074.730.223.299"])

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
                "columns": ["Metric", "2024 (Triệu VND)", "2023 (Triệu VND)"],
            }],
            text_evidence_page_numbers=set(),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric_name"], "net_revenue")
        self.assertEqual(rows[0]["candidate_values"], ["60,479"])
        self.assertEqual(rows[0]["unit"], "triệu VND")
        self.assertIn("label: Net revenue", rows[0]["source_quote"])
        self.assertIn("2024: 60,479", rows[0]["source_quote"])

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

    def test_prefers_the_document_year_from_a_comparative_table(self):
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
        self.assertEqual(rows[0]["candidate_values"], ["60,479"])
        self.assertIn("2024: 60,479", rows[0]["source_quote"])
        self.assertIn("2023: 56,400", rows[0]["source_quote"])

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

        self.assertEqual(rows[0]["candidate_values"], ["60,479"])

    def test_vinamilk_2021_total_revenue_uses_the_2021_table_column(self):
        import fitz

        from core.document_processing.processors.pdf_processor import PDFProcessor

        report = Path(__file__).resolve().parents[1] / "data/raw/vietnam_enterprises/vnm/vnm-ar-2021-vi.pdf"
        if not report.is_file():
            self.skipTest("requires the optional downloaded Vinamilk report corpus")
        with fitz.open(report) as pdf:
            page_text = pdf[9].get_text()
            tables = PDFProcessor._extract_page_tables(pdf[9], 10)

        rows = candidates(
            [{"metadata": {"page_number": 10}, "text": page_text}],
            {
                "company": "Vinamilk", "fiscal_year": 2021,
                "document_id": "VNM-AR-2021-VI",
                "official_url": "https://www.vinamilk.com.vn/",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
            tables=tables,
        )

        revenue = next(row for row in rows if row["metric_name"] == "total_consolidated_revenue")
        self.assertEqual(revenue["candidate_values"], ["61,012"])
        self.assertIn("2017: 51,135", revenue["source_quote"])
        self.assertIn("2021: 61,012", revenue["source_quote"])
        self.assertEqual(revenue["status"], "needs_review")

    def test_real_consolidated_income_statements_select_the_report_year_column(self):
        import fitz

        from core.document_processing.processors.pdf_processor import PDFProcessor

        root = Path(__file__).resolve().parents[1] / "data/raw/vietnam_enterprises/vnm"
        fixtures = (
            ("vnm-ar-2021-vi.pdf", 88, 2021, "VNM-AR-2021-VI", {
                "total_consolidated_revenue": "61,012,074,147,764",
                "profit_after_tax": "10,632,535,972,478",
            }),
            ("vnm-ar-2022-vi.pdf", 109, 2022, "VNM-AR-2022-VI", {
                "total_consolidated_revenue": "60.074.730.223.299",
                "profit_after_tax": "8.577.575.319.708",
            }),
            ("vnm-ar-2023-en.pdf", 115, 2023, "VNM-AR-2023-EN", {
                "total_consolidated_revenue": "60,478,912,566,740",
                "net_revenue": "60,368,915,511,505",
                "gross_profit": "24,544,731,615,410",
                "profit_before_tax": "10,967,899,391,486",
                "profit_after_tax": "9,019,354,165,051",
            }),
            ("vnm-ar-2024-vi.pdf", 92, 2024, "VNM-AR-2024-VI", {
                "gross_profit": "15.166.269",
                "profit_before_tax": "10.833.006",
            }),
        )
        missing = [filename for filename, *_ in fixtures if not (root / filename).is_file()]
        if missing:
            self.skipTest("requires optional downloaded Vinamilk reports: " + ", ".join(missing))

        for filename, page_number, year, document_id, expected in fixtures:
            with self.subTest(document=document_id), fitz.open(root / filename) as pdf:
                page = pdf[page_number - 1]
                rows = candidates(
                    [{"metadata": {"page_number": page_number}, "text": page.get_text()}],
                    {
                        "company": "Vinamilk", "fiscal_year": year,
                        "document_id": document_id,
                        "official_url": "https://example.vn/report.pdf",
                        "rbac": {"allowed_roles": ["finance_analyst"]},
                    },
                    tables=PDFProcessor._extract_page_tables(page, page_number),
                )
                by_metric = {row["metric_name"]: row for row in rows}
                for metric_name, value in expected.items():
                    self.assertEqual(by_metric[metric_name]["candidate_values"], [value])
                    self.assertIn(value, by_metric[metric_name]["source_quote"])
                if document_id == "VNM-AR-2024-VI":
                    self.assertNotIn("net_revenue", by_metric)

    def test_vinamilk_2022_domestic_segment_profit_is_not_company_gross_profit(self):
        import fitz

        report = Path(__file__).resolve().parents[1] / "data/raw/vietnam_enterprises/vnm/vnm-ar-2022-vi.pdf"
        if not report.is_file():
            self.skipTest("requires the optional downloaded Vinamilk report corpus")
        with fitz.open(report) as pdf:
            page_text = pdf[5].get_text()

        rows = candidates(
            [{"metadata": {"page_number": 6}, "text": page_text}],
            {
                "company": "Vinamilk", "fiscal_year": 2022,
                "document_id": "VNM-AR-2022-VI",
                "official_url": "https://example.vn/report.pdf",
                "rbac": {"allowed_roles": ["finance_analyst"]},
            },
        )

        self.assertNotIn("gross_profit", {row["metric_name"] for row in rows})

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
