import sys
import unittest
from io import BytesIO
from pathlib import Path

from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.reports.templates import parse_report_template, render_report_template


class ReportTemplateTest(unittest.TestCase):
    def test_marked_docx_preserves_static_text_styles_headers_and_footers(self):
        source = Document()
        source.sections[0].header.paragraphs[0].text = 'Company header'
        source.sections[0].footer.paragraphs[0].text = 'Company footer'
        source.add_heading('Summary', 1)
        source.add_paragraph('Static disclaimer')
        source.add_paragraph('{{report:Summary}}')
        table = source.add_table(rows=2, cols=1)
        table.rows[0].cells[0].text = 'Value'
        run = table.rows[1].cells[0].paragraphs[0].add_run('{{report:rows}}')
        run.bold = True
        source.add_paragraph('Signature')
        stream = BytesIO(); source.save(stream)
        template = parse_report_template('a.docx', stream.getvalue())
        rendered = Document(BytesIO(render_report_template(template, {'Summary': 'Generated'}, [[[str(i)] for i in range(151)]])))
        self.assertIn('Static disclaimer', [p.text for p in rendered.paragraphs])
        self.assertIn('Signature', [p.text for p in rendered.paragraphs])
        self.assertEqual(rendered.sections[0].header.paragraphs[0].text, 'Company header')
        self.assertEqual(rendered.sections[0].footer.paragraphs[0].text, 'Company footer')
        self.assertEqual(len(rendered.tables), 4)
        self.assertEqual(rendered.tables[-1].rows[-1].cells[0].text, '150')
        self.assertTrue(rendered.tables[0].rows[1].cells[0].paragraphs[0].runs[0].bold)

    def test_explicit_markers_preserve_static_markdown(self):
        template = parse_report_template('a.md', b'# Summary\nCompany disclaimer\n{{report:Summary}}\n| Metric | Value |\n| --- | --- |\n| {{report:rows}} | |\nSignature')
        output = render_report_template(template, {'Summary': 'Generated'}, [[['stock', '10']]])
        self.assertIn('Company disclaimer', output)
        self.assertIn('Signature', output)
        self.assertIn('Generated', output)
        self.assertNotIn('{{report:', output)

    def test_mixed_and_misplaced_markers_rejected(self):
        for content in [b'# Summary\n{{report:Other}}', b'# Summary\n{{report:Summary}}\n# Missing',
                        b'# Summary\n{{report:Summary}}\n{{report:Summary}}']:
            with self.assertRaises(ValueError):
                parse_report_template('a.md', content)

    def test_large_tables_are_split_into_labeled_blocks(self):
        template = parse_report_template('a.md', b'# Details\n| Value |\n| --- |')
        output = render_report_template(template, {'Details': 'Details'}, [[[str(i)] for i in range(151)]])
        self.assertIn('Rows 101–150', output)
        self.assertIn('| 150 |', output)

    def test_markdown_template_keeps_heading_order_and_fills_table(self):
        source = "# Monthly Report\n\n## Summary\n\n## KPIs\n\n| Metric | Value |\n| --- | --- |\n| placeholder | placeholder |\n"
        template = parse_report_template("report.md", source.encode())
        result = render_report_template(template, {
            "Monthly Report": "December 2022",
            "Summary": "Revenue was supported by the validated rows. [S1]",
            "KPIs": "Results below. [S1]",
        }, [[ ["Revenue", "52,454,936.20"] ]])
        self.assertLess(result.index("# Monthly Report"), result.index("## Summary"))
        self.assertLess(result.index("## Summary"), result.index("## KPIs"))
        self.assertIn("| Revenue | 52,454,936.20 |", result)
        self.assertNotIn("placeholder", result)

    def test_docx_template_preserves_headings_and_table_structure(self):
        source = Document()
        source.add_heading("Monthly Report", 1)
        source.add_heading("Summary", 2)
        table = source.add_table(rows=2, cols=2)
        table.rows[0].cells[0].text = "Metric"
        table.rows[0].cells[1].text = "Value"
        table.rows[1].cells[0].text = "placeholder"
        table.rows[1].cells[1].text = "placeholder"
        raw = BytesIO()
        source.save(raw)
        template = parse_report_template("report.docx", raw.getvalue())
        result = render_report_template(template, {
            "Monthly Report": "December 2022",
            "Summary": "Revenue was supported by the validated rows. [S1]",
        }, [[ ["Revenue", "52,454,936.20"] ]])
        rendered = Document(BytesIO(result))
        self.assertEqual([p.text for p in rendered.paragraphs if p.style.name.startswith("Heading")],
                         ["Monthly Report", "Summary"])
        self.assertEqual(rendered.tables[0].rows[1].cells[0].text, "Revenue")

    def test_rejects_unknown_type_and_oversized_template(self):
        with self.assertRaisesRegex(ValueError, "DOCX or Markdown"):
            parse_report_template("report.pdf", b"content")
        with self.assertRaisesRegex(ValueError, "10 MiB"):
            parse_report_template("report.md", b"x" * (10 * 1024 * 1024 + 1))

    def test_replaces_placeholder_prose_and_escapes_table_cells(self):
        template = parse_report_template("a.md", b"# Summary\nplaceholder prose\n| A | B |\n| --- | --- |\n| old | old |")
        output = render_report_template(template, {"Summary": "New text"}, [[["a|b", "c\nd"]]])
        self.assertNotIn("placeholder", output)
        self.assertNotIn("old", output)
        self.assertIn("a&#124;b", output)
        self.assertIn("c<br>d", output)

    def test_docx_multiline_order_and_placeholder_replacement(self):
        source = Document()
        source.add_heading("Summary", 1)
        source.add_paragraph("placeholder")
        source.add_table(rows=1, cols=1).cell(0, 0).text = "Value"
        source.add_paragraph("another placeholder")
        raw = BytesIO()
        source.save(raw)
        template = parse_report_template("a.docx", raw.getvalue())
        output = render_report_template(template, {"Summary": "First\nSecond\n- Bullet"}, [[["100"]]])
        paragraphs = Document(BytesIO(output)).paragraphs
        self.assertEqual([p.text for p in paragraphs], ["Summary", "First", "Second", "Bullet"])
        self.assertEqual(paragraphs[-1].style.name, "List Bullet")

    def test_rejects_excessive_structure_and_tables_without_owner(self):
        with self.assertRaises(ValueError):
            parse_report_template("a.md", "\n".join(f"# Section {i}" for i in range(21)).encode())
        with self.assertRaisesRegex(ValueError, "follow a heading"):
            parse_report_template("a.md", b"| A | B |\n| --- | --- |\n# Summary")


if __name__ == "__main__":
    unittest.main()
