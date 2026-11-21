"""Role-scoped document context and deterministic sales findings, separate from the fixed contract."""
import asyncio
from datetime import date, datetime, timedelta
import hashlib
import logging
import re
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from core.agents.runtime import remaining
from core.agents.dashboard.models import StrictModel
from core.models.agents import Evidence
from core.agents.report.sales_performance import month_start
from core.agents.report.labels import uses_vietnamese_labels


class SalesContext(StrictModel):
    retrieval_status: Literal['not_requested', 'available', 'no_evidence', 'access_denied', 'unavailable'] = 'not_requested'
    documents: list[Evidence] = Field(default_factory=list, max_length=5)
    coverage_status: Literal['not_available', 'available', 'access_denied', 'unsupported'] = 'not_available'
    observed_dates: list[date] = Field(default_factory=list, max_length=6500)
    coverage_evidence: list[Evidence] = Field(default_factory=list, max_length=1)
    access_limited: bool = False
    as_of: date = Field(default_factory=lambda: datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date())

    @model_validator(mode='after')
    def validate_sources(self):
        if any(e.source_type != 'document' or not e.citation_id or not e.content or len(e.content)>600
               or not e.metadata.get('document_id') or qualitative_passage(e.content) != e.content for e in self.documents):
            raise ValueError('Invalid retrieved document context')
        if self.documents and self.retrieval_status != 'available':
            raise ValueError('Document context requires successful retrieval')
        if len(set(self.observed_dates)) != len(self.observed_dates) or self.observed_dates != sorted(self.observed_dates):
            raise ValueError('Invalid company coverage dates')
        if any(e.source_type != 'database' or e.source != 'commerce.sales' or not e.citation_id for e in self.coverage_evidence):
            raise ValueError('Invalid SQL coverage provenance')
        return self


async def retrieve_context(knowledge, request, scope=None):
    identity = request.identity
    if not identity or 'documents:read' not in identity.permissions or not identity.document_roles:
        return SalesContext(retrieval_status='access_denied')
    if knowledge is None:
        return SalesContext(retrieval_status='unavailable')
    period = '' if scope is None else f"\nResolved reporting dates: {scope['period']['start']} to {scope['period']['end_exclusive']} (end excluded)."
    scoped = request.model_copy(update={'metadata':{**request.metadata, 'retrieval_method':request.metadata.get('retrieval_method', 'hybrid')},
        'question': request.question + period +
        '\nRetrieve evidence about sales revenue movement, gross profit, pricing, COGS and promotion changes. '
        'Prefer dated operational explanations for the requested period; distinguish general policy from recorded events.'})
    try:
        try:
            items = await asyncio.wait_for(knowledge.retrieve(scoped), remaining(60))
        except (TimeoutError, RuntimeError, ConnectionError):
            if scoped.metadata.get('retrieval_method') == 'bm25':
                raise
            # Preserve document access when optional embedding/reranking services are slow or unavailable.
            scoped = scoped.model_copy(update={'metadata':{**scoped.metadata, 'retrieval_method':'bm25'}})
            items = await asyncio.wait_for(knowledge.retrieve(scoped), remaining(10))
        documents = []
        for item in items[:5]:
            if re.search(r'schema|metric[_ -]contract', item.source, re.I):
                continue
            passage = qualitative_passage(item.content or '')
            if item.source_type != 'document' or not passage or not item.metadata.get('document_id'):
                continue
            key = hashlib.sha256((str(item.metadata['document_id']) + passage).encode()).hexdigest()[:16]
            if any(e.citation_id == 'doc-' + key for e in documents):
                continue
            metadata = {key:value for key, value in item.metadata.items() if key in {'document_id', 'chunk_id', 'chunk_index', 'section_title', 'page_number'}}
            metadata['retrieval_method'] = scoped.metadata['retrieval_method']
            documents.append(item.model_copy(update={'citation_id':'doc-' + key, 'content':passage, 'metadata':metadata}))
        return SalesContext(retrieval_status='available' if documents else 'no_evidence', documents=documents)
    except PermissionError:
        return SalesContext(retrieval_status='access_denied')
    except Exception as error:
        logging.getLogger(__name__).warning('Sales report document retrieval unavailable: %s', type(error).__name__)
        return SalesContext(retrieval_status='unavailable')


def qualitative_passage(text):
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', text):
        sentence = sentence.strip()
        # Documentary context must never introduce an unvalidated numerical report claim.
        if (20 <= len(sentence) <= 600 and not re.search(r'\d|`|^Section:|^\|', sentence)
                and re.search(r'\bsales\b|revenue|profit|pricing|price|cost|cogs|promotion|doanh thu|lợi nhuận|chi phí|khuyến mãi', sentence, re.I)):
            return sentence
    return None


