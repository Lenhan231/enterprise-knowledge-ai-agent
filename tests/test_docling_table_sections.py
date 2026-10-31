import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docling_core.types.doc import DocItemLabel, DoclingDocument, TableCell, TableData, TableItem
from core.chunking.processor import ChunkingProcessor
from document_processing.docling_adapter.result_mapper import map_result


class DoclingTableSectionsTest(unittest.TestCase):
    def table(self, doc, weight):
        doc.add_table(data=TableData(num_rows=1, num_cols=2, table_cells=[
            TableCell(text=text, start_row_offset_idx=0, end_row_offset_idx=1,
                      start_col_offset_idx=column, end_col_offset_idx=column + 1)
            for column, text in enumerate(["Weight", weight])
        ]))

    def mapped(self, doc):
        return map_result(SimpleNamespace(document=doc), {}, TableItem,
                          False, "test", "pdf")

    def test_nested_heading_and_intervening_text_reach_table_chunks(self):
        doc = DoclingDocument(name="Specifications")
        doc.add_title(text="Product information")
        doc.add_heading(text="Specifications", level=1)
        doc.add_heading(text="CTL-4100", level=2)
        doc.add_text(label=DocItemLabel.TEXT, text="An explanatory paragraph before the table.")
        self.table(doc, "230 g")
        doc.add_heading(text="CTL-4100WL", level=2)
        self.table(doc, "250 g")
        doc.add_heading(text="Warranty", level=1)
        self.table(doc, "Not applicable")
        parsed = self.mapped(doc)
        expected = [
            ["Product information", "Specifications", "CTL-4100"],
            ["Product information", "Specifications", "CTL-4100WL"],
            ["Product information", "Warranty"],
        ]
        markers = [e for e in parsed["elements"] if "table_ref" in e]
        for marker, table, path in zip(markers, parsed["tables"], expected, strict=True):
            self.assertEqual(marker["metadata"]["section_path"], path)
            self.assertEqual(table["metadata"]["section_path"], path)
        chunks = [c for c in ChunkingProcessor().process(parsed)["chunks"]
                  if c["metadata"]["element_type"] == "table"]
        self.assertTrue(chunks[0]["text"].startswith("Section: Product information > Specifications > CTL-4100\n"))
        self.assertIn("230 g", chunks[0]["text"])
        self.assertTrue(chunks[1]["text"].startswith("Section: Product information > Specifications > CTL-4100WL\n"))
        self.assertIn("250 g", chunks[1]["text"])

    def test_no_heading_does_not_invent_section(self):
        doc = DoclingDocument(name="No headings")
        self.table(doc, "230 g")
        parsed = self.mapped(doc)
        self.assertIsNone(parsed["tables"][0]["metadata"]["section_title"])
        self.assertEqual(parsed["tables"][0]["metadata"]["section_path"], [])


if __name__ == "__main__":
    unittest.main()
