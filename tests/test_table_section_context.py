import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.chunking.processor import ChunkingProcessor
from core.chunking.processing_output import map_output


class TableSectionContextTest(unittest.TestCase):
    def setUp(self):
        self.heading = {"text": "WACOM INTUOS(CTL-4100)", "metadata": {
            "element_type": "section_header", "page_number": 2,
            "bbox_coordinate_origin": "TOPLEFT", "bbox": [14, 225, 155, 235],
            "section_title": "WACOM INTUOS(CTL-4100)",
            "section_path": ["Specifications", "WACOM INTUOS(CTL-4100)"],
            "source_elements": [{"field": "elements", "index": 0}],
        }}
        self.table = {"table_ref": 0, "metadata": {
            "element_type": "table", "page_number": 2,
            "bbox_coordinate_origin": "TOPLEFT", "bbox": [13, 239, 440, 284],
            "allowed_roles": ["employee"],
            "source_elements": [{"field": "tables", "index": 0}],
        }}
        self.parsed = {"elements": [self.heading, self.table], "tables": [{
            "table_index": 0, "columns": ["Property", "Value"],
            "rows": [{"Property": "Weight", "Value": "230 g, 8.1 oz"}],
            "context": {}, "metadata": {},
        }]}

    def table_chunks(self):
        return [c for c in ChunkingProcessor({"chunk_size": 90, "chunk_overlap": 0}).process(self.parsed)["chunks"]
                if c["metadata"].get("element_type") == "table"]

    def test_wacom_models_remain_distinct_without_mutating_source(self):
        heading = copy.deepcopy(self.heading)
        heading["text"] = "WACOM INTUOS(CTL-4100WL)"
        heading["metadata"].update(section_title=heading["text"],
                                   section_path=["Specifications", heading["text"]], bbox=[14, 294, 172, 304])
        table = copy.deepcopy(self.table)
        table["table_ref"] = 1
        table["metadata"]["bbox"] = [13, 308, 440, 352]
        self.parsed["elements"].extend([heading, table])
        second = copy.deepcopy(self.parsed["tables"][0])
        second["rows"][0]["Value"] = "250 g, 8.8 oz"
        self.parsed["tables"].append(second)
        original = copy.deepcopy(self.parsed)
        chunks = self.table_chunks()
        self.assertEqual(len(chunks), 2)
        for chunk, model, weight in zip(chunks, ["CTL-4100", "CTL-4100WL"], ["230 g", "250 g"]):
            self.assertTrue(chunk["text"].startswith(f"Section: Specifications > WACOM INTUOS({model})\n"))
            self.assertIn(weight, chunk["text"])
            self.assertEqual(chunk["metadata"]["allowed_roles"], ["employee"])
        self.assertEqual(self.parsed, original)
        self.assertIn({"field": "elements", "index": 0}, chunks[0]["metadata"]["source_elements"])

    def test_fragments_repeat_inherited_context(self):
        self.parsed["tables"][0]["rows"] *= 4
        chunks = self.table_chunks()
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c["text"].startswith("Section: Specifications > WACOM INTUOS(CTL-4100)\n") for c in chunks))

    def test_explicit_table_context_wins(self):
        for location in (self.table["metadata"], self.parsed["tables"][0]["metadata"]):
            with self.subTest(location=location):
                location["section_title"] = "Explicit section"
                self.assertTrue(self.table_chunks()[0]["text"].startswith("Section: Explicit section\n"))
                location.pop("section_title")

    def test_uncertain_geometry_does_not_inherit(self):
        variants = [
            {"page_number": 3}, {"page_number": None}, {"bbox": None},
            {"bbox": [300, 239, 440, 284]}, {"bbox": [13, 500, 440, 550]},
            {"bbox": [13, 100, 440, 120]}, {"bbox": [13, float("nan"), 440, 284]},
            {"bbox_coordinate_origin": "BOTTOMLEFT"},
        ]
        original = copy.deepcopy(self.table["metadata"])
        for change in variants:
            with self.subTest(change=change):
                self.table["metadata"] = {**original, **change}
                self.assertFalse(self.table_chunks()[0]["text"].startswith("Section:"))

    def test_appended_or_unreferenced_tables_do_not_take_last_heading(self):
        self.parsed["elements"].insert(1, {"text": "End of controlled policy", "metadata": {"element_type": "text"}})
        self.assertFalse(self.table_chunks()[0]["text"].startswith("Section:"))
        self.parsed["elements"] = [self.heading]
        self.assertFalse(self.table_chunks()[0]["text"].startswith("Section:"))

    def test_mislabeled_reference_keeps_original_position_and_section(self):
        self.table["metadata"].update(element_type="text", layout_type="text",
                                      section_title="Specifications", section_path=["Specifications"])
        self.parsed["elements"].append({"text": "End of controlled policy", "metadata": {"element_type": "text"}})
        duplicate = {"table_ref": 0, "metadata": {"element_type": "table"}}
        self.parsed["elements"].append(duplicate)
        original = copy.deepcopy(self.parsed)
        result = ChunkingProcessor().process(self.parsed)["chunks"]
        tables = [c for c in result if c["metadata"].get("element_type") == "table"]
        self.assertEqual(len(tables), 1)
        self.assertTrue(tables[0]["text"].startswith("Section: Specifications\n"))
        table_index = result.index(tables[0])
        ending_index = next(i for i, c in enumerate(result) if "End of controlled policy" in c["text"])
        self.assertLess(table_index, ending_index)
        self.assertEqual(self.parsed, original)

    def test_worker_mapping_uses_same_reference_resolution_and_original_sources(self):
        self.table["metadata"].update(element_type="text", layout_type="text", section_title="Specifications")
        self.parsed["elements"].append({"table_ref": 0, "metadata": {"element_type": "table"}})
        row = {**self.parsed, "document_id": "DOC-1", "document_metadata": {}}
        doc = {"title": "Sample", "domain": "general", "document_type": "report",
               "allowed_roles": ["employee"], "knowledge_base_active": True}
        original = copy.deepcopy(row)
        mapped, _ = map_output(row, doc)
        self.assertEqual(len(mapped["elements"]), 2)
        table = mapped["elements"][1]
        self.assertEqual(table["metadata"]["element_type"], "table")
        self.assertEqual(table["metadata"]["section_title"], "Specifications")
        self.assertEqual(table["metadata"]["source_elements"],
                         [{"field": "elements", "index": 1}, {"field": "tables", "index": 0}])
        self.assertEqual(table["metadata"]["allowed_roles"], ["employee"])
        self.assertEqual(row, original)

    def test_duplicate_context_or_location_conflicts_fail_in_both_paths(self):
        self.table["metadata"]["section_title"] = "Model A"
        for conflict in ({"section_title": "Model B"}, {"section_path": ["Other", "Model B"]},
                         {"page_number": 3}, {"bbox": [0, 0, 100, 100]}):
            with self.subTest(conflict=conflict):
                self.parsed["elements"] = [self.heading, self.table,
                    {"table_ref": 0, "metadata": {"element_type": "table", **conflict}}]
                with self.assertRaisesRegex(ValueError, "Conflicting table references"):
                    self.table_chunks()
                row = {**self.parsed, "document_id": "DOC-1", "document_metadata": {}}
                doc = {"title": "Sample", "domain": "general", "document_type": "report",
                       "allowed_roles": [], "knowledge_base_active": False}
                with self.assertRaisesRegex(ValueError, "Conflicting table references"):
                    map_output(row, doc)

    def test_invalid_references_are_not_silently_ignored(self):
        for ref in (-1, 1, True, "0", None):
            with self.subTest(ref=ref):
                self.table["table_ref"] = ref
                with self.assertRaisesRegex(ValueError, "Table references"):
                    self.table_chunks()


if __name__ == "__main__":
    unittest.main()