def document_passages(context):
    return [{'text':item.content, 'citations':[item.citation_id]} for item in context.documents]


def date_ranges(dates, *, vi=False):
    ranges = []
    for day in sorted(dates):
        if ranges and day == ranges[-1][1] + timedelta(days=1):
            ranges[-1][1] = day
        else:
            ranges.append([day, day])
    return ', '.join(f'{start} {"đến" if vi else "to"} {end}' if start != end else str(start) for start, end in ranges)


def data_needs(scope, context, *, vi=False):
    needs = []
    if scope['dimension'] != 'all':
        needs.append('Cần tài liệu xác định cách phân bổ số liệu cấp công ty cho nhóm đã chọn.' if vi else
                     'Company comparisons cannot be allocated to this dimension. A documented company-to-dimension mapping is required; adding unrelated order rows will not resolve this.')
    elif context.coverage_status == 'available':
        start = date.fromisoformat(scope['period']['start'])
        start = month_start(start.year, start.month-1)
        end = date.fromisoformat(scope['period']['end_exclusive'])
        expected = {start + timedelta(days=i) for i in range((end-start).days)}
        missing = expected - set(context.observed_dates)
        past = {day for day in missing if day < context.as_of}
        pending = missing - past
        if past:
            needs.append(('Thiếu dữ liệu commerce.sales: ' + date_ranges(past, vi=True) +
                          '. Cần số liệu doanh thu và giá vốn thực tế theo ngày, kể cả tháng đối chiếu.') if vi else
                         'Missing or incomplete commerce.sales records: ' + date_ranges(past) +
                         '. Supply genuine daily date, revenue, cogs records, including the preceding-month baseline. Do not fill missing observations with zero.')
        if pending:
            needs.append('Các ngày trong kỳ chưa kết thúc: ' + date_ranges(pending, vi=True) + '. Số liệu thực tế sẽ có sau khi chốt từng ngày.'
                         if vi else 'Reporting days not yet complete: ' + date_ranges(pending) + '. Collect actual sales after these days close; future values are not backfill data.')
        if not missing:
            needs.append('Dữ liệu theo ngày đã bao phủ các tháng yêu cầu và tháng đối chiếu.' if vi else
                         'Company daily records cover the requested months and preceding-month baseline; no missing sales dates were detected.')
    else:
        needs.append('Chưa xác định được ngày thiếu dữ liệu bán hàng từ nguồn hiện có.' if vi else
                     'Exact missing sales dates could not be checked with the authorized source. Resolve source access/query availability before assuming database rows are absent.')
    statuses = {
        'not_requested':'Document retrieval was not collected for this saved snapshot; regenerate it to retrieve supporting evidence.',
        'access_denied':'Document access is not authorized for this identity. Grant the appropriate existing document role; uploading duplicate data will not fix access.',
        'unavailable':'Document retrieval is temporarily unavailable. Restore the retrieval service before assuming supporting documents are absent.',
        'no_evidence':'No usable role-authorized qualitative sales passage was retrieved for this request; this does not prove that supporting documents are absent.',
        'available':'Retrieved documents provide context; they do not by themselves establish the cause of a sales movement.'}
    if vi:
        statuses = {
            'not_requested': 'Phiên bản báo cáo này chưa truy xuất tài liệu hỗ trợ.',
            'access_denied': 'Tài khoản hiện tại chưa có quyền đọc tài liệu hỗ trợ.',
            'unavailable': 'Dịch vụ truy xuất tài liệu tạm thời không khả dụng.',
            'no_evidence': 'Chưa tìm thấy đoạn tài liệu phù hợp trong phạm vi được cấp quyền.',
            'available': 'Tài liệu truy xuất cung cấp bối cảnh. Cần thêm bằng chứng để xác định nguyên nhân biến động doanh thu.',
        }
    needs.append(statuses[context.retrieval_status])
    if context.access_limited:
        needs.append('Tài liệu từng truy xuất đang được ẩn vì chưa xác minh được quyền truy cập hiện tại.' if vi else
                     'Previously retrieved evidence is withheld because current document access could not be verified. SQL findings and rule results remain available.')
    if context.documents and not document_passages(context):
        needs.append('Tài liệu truy xuất chưa cung cấp diễn giải định tính phù hợp với báo cáo này.' if vi else
                     'Retrieved documents contained no suitable qualitative sales passage for this report. No unsupported numerical or causal explanation has been added.')
    needs.append('Để phân tích nguyên nhân, cần hồ sơ thay đổi giá bán hoặc giá vốn, kết quả chiến dịch, hoặc báo cáo bán hàng đã duyệt cho đúng kỳ.'
                 if vi else 'For causal explanations, provide dated pricing/COGS change logs, campaign execution and outcome reports, or approved sales reviews linked to the requested period and company/source. Index them through the existing document ingestion flow with the correct access roles. A general policy alone does not prove cause.')
    return needs


