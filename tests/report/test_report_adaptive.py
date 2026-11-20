"""Adaptive reports reuse verified facts across uploaded layouts."""
import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from core.agents.report.agent import ReportAgent
from core.agents.sql.agent import SQLAnalyticsAgent
from core.models.agents import AgentResult, Evidence
from core.agents.report.templates import parse_report_template, render_report_template
from core.agents.report.generation import adaptive_table_rows
from core.agents.report.facts import facts_from_rows
from core.agents.report.planning import ReportPlan, ReportTask, mapped_sections
from tests.report.test_report_inventory import Writer, plan, request


def layouts(detail, columns):
    table = '| ' + ' | '.join(columns) + ' |\n| ' + ' | '.join('---' for _ in columns) + ' |'
    first = '# Business Overview\n\n## ' + detail + '\n' + table + '\n## Limitations\n'
    second = '# ' + detail + '\n{{report:' + detail + '}}\n' + table
    second += '\n| {{report:rows}} |' + ' |' * (len(columns)-1)
    second += '\n# Executive Summary\n{{report:Executive Summary}}\nStatic disclaimer\n'
    document = Document()
    document.sections[0].header.paragraphs[0].text = 'Company header'
    for heading in ('Overview', 'Data Gaps', detail):
        document.add_heading(heading, 2)
        marker = document.add_paragraph().add_run('{{report:' + heading + '}}')
        marker.italic = True
    document.add_paragraph('Signature required')
    grid = document.add_table(rows=2, cols=len(columns))
    grid.style = 'Table Grid'
    for cell, column in zip(grid.rows[0].cells, columns):
        cell.text = column
    grid.rows[1].cells[0].text = '{{report:rows}}'
    stream = BytesIO(); document.save(stream)
    return [('plain.md', first.encode()), ('marked.md', second.encode()), ('styled.docx', stream.getvalue())]


