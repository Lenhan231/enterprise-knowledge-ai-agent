import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.analytics.financial_extraction import (
    extract_financial_candidates,
    merge_candidate_sources,
    select_financial_pages,
)


class FakeLLM:
    model_name = "fake-finance-model"

    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.response


class FinancialPageSelectionTests(unittest.TestCase):
    def test_merge_keeps_parser_metrics_missing_from_llm_and_prefers_llm_duplicates(self):
        parser = [
            {"document_id": "D", "metric_name": "net_revenue", "fiscal_year": 2024,
             "page_number": 2, "extraction_method": "rule_based_page_evidence", "candidate_values": ["10"]},
            {"document_id": "D", "metric_name": "profit_after_tax", "fiscal_year": 2024,
             "page_number": 2, "extraction_method": "rule_based_page_evidence", "candidate_values": ["3"]},
        ]
        llm = [{"document_id": "D", "metric_name": "net_revenue", "fiscal_year": 2024,
                "page_number": 2, "extraction_method": "llm_selected_financial_page", "candidate_values": ["11"]}]

        merged = merge_candidate_sources(parser, llm)

        self.assertEqual(len(merged), 2)
        self.assertEqual(next(row for row in merged if row["metric_name"] == "net_revenue")["candidate_values"], ["11"])
        self.assertEqual(next(row for row in merged if row["metric_name"] == "profit_after_tax")["candidate_values"], ["3"])

    def test_selects_ranked_financial_pages_and_caps_llm_work(self):
        chunks = [
            {
                "text": f"Consolidated income statement revenue 2024 value {page}",
                "metadata": {"page_number": page, "section_title": "Financial statements"},
            }
            for page in range(1, 15)
        ]
        chunks.append({"text": "Employee handbook", "metadata": {"page_number": 20}})

        pages = select_financial_pages(chunks, max_pages=10)

        self.assertEqual(len(pages), 10)
        self.assertEqual([page["page_number"] for page in pages], list(range(1, 11)))
        self.assertTrue(all(page["selection_signals"]["financial_terms"] for page in pages))
        self.assertNotIn(20, {page["page_number"] for page in pages})

    def test_table_layout_alone_does_not_select_nonfinancial_pages(self):
        pages = select_financial_pages(
            [{"text": "Name | Department\nAlex | Sales",
              "metadata": {"page_number": 4, "layout_type": "table"}}],
            [{"page_number": 4, "columns": ["Name", "Department"],
              "rows": [{"Name": "Alex", "Department": "Sales"}]}],
        )

        self.assertEqual(pages, [])

    def test_candidate_requires_exact_page_quote_and_uses_page_evidence(self):
        page_text = "Bảng cân đối kế toán\nTổng tài sản năm 2024 là 55.049 tỷ đồng."
        llm = FakeLLM(json.dumps({
            "metrics": [{
                "metric_name": "total_assets",
                "metric_value": "55.049",
                "unit": "tỷ đồng",
                "fiscal_year": 2024,
                "source_quote": "Tổng tài sản năm 2024 là 55.049 tỷ đồng.",
            }],
        }, ensure_ascii=False))
        chunks = [{"text": page_text, "metadata": {"page_number": 3}}]
        document = {
            "company": "Công ty Cổ phần Sữa Việt Nam",
            "fiscal_year": 2024,
            "document_id": "VNM-AR-2024-VI",
            "official_url": "https://example.vn/report.pdf",
            "rbac": {"allowed_roles": ["finance_analyst"]},
        }

        candidates, selected = extract_financial_candidates(chunks, [], document, llm)

        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual([page["page_number"] for page in selected], [3])
        self.assertEqual(candidates[0]["candidate_values"], ["55.049"])
        self.assertEqual(candidates[0]["unit"], "tỷ đồng")
        self.assertEqual(candidates[0]["status"], "needs_review")
        self.assertEqual(candidates[0]["extraction_method"], "llm_selected_financial_page")
        self.assertEqual(candidates[0]["extractor_model"], "fake-finance-model")
        self.assertEqual(candidates[0]["fiscal_year"], 2024)
        self.assertEqual(candidates[0]["allowed_roles"], ["finance_analyst"])
        self.assertIn("ignore comparison years", llm.prompts[0])

    def test_ocr_near_match_label_is_reviewable_but_native_and_ungrounded_values_fail(self):
        quote = "Doanh thu bán hàng và cung cép dich vy | 22.070.557.490.766 | 16.081.466.183.586"
        page_text = f"Đơn vị: VNĐ | 2011 | 2010\n{quote}"
        response = json.dumps({"metrics": [{
            "metric_name": "total_consolidated_revenue",
            "metric_value": "22.070.557.490.766",
            "unit": "VNĐ",
            "fiscal_year": 2011,
            "source_quote": quote,
        }]}, ensure_ascii=False)
        document = {
            "company": "Công ty Cổ phần Sữa Việt Nam", "fiscal_year": 2011,
            "document_id": "VNM-FS-2011", "rbac": {"allowed_roles": ["finance_analyst"]},
        }

        ocr_candidates, _ = extract_financial_candidates(
            [{"text": page_text, "metadata": {"page_number": 10, "text_extraction_method": "tesseract"}}],
            [], document, FakeLLM(response),
        )
        native_candidates, _ = extract_financial_candidates(
            [{"text": page_text, "metadata": {"page_number": 10}}],
            [], document, FakeLLM(response),
        )
        wrong_value = json.loads(response)
        wrong_value["metrics"][0]["metric_value"] = "22.070.557.490.767"
        wrong_value_response = json.dumps(wrong_value, ensure_ascii=False)
        ungrounded_candidates, _ = extract_financial_candidates(
            [{"text": page_text, "metadata": {"page_number": 10, "text_extraction_method": "tesseract"}}],
            [], document, FakeLLM(wrong_value_response),
        )

        self.assertEqual(len(ocr_candidates), 1)
        self.assertEqual(ocr_candidates[0]["status"], "needs_review")
        self.assertEqual(ocr_candidates[0]["selection_evidence"]["source_label_match"], "ocr_near_match")
        self.assertEqual(native_candidates, [])
        self.assertEqual(ungrounded_candidates, [])

    def test_llm_cannot_publish_a_comparative_year_as_the_report_year_candidate(self):
        llm = FakeLLM(json.dumps({
            "metrics": [{
                "metric_name": "net_revenue",
                "metric_value": "90",
                "unit": "billion VND",
                "fiscal_year": 2023,
                "source_quote": "Net revenue 2023 was 90 billion VND.",
            }],
        }))
        page_text = "Net revenue 2024 was 100 billion VND. Net revenue 2023 was 90 billion VND."
        document = {
            "company": "Example", "fiscal_year": "2024", "document_id": "DOC-2024",
            "rbac": {"allowed_roles": ["finance_analyst"]},
        }

        candidates, selected = extract_financial_candidates(
            [{"text": page_text, "metadata": {"page_number": 1}}], [], document, llm,
        )

        self.assertEqual(candidates, [])
        self.assertEqual(selected[0]["validation_rejections"], {"wrong_report_year": 1})

    def test_candidate_with_quote_not_found_on_page_is_discarded(self):
        llm = FakeLLM(json.dumps({
            "metrics": [{
                "metric_name": "total_assets",
                "metric_value": "999",
                "unit": "billion VND",
                "fiscal_year": 2024,
                "source_quote": "Total assets in 2024 were 999 billion VND.",
            }],
        }))
        document = {
            "company": "Example",
            "fiscal_year": 2024,
            "document_id": "DOC-2024",
            "rbac": {"allowed_roles": ["finance_analyst"]},
        }

        candidates, _ = extract_financial_candidates(
            [{"text": "Total assets 2024 were 100 billion VND.",
              "metadata": {"page_number": 1}}],
            [], document, llm,
        )

        self.assertEqual(candidates, [])

    def test_table_row_quote_can_use_year_from_column_header(self):
        page_text = "Đơn vị: Triệu VND | 2024 | 2023\\nDoanh thu | 52.576.991 | 51.465.324\\nLợi nhuận trước thuế | 10.833.006 | 10.195.687"
        llm = FakeLLM(json.dumps({
            "metrics": [{
                "metric_name": "profit_before_tax",
                "metric_value": "10.833.006",
                "unit": "Triệu VND",
                "fiscal_year": 2024,
                "source_quote": "Lợi nhuận trước thuế | 10.833.006 | 10.195.687",
            }],
        }, ensure_ascii=False))
        document = {
            "company": "Example", "fiscal_year": 2024, "document_id": "DOC-2024",
            "rbac": {"allowed_roles": ["finance_analyst"]},
        }

        candidates, _ = extract_financial_candidates(
            [{"text": page_text, "metadata": {"page_number": 92}}], [], document, llm,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["candidate_values"], ["10.833.006"])

    def test_unexpected_json_shape_fails_closed_and_records_error(self):
        llm = FakeLLM('{"answer":"revenue is 10"}')
        document = {
            "company": "Example",
            "fiscal_year": 2024,
            "document_id": "DOC-2024",
            "rbac": {"allowed_roles": ["finance_analyst"]},
        }

        candidates, selected = extract_financial_candidates(
            [{"text": "Consolidated revenue 10 in 2024.",
              "metadata": {"page_number": 1}}],
            [], document, llm,
        )

        self.assertEqual(candidates, [])
        self.assertIn("ValueError", selected[0]["extraction_error"])


if __name__ == "__main__":
    unittest.main()
