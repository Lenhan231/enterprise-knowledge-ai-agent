import sys
import fitz
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_document_extraction import (
    anchor_present,
    compact_result,
    evaluate_table_strategies,
    native_single_page_pdf,
    normalized_anchor_present,
    rasterized_single_page_pdf,
    rasterized_single_page_png,
    score_parse,
    table_page_text,
)  # noqa: E402


class DocumentExtractionEvaluationTest(unittest.TestCase):
    def test_compact_result_keeps_scores_but_drops_raw_parser_dumps(self):
        result = {
            "file_sha256": "abc",
            "conditions": [{
                "condition": "born_digital_pdf",
                "text_anchor_recall": 1.0,
                "extracted_page_text": "large text dump",
                "extracted_tables": [{"rows": ["large table dump"]}],
            }],
        }

        compact = compact_result(result)

        self.assertEqual(compact["file_sha256"], "abc")
        self.assertEqual(compact["conditions"][0]["text_anchor_recall"], 1.0)
        self.assertNotIn("extracted_page_text", compact["conditions"][0])
        self.assertNotIn("extracted_tables", compact["conditions"][0])

    def test_table_strategy_sweep_scores_same_manual_fields_and_records_shapes(self):
        table = SimpleNamespace(
            row_count=1,
            col_count=3,
            extract=lambda: [["Tổng tài sản", "56.993.245", "54.232.491"]],
        )
        page = Mock()
        page.find_tables.return_value.tables = [table]
        case = {
            "expected_table_regions": 1,
            "fields": [{
                "id": "total-assets",
                "label": "Tổng tài sản",
                "values": ["56.993.245", "54.232.491"],
            }],
        }

        results = evaluate_table_strategies(page, case)

        self.assertEqual([row["strategy"] for row in results], [
            "default", "text_text", "text_lines", "lines_text",
        ])
        self.assertTrue(all(row["detected_tables"] == 1 for row in results))
        self.assertTrue(all(row["table_shapes"] == [[1, 3]] for row in results))
        self.assertTrue(all(row["normalized_anchor_matches"] == 1 for row in results))
        self.assertEqual(page.find_tables.call_count, 4)

    def test_anchor_requires_label_and_values_in_expected_order(self):
        self.assertTrue(anchor_present(
            "Hàng tồn kho 5.634.710 6.082.233",
            "Hàng tồn kho",
            ["5.634.710", "6.082.233"],
        ))
        self.assertFalse(anchor_present(
            "Hàng tồn kho 6.082.233 5.634.710",
            "Hàng tồn kho",
            ["5.634.710", "6.082.233"],
        ))

    def test_normalized_anchor_ignores_diacritics_spaces_and_number_grouping(self):
        self.assertTrue(normalized_anchor_present(
            "Tong taisan 56993245 54.232.491",
            "Tổng tài sản",
            ["56.993.245", "54.232.491"],
        ))
        self.assertFalse(normalized_anchor_present(
            "Tong taisan 54232491 56993245",
            "Tổng tài sản",
            ["56.993.245", "54.232.491"],
        ))

    def test_table_page_text_includes_only_rows_from_selected_page(self):
        tables = [
            {"page_number": 91, "columns": ["label", "value"], "rows": [{"label": "Tổng tài sản", "value": "56.993.245"}]},
            {"page_number": 16, "columns": ["Other"], "rows": [{"Other": "irrelevant"}]},
        ]

        text = table_page_text(tables, 91)
        self.assertIn("Tổng tài sản", text)
        self.assertIn("56.993.245", text)
        self.assertNotIn("irrelevant", text)

    def test_image_upload_scores_tables_on_its_single_page(self):
        case = {"id": "image", "fields": [{
            "id": "revenue", "label": "Revenue", "values": ["100"],
        }]}
        parsed = {
            "chunks": [{"text": "Revenue 100", "metadata": {}}],
            "tables": [{
                "page_number": 1,
                "columns": ["label", "value"],
                "rows": [{"label": "Revenue", "value": "100"}],
            }],
        }

        result = score_parse(case, parsed, None, "synthetic_raster_image_upload_tesseract")

        self.assertEqual(result["detected_tables"], 1)
        self.assertEqual(result["table_anchor_exact_match_count"], 1)

    def test_rasterized_fixture_removes_native_text_layer(self):
        source = fitz.open()
        page = source.new_page()
        page.insert_text((40, 40), "Public report source text")
        original_pdf = source.tobytes()
        source.close()

        raster_pdf = rasterized_single_page_pdf(original_pdf, page_index=0, dpi=120)
        raster = fitz.open(stream=raster_pdf, filetype="pdf")
        self.assertEqual(raster[0].get_text().strip(), "")
        self.assertGreater(len(raster[0].get_images()), 0)
        raster.close()

    def test_native_page_fixture_keeps_text_and_limits_processing_to_labeled_page(self):
        source = fitz.open()
        source.new_page().insert_text((40, 40), "First page decoy")
        source.new_page().insert_text((40, 40), "Labeled source page revenue 100")
        original_pdf = source.tobytes()
        source.close()

        selected = fitz.open(stream=native_single_page_pdf(original_pdf, 1), filetype="pdf")

        self.assertEqual(len(selected), 1)
        self.assertIn("Labeled source page", selected[0].get_text())
        self.assertNotIn("First page decoy", selected[0].get_text())
        self.assertEqual(selected[0].get_images(), [])
        selected.close()

    def test_upload_image_fixture_is_a_real_png_render_of_the_same_pdf_page(self):
        source = fitz.open()
        page = source.new_page(width=200, height=100)
        page.insert_text((20, 30), "Revenue 100 VND")
        original_pdf = source.tobytes()
        source.close()

        image = rasterized_single_page_png(original_pdf, page_index=0, dpi=144)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", image[16:24])
        self.assertEqual((width, height), (400, 200))


if __name__ == "__main__":
    unittest.main()
