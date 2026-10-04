import importlib.util
import hashlib
from pathlib import Path
import unittest
from unittest.mock import Mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/analytics/audit_verified_financial_metrics.py"
SPEC = importlib.util.spec_from_file_location("audit_verified_financial_metrics", SCRIPT)
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


class VerifiedMetricSourceAuditTest(unittest.TestCase):
    def test_accepts_value_label_year_and_reported_unit_on_page(self):
        observation = {
            "metric_name": "total_consolidated_revenue", "fiscal_year": 2020,
            "metric_value": 59723, "unit": "billion VND",
        }

        result = audit_module.score_observation(
            observation,
            "Consolidated net revenue 2020 reached VND 59,723 billion.",
        )

        self.assertTrue(result["passed"])

    def test_rejects_wrong_unit_or_missing_metric_label(self):
        observation = {
            "metric_name": "profit_after_tax", "fiscal_year": 2020,
            "metric_value": 11236, "unit": "billion VND",
        }

        result = audit_module.score_observation(observation, "Consolidated revenue: 11,236 million VND in 2020")

        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["metric_label"])
        self.assertFalse(result["checks"]["unit"])

    def test_matches_vietnamese_labels_and_period_separators_in_reported_values(self):
        cases = (
            ({"metric_name": "total_consolidated_revenue", "fiscal_year": 2024,
              "metric_value": 61824, "unit": "tỷ đồng"},
             "Tổng doanh thu hợp nhất năm 2024: 61.824 tỷ đồng"),
            ({"metric_name": "profit_after_tax", "fiscal_year": 2024,
              "metric_value": 9453, "unit": "tỷ đồng"},
             "Lợi nhuận sau thuế hợp nhất năm 2024: 9.453 tỷ đồng"),
            ({"metric_name": "inventory", "fiscal_year": 2024,
              "metric_value": 5634710, "unit": "triệu VND"},
             "Hàng tồn kho tại ngày 31/12/2024: 5.634.710 Triệu VND"),
        )
        for observation, page_text in cases:
            with self.subTest(metric=observation["metric_name"]):
                self.assertTrue(audit_module.score_observation(observation, page_text)["passed"])

    def test_source_must_match_the_official_manifest_url(self):
        manifest = {"documents": [{
            "document_id": "VNM-AR-2021-VI",
            "source_url": "https://reports.example.test/annual.pdf",
        }]}

        self.assertTrue(audit_module._is_manifest_source(
            "VNM-AR-2021-VI", "https://reports.example.test/annual.pdf", manifest,
        ))
        self.assertFalse(audit_module._is_manifest_source(
            "VNM-AR-2021-VI", "https://attacker.example.test/annual.pdf", manifest,
        ))
        self.assertFalse(audit_module._is_manifest_source(
            "VNM-AR-2021-VI", "http://reports.example.test/annual.pdf", manifest,
        ))

    def test_never_concatenates_adjacent_table_cells_into_one_value(self):
        observation = {"metric_name": "total_assets", "fiscal_year": 2024,
                       "metric_value": 5634710, "unit": "million VND"}
        result = audit_module.score_observation(
            observation, "Total assets 2024\n56,993,245\nInventories 5,634,710\nVND million",
        )
        self.assertTrue(result["checks"]["value"])
        wrong = dict(observation, metric_value=569932455634710)
        self.assertFalse(audit_module.score_observation(
            wrong, "Total assets 2024\n56,993,245\nInventories 5,634,710\nVND million",
        )["checks"]["value"])

    def test_image_only_page_uses_only_its_hash_matched_parser_chunk(self):
        content = "2011 Cost of goods sold 15.039.305.378.364 VND"
        observation = {
            "document_id": "UPLOAD-1", "page_number": 8, "source_chunk_index": 13,
            "source_content_hash": hashlib.sha256(content.encode()).hexdigest(),
        }
        repository = Mock()
        repository.get_document_chunks.return_value = [{
            "chunk_index": 13, "content": content, "metadata": {"page_number": 8},
        }]
        self.assertEqual(audit_module.linked_parser_chunk_text(observation, repository),
                         (content, observation["source_content_hash"]))
        repository.get_document_chunks.return_value[0]["metadata"]["page_number"] = 9
        self.assertIsNone(audit_module.linked_parser_chunk_text(observation, repository))

    def test_resolves_financial_metric_to_its_exact_chunk_id_and_provenance(self):
        content = "2024 Total consolidated revenue 61,824 billion VND"
        observation = {
            "document_id": "VNM-AR-2024-EN", "page_number": 2,
            "source_chunk_id": 7001, "source_chunk_index": 12,
            "source_content_hash": hashlib.sha256(content.encode()).hexdigest(),
        }
        repository = Mock()
        repository.get_document_chunk.return_value = {
            "chunk_index": 12, "content": content, "metadata": {"page_number": 2},
        }
        result = audit_module.linked_parser_chunk(observation, repository)
        self.assertEqual(result["content"], content)
        self.assertEqual(result["content_sha256"], observation["source_content_hash"])
        repository.get_document_chunk.assert_called_once_with(7001, "VNM-AR-2024-EN")

        observation["source_content_hash"] = "0" * 64
        self.assertIsNone(audit_module.linked_parser_chunk(observation, repository))

    def test_unit_context_can_be_verified_on_another_page_of_the_same_uploaded_report(self):
        observation = {"document_id": "UPLOAD-1", "metric_name": "net_revenue",
                       "metric_label": "Net revenue", "fiscal_year": 2011, "unit": "VND"}
        chunks = [
            {"content": "Đơn vị tính: VND. Doanh thu thudn cho năm 2011.",
             "metadata": {"page_number": 8}},
            {"content": "Doanh thu thuần cho năm 2011.", "metadata": {"page_number": 39}},
            {"content": "Đơn vị tính: VND. Doanh thu thudn cho năm 2010.",
             "metadata": {"page_number": 7}},
        ]
        result = audit_module.linked_document_unit_pages(observation, chunks)
        self.assertEqual([page["page_number"] for page in result], [8])


if __name__ == "__main__":
    unittest.main()
