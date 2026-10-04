import hashlib
import unittest

import fitz

from scripts.ingestion.archive_metric_source_pdfs import verify_source


class MetricSourceArchiveTest(unittest.TestCase):
    def test_source_hash_and_quotes_are_checked_against_cited_physical_pages(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Net revenue was 100 billion VND.")
        content = pdf.tobytes()
        pdf.close()

        source_hash = verify_source("VNM-AR-2024-EN", content, [{
            "page_number": 1,
            "source_quote": "Net revenue was 100 billion VND.",
        }])

        self.assertEqual(source_hash, hashlib.sha256(content).hexdigest())

    def test_archive_refuses_a_quote_that_does_not_match_its_pdf_page(self):
        pdf = fitz.open()
        pdf.new_page().insert_text((72, 72), "Net revenue was 100 billion VND.")
        content = pdf.tobytes()
        pdf.close()

        with self.assertRaisesRegex(ValueError, "quotes do not match"):
            verify_source("VNM-AR-2024-EN", content, [{
                "page_number": 1,
                "source_quote": "Net revenue was 999 billion VND.",
            }])


if __name__ == "__main__":
    unittest.main()
