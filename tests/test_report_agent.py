import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.report_agent import ReportAgent
from core.models.agents import AgentRequest, AgentResult, Evidence, VerifiedIdentity


class ReportAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_generates_docx_in_template_order_with_benchmark_evidence(self):
        knowledge = MagicMock()
        knowledge.run = AsyncMock(return_value=AgentResult(
            answer="The policy is a simulated draft.", agent="knowledge",
            evidence=[Evidence(citation_id="S1", source_type="document", source="policy.docx",
                              content="The policy is a draft.")],
        ))
        analytics = MagicMock()
        analytics.run = AsyncMock(return_value=AgentResult(
            answer="Revenue is 100.", agent="analytics",
            data={"rows": [{"revenue": 100}]},
            metadata={"ok": False, "limitations": ["Source data is unavailable."]},
            evidence=[Evidence(citation_id="S1", source_type="database", source="commerce.sales")],
        ))
        llm = MagicMock()
        llm.generate.side_effect = ["{truncated", json.dumps({
            "sections": {"Monthly Report": "December 2022 [S2]", "Summary": "Draft policy [S1]."},
            "tables": [{"rows": [["Revenue", "100"]]}],
        })]
        agent = ReportAgent(knowledge, analytics, llm=llm)
        document = Document()
        document.add_heading("Monthly Report", 1)
        document.add_heading("Summary", 2)
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "Metric"
        table.rows[0].cells[1].text = "Value"
        source = BytesIO()
        document.save(source)

        request = AgentRequest(question="Create a report", identity=VerifiedIdentity(
            subject="analyst", permissions={"analytics:read"}))
        result, payload, media_type = await agent.generate_from_template(
            request, "template.docx", source.getvalue())

        rendered = Document(BytesIO(payload))
        self.assertEqual(media_type, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertEqual([p.text for p in rendered.paragraphs if p.style.name.startswith("Heading")],
                         ["Monthly Report", "Summary"])
        self.assertEqual(rendered.tables[0].rows[1].cells[0].text, "Revenue")
        self.assertEqual([item.source for item in result.evidence], ["policy.docx", "commerce.sales"])
        self.assertFalse(result.metadata["ok"])
        self.assertEqual(result.metadata["limitations"], ["Source data is unavailable."])
        self.assertIn("The policy is a draft.", llm.generate.call_args.args[0])
        self.assertEqual(llm.generate.call_count, 2)


if __name__ == "__main__":
    unittest.main()