def build_insights(report, monthly, context):
    from core.agents.report.presentation import SALES_ACTIONS_VI, data_notes, display_value
    groups = monthly or [report]
    complete = sum(all(d['triggered'] is not None for d in group['decisions']) for group in groups)
    partial = sum(any(d['triggered'] is not None for d in group['decisions']) and
                  any(d['triggered'] is None for d in group['decisions']) for group in groups)
    vi = uses_vietnamese_labels(report)
    summary = f'{complete} of {len(groups)} reporting months fully evaluated; {partial} additional months have partial rule results.' if monthly else 'Whole-period rule results are shown; monthly evaluations were not collected for this saved snapshot.'
    if vi:
        summary = (f'Đã đánh giá đầy đủ {complete}/{len(groups)} tháng. Có thêm {partial} tháng đánh giá được một phần.'
                   if monthly else 'Kết quả đánh giá áp dụng cho toàn kỳ báo cáo.')
    actions, findings = [], []
    for fixed in report['decisions']:
        matches = [(group, rule) for group in groups for rule in group['decisions'] if rule['id'] == fixed['id'] and rule['triggered'] is True]
        if not matches:
            continue
        citations = list(dict.fromkeys(e['query_id'] for _, rule in matches for e in rule['evidence']))
        periods = [group['period']['start'][:7] if 'period' in group else
                   report['request']['period']['start'] + ' to ' + str(date.fromisoformat(report['request']['period']['end_exclusive'])-timedelta(days=1)) for group, _ in matches]
        from core.agents.report.presentation import decision_text
        group, rule = matches[-1]
        values = {m['id']: m for m in group['metrics']}
        why = (f"Most recent matching period: {periods[-1]}. Revenue: {display_value(values['company_revenue'])}; "
               f"gross profit: {display_value(values['company_gross_profit'])}.")
        if vi:
            why = (f"Kỳ gần nhất thỏa điều kiện: {periods[-1]}. Doanh thu: {display_value(values['company_revenue'])}. "
                   f"Lợi nhuận gộp: {display_value(values['company_gross_profit'])}.")
        actions.append({'title':fixed['title'], 'why':why, 'action':decision_text(rule, group), 'periods':periods, 'citations':citations})
        if fixed['id'] == 'S04':
            continue
        group, rule = matches[-1]
        metrics = {m['id']:m for m in group['metrics']}
        text = f"{periods[-1]}: {fixed['title']}. Revenue is {display_value(metrics['company_revenue'])}; gross profit is {display_value(metrics['company_gross_profit'])}."
        if vi:
            text = f"{periods[-1]}: {fixed['title']}. Doanh thu: {display_value(metrics['company_revenue'])}. Lợi nhuận gộp: {display_value(metrics['company_gross_profit'])}."
        change = metrics['company_revenue_change_pct']
        if change['status'] == 'available':
            text += (f" Doanh thu thay đổi {display_value(change)} so với {'tháng trước' if monthly else 'kỳ trước cùng độ dài'}."
                     if vi else f" Revenue changed {display_value(change)} against the preceding {'calendar month' if monthly else 'equal-length calendar period'}.")
        if fixed['id'] == 'S03':
            prior_profit = {**metrics['company_gross_profit'], 'value':group['comparison']['prior_gross_profit']} if monthly else None
            if prior_profit is not None:
                text += (f" Lợi nhuận gộp tháng trước: {display_value(prior_profit)}."
                         if vi else f" Prior-month gross profit was {display_value(prior_profit)}.")
        findings.append({'text':text, 'citations':list(dict.fromkeys(e['query_id'] for m in metrics.values() for e in m['evidence']))})
    return {'decision_summary':summary, 'actions':actions, 'findings':findings,
            'document_context':document_passages(context), 'data_needs':data_needs(report['request'], context, vi=vi),
            'data_notes':data_notes(report, include_currency=False),
            'rule_actions':SALES_ACTIONS_VI.copy() if vi else {},
            'coverage_evidence':[e.metadata for e in context.coverage_evidence],
            'documents':[e.model_dump(mode='json') for e in context.documents]}