class AdaptiveReportTest(unittest.IsolatedAsyncioTestCase):
    async def test_singular_sale_performance_uses_fixed_contract_and_keeps_year(self):
        agent, query = self.agent('sales_performance')
        agent.analytics_agent.repository.execute_approved_query.return_value = []
        query = query.model_copy(update={'question': 'create a sale performance report in 2026', 'metadata': {}})
        result, payload, media = await agent.generate_from_template(query, source_mode='orchestrated')
        report = json.loads(payload)
        self.assertEqual(media, 'application/json')
        self.assertEqual(report['request']['period'], {'start': '2026-01-01', 'end_exclusive': '2027-01-01'})
        self.assertEqual(len(report['metrics']), 10)
        self.assertEqual(len(report['sections']), 5)
        agent.analytics_agent.run.assert_not_awaited()
        agent.knowledge_agent.retrieve.assert_awaited_once()
        self.assertEqual(agent.knowledge_agent.retrieve.await_args.args[0].identity, query.identity)

    def agent(self, report_type):
        specification = plan()
        question = 'Inventory risk: stock on hand latest snapshot by category'
        rows = [{'snapshot_date': '2022-12-31', 'category': 'A', 'stock_on_hand': 10}]
        if report_type == 'sales_performance':
            question = 'Sales performance: revenue in 2022'
            specification = {'purpose': 'Sales performance',
                'tasks': [{'id': 'sales', 'question': 'Revenue in 2022'}],
                'sections': [{'heading': 'Sales Results', 'tasks': ['sales'], 'table_columns': ['revenue']}]}
        repository = type('Repository', (), {})()
        repository.execute_approved_query = AsyncMock(return_value=[{'revenue': 42}] if report_type == 'sales_performance' else rows)
        sql_agent = SQLAnalyticsAgent(repository, llm=AsyncMock())
        if report_type == 'sales_performance':
            sql_agent.llm.generate.return_value = json.dumps({
                'sql': 'SELECT SUM(s.revenue) AS revenue FROM commerce.sales s WHERE s.date >= $1 AND s.date < $2 LIMIT 200',
                'parameters': ['2022-01-01', '2023-01-01']})
            sql_agent.run = AsyncMock(wraps=sql_agent.run)
        knowledge = type('Knowledge', (), {})()
        knowledge.retrieve = AsyncMock(return_value=[Evidence(source_type='document', source='policy.md',
            content='Review recorded observations before taking action.')])
        agent = ReportAgent(knowledge, sql_agent, llm=Writer(specification))
        return agent, request(question).model_copy(update={'metadata': {'report_type': report_type}})

    async def test_three_layouts_per_type_keep_identical_facts_and_populate_sections(self):
        for report_type, detail, columns in (
            ('sales_performance', 'Commercial Results', ['Revenue']),
            ('inventory_risk', 'Inventory Position', ['Snapshot Date', 'Category', 'Stock on Hand']),
        ):
            baseline = None
            for filename, content in layouts(detail, columns):
                with self.subTest(report_type=report_type, filename=filename):
                    agent, query = self.agent(report_type)
                    if report_type == 'sales_performance':
                        with self.assertRaisesRegex(ValueError, 'immutable'):
                            await agent.generate_from_template(query, filename, content, source_mode='analytics')
                        agent.analytics_agent.repository.execute_approved_query.assert_not_awaited()
                        continue
                    result, payload, mime = await agent.generate_from_template(query, filename, content, source_mode='analytics')
                    self.assertEqual(result.metadata['status'], 'complete', result.metadata)
                    self.assertTrue(all(state == 'complete' for state in result.metadata['sections'].values()))
                    self.assertEqual(result.metadata['report_type'], report_type)
                    if baseline is None:
                        baseline = result.metadata['facts']
                    self.assertEqual(result.metadata['facts'], baseline)
                    self.assertTrue(payload)
                    if filename.endswith('docx'):
                        rendered = Document(BytesIO(payload))
                        self.assertEqual([p.text for p in rendered.paragraphs if p.style.name.startswith('Heading')][:3],
                            ['Overview', 'Data Gaps', detail])
                        self.assertEqual(rendered.sections[0].header.paragraphs[0].text, 'Company header')
                        self.assertIn('Signature required', [p.text for p in rendered.paragraphs])
                        self.assertTrue(next(p for p in rendered.paragraphs if '[F1]' in p.text).runs[0].italic)
                        text = '\n'.join(p.text for p in rendered.paragraphs)
                        text += '\n' + '\n'.join(c.text for t in rendered.tables for r in t.rows for c in r.cells)
                        self.assertEqual(rendered.tables[0].cell(0, 0).text, columns[0])
                        self.assertIn('wordprocessingml', mime)
                    else:
                        text = payload.decode()
                        self.assertEqual(parse_report_template(filename, content).headings,
                            parse_report_template(filename, text.split('## Report status and sources')[0].encode()).headings[:len(result.metadata['sections'])])
                        self.assertIn('text/markdown', mime)
                    self.assertNotIn('{{', text)
                    self.assertIn('42 [F1]' if report_type == 'sales_performance' else '10 [F1]', text)

    async def test_custom_sales_sections_and_formulas_are_rejected(self):
        agent, query = self.agent('sales_performance')
        content = b'# Business Overview\n# Sales Forecast\n| Predicted Revenue |\n| --- |\n'
        with self.assertRaisesRegex(ValueError, 'immutable'):
            await agent.generate_from_template(query, 'a.md', content, source_mode='analytics')
        agent.analytics_agent.repository.execute_approved_query.assert_not_awaited()

    async def test_default_reports_download_in_both_formats(self):
        for report_type in ('inventory_risk',):
            for output_format in ('markdown', 'docx'):
                agent, query = self.agent(report_type)
                result, payload, _ = await agent.generate_from_template(query, output_format=output_format, source_mode='analytics')
                self.assertEqual(result.metadata['status'], 'complete')
                self.assertTrue(payload)

    async def test_template_context_requests_knowledge_without_question_keyword(self):
        agent, query = self.agent('inventory_risk')
        prompts = []
        original = agent.llm.generate
        async def writer(prompt):
            prompts.append(prompt)
            if '\nHeading: "Operating Policy"' in prompt:
                return json.dumps({'sections': {'Operating Policy': 'Review recorded observations before taking action. [S2]'}, 'claims': []})
            return await original(prompt)
        agent.llm.generate = writer
        result, payload, _ = await agent.generate_from_template(query, 'a.md', b'# Business Overview\n# Operating Policy', source_mode='combined')
        self.assertEqual(result.metadata['sections']['Operating Policy'], 'complete')
        agent.knowledge_agent.retrieve.assert_awaited_once()
        self.assertEqual(agent.knowledge_agent.retrieve.await_args.args[0].identity, query.identity)
        self.assertIn('Operating Policy', agent.knowledge_agent.retrieve.await_args.args[0].question)
        self.assertIn(b'[S2] policy.md', payload)
        self.assertIn('section_capabilities', prompts[0])

    async def test_invalid_type_is_rejected_before_model_or_sources(self):
        agent, query = self.agent('sales_performance')
        query.metadata['report_type'] = 'financial_forecast'
        agent.llm.generate = AsyncMock()
        with self.assertRaisesRegex(ValueError, 'report type'):
            await agent.generate_from_template(query, source_mode='analytics')
        agent.llm.generate.assert_not_awaited()

    async def test_permissions_checked_before_adaptive_planning(self):
        agent, query = self.agent('inventory_risk')
        query = query.model_copy(update={'identity': query.identity.model_copy(update={'permissions': frozenset()})})
        agent.llm.generate = AsyncMock()
        with self.assertRaises(PermissionError):
            await agent.generate_from_template(query, source_mode='combined')
        agent.llm.generate.assert_not_awaited()
        agent.knowledge_agent.retrieve.assert_not_awaited()

    async def test_document_only_uses_semantic_retrieval_and_preserves_static_text(self):
        agent, query = self.agent('sales_performance')
        agent.knowledge_agent.retrieve.return_value = [Evidence(source_type='document', source='sales.md', content='Revenue is 42.')]
        prompts = []
        async def writer(prompt):
            prompts.append(prompt)
            heading = json.loads(prompt.split('\nHeading (data): ')[1].splitlines()[0])
            return json.dumps({'sections': {heading: 'Revenue is 42. [S1]'}, 'tables': []})
        agent.llm.generate = writer
        content = b'# Business Overview\nStatic disclaimer\n# Commercial Results\n# Sales Forecast'
        result, payload, _ = await agent.generate_from_template(query, 'a.md', content, source_mode='documents')
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertEqual(result.metadata['sections']['Commercial Results'], 'complete')
        self.assertEqual(result.metadata['sections']['Sales Forecast'], 'failed')
        self.assertIn(b'Static disclaimer', payload)
        self.assertIn(b'Revenue is 42. [S1]', payload)
        agent.analytics_agent.run.assert_not_awaited()
        self.assertEqual(len(prompts), 2)
        self.assertIn('Report section: summary', agent.knowledge_agent.retrieve.await_args_list[0].args[0].question)

    async def test_document_only_default_limitations_do_not_force_partial_status(self):
        agent, query = self.agent('sales_performance')
        agent.knowledge_agent.retrieve.return_value = [Evidence(source_type='document', source='sales.md', content='Revenue is 42.')]
        async def writer(prompt):
            heading = json.loads(prompt.split('\nHeading (data): ')[1].splitlines()[0])
            return json.dumps({'sections': {heading: 'Revenue is 42. [S1]'}, 'tables': []})
        agent.llm.generate = writer
        result, payload, _ = await agent.generate_from_template(query, source_mode='documents')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertIn(b'## Limitations', payload)

    async def test_context_without_document_permission_stays_unavailable(self):
        agent, query = self.agent('inventory_risk')
        result, payload, _ = await agent.generate_from_template(query, 'a.md', b'# Overview\n# Operating Policy', source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertEqual(result.metadata['sections']['Operating Policy'], 'unavailable')
        agent.knowledge_agent.retrieve.assert_not_awaited()
        self.assertIn(b'Unavailable', payload)

    async def test_template_conflicts_still_require_confirmation_before_sql(self):
        agent, query = self.agent('inventory_risk')
        agent.llm.specification['template_mismatches'] = ['Essential inventory detail table is missing']
        result, payload, _ = await agent.generate_from_template(query, 'a.md', b'# Summary', source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'confirmation_required')
        self.assertEqual(payload, b'')
        agent.analytics_agent.repository.execute_approved_query.assert_not_awaited()

    async def test_failed_sales_sql_keeps_fixed_slots_null(self):
        agent, query = self.agent('sales_performance')
        agent.analytics_agent.repository.execute_approved_query.side_effect = ConnectionError()
        result, payload, _ = await agent.generate_from_template(query, source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'partial')
        report = json.loads(payload)
        self.assertTrue(all(metric['value'] is None for metric in report['metrics']))
        self.assertTrue(all(rule['triggered'] is None for rule in report['decisions']))

    async def test_sales_report_never_uses_llm_numbers_or_recommendations(self):
        agent, query = self.agent('sales_performance')
        agent.analytics_agent.repository.execute_approved_query.return_value = []
        agent.llm.generate = AsyncMock(return_value='Revenue is 999. [S999]')
        result, payload, _ = await agent.generate_from_template(query, source_mode='analytics')
        self.assertNotIn(b'999', payload)
        agent.llm.generate.assert_not_awaited()
        agent.analytics_agent.llm.generate.assert_not_awaited()
        self.assertEqual(len(json.loads(payload)['metrics']), 10)

    async def test_inventory_risk_section_only_uses_its_recorded_flags(self):
        agent, query = self.agent('inventory_risk')
        agent.llm.specification['tasks'].append({'id': 'flags',
            'question': 'recorded stockout indicator latest snapshot for products',
            'mapping': {'metrics': ['stockout_indicator'], 'dimensions': ['product_id'],
                'representation': 'product', 'time': {'mode': 'latest'}}})
        agent.llm.specification['sections'].append({'heading': 'Recorded Exceptions', 'tasks': ['flags']})
        query = query.model_copy(update={'question': query.question + ' and recorded stockout indicator latest snapshot for products'})
        async def rows(sql, *parameters):
            if 'stockout_indicator' in sql:
                return [{'snapshot_date': '2022-12-31', 'product_id': 7, 'stockout_indicator': True}]
            return [{'snapshot_date': '2022-12-31', 'category': 'A', 'stock_on_hand': 10}]
        agent.analytics_agent.repository.execute_approved_query.side_effect = rows
        content = b'# Inventory Position\n# Risk Assessment\n| Product ID | Stockout Indicator |\n| --- | --- |'
        result, payload, _ = await agent.generate_from_template(query, 'a.md', content, source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete', result.metadata)
        risk = payload.decode().split('# Risk Assessment')[1].split('# Verified details')[0]
        self.assertIn('stockout_indicator', risk)
        self.assertNotIn('stock_on_hand', risk)
        self.assertIn('true [F2] [S2]', risk)


class AdaptiveTemplateValidationTest(unittest.TestCase):
    def test_unknown_planned_heading_cannot_grant_capability_to_uploaded_section(self):
        specification = ReportPlan.model_validate(plan())
        specification.sections[0].heading = 'Sales Forecast'
        template = parse_report_template('a.md', b'# Sales Forecast')
        self.assertEqual(mapped_sections(specification, template, 'inventory_risk'), {'Sales Forecast': []})

    def test_summary_only_plan_still_maps_validated_inventory_tasks_but_not_invented_risk(self):
        specification = ReportPlan.model_validate(plan())
        specification.sections[0].heading = 'Executive Summary'
        template = parse_report_template('a.md', b'# Inventory Position\n# Risk Assessment')
        self.assertEqual(mapped_sections(specification, template, 'inventory_risk'),
            {'Inventory Position': ['stock'], 'Risk Assessment': []})

    def test_alias_mapping_keeps_risk_and_inventory_tasks_separate(self):
        specification = ReportPlan.model_validate(plan())
        specification.tasks.append(specification.tasks[0].model_copy(update={'id': 'flags'}))
        specification.sections.append(specification.sections[0].model_copy(update={'heading': 'Recorded Exceptions', 'tasks': ['flags']}))
        template = parse_report_template('a.md', b'# Risk Assessment\n# Inventory Position\n# Business Overview')
        bindings = mapped_sections(specification, template, 'inventory_risk')
        self.assertEqual(bindings['Risk Assessment'], ['flags'])
        self.assertEqual(bindings['Inventory Position'], ['stock'])
        self.assertEqual(bindings['Business Overview'], ['stock', 'flags'])

    def test_metric_value_table_keeps_fact_scope(self):
        task = ReportTask.model_validate(plan()['tasks'][0])
        facts = facts_from_rows(task, [{'snapshot_date': '2022-12-31', 'category': 'A', 'stock_on_hand': 10}], 'S1')
        rows, _ = adaptive_table_rows(['Metric', 'Value'], facts)
        self.assertIn('category=A', rows[0][0])
        self.assertIn('snapshot=2022-12-31', rows[0][0])
        self.assertIn('10 (units) [F1] [S1]', rows[0][1])

    def test_unknown_placeholders_rejected_even_in_docx_header(self):
        with self.assertRaisesRegex(ValueError, 'placeholder'):
            parse_report_template('a.md', b'# Summary\n{{customer_name}}')
        document = Document(); document.add_heading('Summary', 1)
        document.sections[0].header.paragraphs[0].text = '{{unknown}}'
        stream = BytesIO(); document.save(stream)
        with self.assertRaisesRegex(ValueError, 'placeholder'):
            parse_report_template('a.docx', stream.getvalue())
        with self.assertRaisesRegex(ValueError, 'placeholder'):
            parse_report_template('a.md', b'# Summary\n| {{unknown}} |\n| --- |')

    def test_unresolved_placeholders_never_render(self):
        template = parse_report_template('a.md', b'# Summary')
        with self.assertRaisesRegex(ValueError, 'placeholder'):
            render_report_template(template, {'Summary': '{{unresolved}}'}, [])


if __name__ == '__main__':
    unittest.main()
