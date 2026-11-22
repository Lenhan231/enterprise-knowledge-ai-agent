"""Bounded section reports with explicit grounding and coverage."""

import asyncio
import inspect
import json
import time
import logging
from dataclasses import replace
from io import BytesIO

from docx import Document

from core.models.agents import AgentResult
from core.agents.language import VIETNAMESE_STATUS, is_vietnamese
from core.agents.report.grounding import UNAVAILABLE, UNAVAILABLE_VI, VERIFICATION_SCOPE, validate_section
from core.agents.report.sources import ReportClarificationRequired, authorize_sources, collect_sources, serialize_context
from core.agents.report.templates import default_report_template, parse_report_template, render_report_template, section_capability
from core.prompts.report import REPORT_SECTION_PROMPT, REPORT_REPAIR_PROMPT
from core.agents.runtime import deadline, remaining, run_sync
from core.agents.report.planning import adaptive_report_type, inventory_request
from core.agents.report.calendar_scope import FINANCIAL_OVERVIEW, has_sales_period
from core.agents.sql.metric_ontology import resolve_metric_names

MIME_TYPES = {
    "markdown": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ReportAgent:
    def __init__(self, knowledge_agent, analytics_agent, *, llm=None, source_router=None):
        self.knowledge_agent = knowledge_agent
        self.analytics_agent = analytics_agent
        self.llm = llm
        self._owns_llm = llm is None
        self.source_router = source_router

    async def close(self):
        if self._owns_llm and self.llm is not None:
            self.llm.close()

    async def run(self, request):
        result, payload, _ = await self.generate_from_template(
            request, source_mode=request.metadata.get("source_mode"),
            template_choice=request.metadata.get('template_choice'),
            accept_supported_scope=request.metadata.get('accept_supported_scope', False))
        if payload:
            result.answer = payload.decode("utf-8")
        return result

    async def generate_from_template(self, request, filename=None, content=None, *,
                                     source_mode=None, output_format=None,
                                     template_choice=None, accept_supported_scope=False):
        started = time.monotonic()
        end = started + remaining(180)
        token = deadline.set(end - 10)
        try:
            result, payload, media_type = await self._generate_from_template(
                request, filename, content, source_mode=source_mode, output_format=output_format,
                template_choice=template_choice, accept_supported_scope=accept_supported_scope)
            result.metadata.setdefault('timing', {})['total_ms'] = round((time.monotonic()-started)*1000)
            logging.getLogger(__name__).info('report_summary %s', json.dumps({
                'status': result.metadata.get('status'), 'section_count': result.data.get('section_count', 0),
                'task_count': len(result.metadata.get('plan', {}).get('tasks', [])),
                'validated_fact_count': result.metadata.get('fact_validation', {}).get('validated', 0),
                'total_ms': result.metadata['timing']['total_ms'],
            }))
            return result, payload, media_type
        finally:
            deadline.reset(token)

    async def _generate_from_template(self, request, filename=None, content=None, *,
                                      source_mode=None, output_format=None,
                                      template_choice=None, accept_supported_scope=False):
        import re
        vi = is_vietnamese(request.question)
        unavailable = UNAVAILABLE_VI if vi else UNAVAILABLE
        financial_overview = re.search(FINANCIAL_OVERVIEW, request.question, re.I)
        natural_sales = (filename is None and output_format is None and not request.metadata.get('report_type') and
                         (financial_overview or re.search(r'\bsales?\b|\brevenue\b|doanh thu|bán hàng', request.question, re.I)))
        report_type = adaptive_report_type(request)
        natural_inventory = (filename is None and report_type is None and output_format is None
                             and re.search(r'\binventory\b|tồn kho', request.question, re.I)
                             and not re.search(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b', request.question)
                             and has_sales_period(request.question))
        strict_inventory = report_type == 'inventory_operations' or natural_inventory
        if source_mode is None:
            dated_sales = natural_sales and (financial_overview or has_sales_period(request.question))
            source_mode = 'analytics' if report_type == 'sales_performance' or dated_sales or strict_inventory else 'documents'
        authorize_sources(request, source_mode)
        if strict_inventory:
            if filename is not None or output_format is not None or source_mode == 'documents':
                raise ValueError('Inventory operations reports require the immutable JSON template and analytics sources.')
            from core.agents.report.inventory_operations import generate_inventory_report
            return await generate_inventory_report(self, request)
        sales_report = source_mode != 'documents' and (report_type == 'sales_performance' or natural_sales)
        if sales_report:
            if filename is not None:
                raise ValueError('Sales performance reports use the immutable server template; custom templates are not supported.')
            from core.agents.report.sales_performance import generate_sales_report
            return await generate_sales_report(self, request)
        if template_choice not in {None, 'uploaded', 'suggested'} or type(accept_supported_scope) is not bool:
            raise ValueError('Invalid report confirmation choice')
        if output_format is not None and output_format not in MIME_TYPES:
            raise ValueError("Output format must be markdown or docx")
        template = (parse_report_template(filename, content) if filename is not None
                    else default_report_template(output_format or "markdown", vietnamese=vi))
        if output_format and template.format != output_format:
            raise ValueError("Output format conflicts with uploaded template")
        if source_mode != 'documents' and (report_type or inventory_request(request.question) or resolve_metric_names(request.question)):
            from core.agents.report.generation import generate_planned_report
            return await generate_planned_report(
                self, request, template if filename else None, source_mode=source_mode,
                output_format=output_format, template_choice=template_choice,
                accept_supported_scope=accept_supported_scope)
        if source_mode in {'orchestrated', 'combined'} and self.source_router is None:
            from core.agents.sql.analytics_agent import AnalyticsAgent
            from core.agents.decision_support.orchestrator import AgentOrchestrator
            analytics = (self.analytics_agent if isinstance(self.analytics_agent, AnalyticsAgent)
                         else AnalyticsAgent(self.analytics_agent))
            self.source_router = AgentOrchestrator(None, self.knowledge_agent, analytics, llm=self._provider())
        capabilities = {h: section_capability(h, report_type) for h in template.headings} if report_type else None
        if capabilities is not None:
            template = replace(template, preserve_static=True)
        retrieval_headings = tuple(dict.fromkeys(c for c in capabilities.values() if c and c != 'limitations')) if capabilities is not None else template.headings
        try:
            contexts, coverage, limitations, row_coverage = await collect_sources(
                request, retrieval_headings, source_mode, self.knowledge_agent, self.analytics_agent,
                source_router=self.source_router)
        except ReportClarificationRequired as error:
            clarification = str(error)
            return AgentResult(answer=clarification, agent="report", metadata={
                "ok": False, "status": "clarification_required", "clarification_required": True,
                "limitations": [clarification],
            }), b"", MIME_TYPES[template.format]
        if capabilities is not None:
            contexts = {h: contexts.get(capability, []) for h, capability in capabilities.items()}
            coverage = {h: coverage.get(capability, {'included': 0, 'omitted': 0}) for h, capability in capabilities.items()}
        sections = {}
        tables = [[] for _ in template.table_headers]
        section_status = {}
        issues = {}
        evidence = {}
        usable = 0
        provider_failed = False
        for heading in template.headings:
            if capabilities is not None and capabilities[heading] == 'limitations':
                sections[heading] = '\n'.join(limitations) or ('Không phát hiện thêm giới hạn trong tài liệu nguồn.' if vi else 'No additional limitations identified for the supplied document evidence.')
                section_status[heading] = 'complete'
                continue
            supplied = contexts[heading]
            indices = [index for index, owner in enumerate(template.table_sections) if owner == heading]
            headers = [template.table_headers[index] for index in indices]
            body, rows = unavailable, [[] for _ in headers]
            valid = False
            if supplied:
                prompt = self._prompt(request.question, heading, headers, supplied)
                for _ in range(2):
                    try:
                        raw = await asyncio.wait_for(self._generate(prompt), timeout=90)
                    except Exception:
                        provider_failed = True
                        issues[heading] = "provider_unavailable"
                        break
                    try:
                        draft = self._decode_draft(raw)
                        body, rows = validate_section(draft, heading, headers, supplied)
                        valid = body not in {UNAVAILABLE, UNAVAILABLE_VI} or any(rows)
                        if valid:
                            break
                    except (ValueError, TypeError, KeyError, RecursionError) as error:
                        issues[heading] = str(error)[:100]
                        prompt += REPORT_REPAIR_PROMPT.format(issue=issues[heading])
            if valid:
                usable += 1
                issues.pop(heading, None)
                section_status[heading] = "complete"
                for item in supplied:
                    evidence[item.citation_id] = item
            else:
                body, rows = unavailable, [[] for _ in headers]
                section_status[heading] = "failed"
                limitations.append(f"Không thể xác minh mục {heading}." if vi else f"Section unavailable or verification failed: {heading}")
            sections[heading] = body
            for index, values in zip(indices, rows):
                tables[index] = values
        if capabilities is not None:
            for index, rows in enumerate(tables):
                if not rows:
                    tables[index] = [[('Không có dữ liệu nguồn' if vi else 'Unavailable in source data') for _ in template.table_headers[index]]]
                    label = 'Không có dữ liệu cho bảng' if vi else 'Table unavailable'
                    limitations.append(f'{label}: {template.table_sections[index]}: ' + ', '.join(template.table_headers[index]))
            for heading, capability in capabilities.items():
                if capability == 'limitations':
                    sections[heading] = '\n'.join(dict.fromkeys(limitations)) or ('Không phát hiện thêm giới hạn trong tài liệu nguồn.' if vi else 'No additional limitations identified for the supplied document evidence.')
        limitations = list(dict.fromkeys(limitations))
        status = "failed" if not usable else ("partial" if limitations or any(state != 'complete' for state in section_status.values()) else "complete")
        metadata = {"ok": status == "complete", "status": status, "limitations": limitations,
                    "sections": section_status, "coverage": coverage, "row_coverage": row_coverage,
                    "verification_scope": VERIFICATION_SCOPE, "issues": issues,
                    "failure_type": ("source_unavailable" if not any(contexts.values()) else (
                        "provider_unavailable" if provider_failed else "validation_failed")) if status == "failed" else None}
        metadata['template_mode'] = ('marked' if template.marked else 'legacy') if filename else 'generated'
        if report_type:
            metadata.update(report_type=report_type, section_mapping=capabilities)
        if 'orchestration' in row_coverage:
            metadata['source_collection'] = row_coverage['orchestration']
        answer = f"Trạng thái báo cáo: {VIETNAMESE_STATUS[status]}." if vi else f"Report status: {status}."
        result = AgentResult(answer=answer, agent="report",
                             evidence=list(evidence.values()), metadata=metadata,
                             data={"report_format": template.format, "section_count": len(sections)})
        if status == "failed":
            return result, b"", MIME_TYPES[template.format]
        output = render_report_template(template, sections, tables)
        appendix = self._appendix(status, limitations, evidence.values(), coverage, row_coverage, vi=vi)
        if filename:
            appendix += ('Nội dung giữ lại từ mẫu do người dùng cung cấp và chưa được xác minh.\n' if vi else
                         'Only explicit fill regions were replaced. Retained template text is user-provided and unverified.\n'
                         if template.marked else ('Static paragraphs retained and unverified; existing table data replaced.\n' if report_type else
                                                 'Legacy template: body paragraphs and existing table data were replaced.\n'))
        if isinstance(output, str):
            payload = (output + appendix).encode("utf-8")
        else:
            document = Document(BytesIO(output))
            document.add_heading("Trạng thái báo cáo và nguồn" if vi else "Report status and sources", 1)
            for line in appendix.splitlines():
                if line.strip():
                    document.add_paragraph(line.lstrip("# "))
            stream = BytesIO()
            document.save(stream)
            payload = stream.getvalue()
        return result, payload, MIME_TYPES[template.format]

    async def _generate(self, prompt):
        timeout = remaining(60)
        provider = self._provider()
        options = {"max_output_tokens": 4096} if "max_output_tokens" in inspect.signature(provider.generate).parameters else {}
        if inspect.iscoroutinefunction(provider.generate):
            return await asyncio.wait_for(provider.generate(prompt, **options), timeout)
        raw = await run_sync(provider.generate, prompt, **options)
        return await asyncio.wait_for(raw, remaining(60)) if inspect.isawaitable(raw) else raw

    def _provider(self):
        if self.llm is None:
            from core.llm.groq_provider import GroqProvider
            self.llm = GroqProvider()
        return self.llm

    @staticmethod
    def _decode_draft(raw):
        if not isinstance(raw, str) or len(raw) > 100_000:
            raise ValueError("invalid_response_size")
        text = raw.strip()
        if text.startswith("```json") and text.endswith("```"):
            text = text[7:-3].strip()
        return json.loads(text)

    @staticmethod
    def _prompt(question, heading, headers, evidence):
        vi = is_vietnamese(question)
        return REPORT_SECTION_PROMPT.format(
            language="Vietnamese" if vi else "the language of the question",
            unavailable=UNAVAILABLE_VI if vi else UNAVAILABLE,
            question=json.dumps(question, ensure_ascii=False),
            heading=json.dumps(heading, ensure_ascii=False),
            headers=json.dumps(headers, ensure_ascii=False),
            evidence=serialize_context(evidence),
        )

    @staticmethod
    def _appendix(status, limitations, evidence, coverage, rows, *, vi=False):
        lines = (["", "## Trạng thái báo cáo và nguồn", f"Trạng thái: {VIETNAMESE_STATUS[status]}",
                  "Kiểm tra sự tồn tại của trích dẫn và đối chiếu số liệu. Phạm vi kiểm tra không bao gồm diễn giải, phép tính, phạm vi kế toán hay độ bao phủ nguồn.",
                  f"Đã xem xét {rows['considered_rows']} trên {rows['available_rows']} dòng SQL được trả về."]
                 if vi else ["", "## Report status and sources", f"Status: {status}", VERIFICATION_SCOPE,
                             rows["scope"], f"SQL rows considered: {rows['considered_rows']} of {rows['available_rows']} returned."])
        lines.extend(f"- {note}" for note in limitations)
        for heading, counts in coverage.items():
            lines.append(f"Phạm vi mục {heading}: dùng {counts['included']}, bỏ qua {counts['omitted']}."
                         if vi else f"Coverage — {heading}: {counts['included']} included; {counts['omitted']} omitted.")
        for item in evidence:
            page = item.metadata.get("page_number", item.metadata.get("page"))
            location = (f"; trang {page}" if vi else f"; page {page}") if page is not None else ""
            lines.append(f"[{item.citation_id}] {item.source}{location}")
        return "\n".join(lines) + "\n"
