"""Prepare source-grounded draft questions without looking at retrieval scores."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1/indexed-corpus.jsonl'
OUT = ROOT / 'artifacts/evaluation/fresh-review-20261020'

# Each pair defines a new narrow intent; translations are not independent intents.
# Evidence selectors identify complete source lines, except the explicit PDF interval.
SPECS = [
    ('receiving_exception', 'narrative', 'Manual', 11, 12,
     'Khi nhận hàng phát hiện thiếu hoặc hư hỏng, phải ghi nhận lúc nào và cần những bằng chứng gì?',
     'When an inbound delivery is short or damaged, when must the exception be recorded and what evidence is required?',
     'Ghi nhận thiếu / thừa', 'Record shortages'),
    ('post_campaign', 'narrative', 'Manual', 12, 13,
     'Sau khi chiến dịch kết thúc, cần đối chiếu forecast với những chỉ số nào để cập nhật kế hoạch?',
     'After a campaign ends, which outcomes must be compared with the forecast to revise the plan?',
     'Sau campaign,', 'After the campaign,'),
    ('emergency_po_record', 'narrative', 'Manual', 5, 6,
     'Một PO khẩn cấp phải ghi rõ ba thông tin gì?',
     'Which three details must be documented for an emergency purchase order?',
     'Mọi PO khẩn cấp', 'Every emergency PO'),
    ('stock_240_days', 'narrative', 'Manual', 10, 11,
     'Nếu hàng tồn vượt 240 ngày, ai phải đánh giá và đánh giá những phương án kế toán nào?',
     'For stock exceeding 240 days, who evaluates it and which accounting actions are considered?',
     'Trên 240 ngày:', 'Over 240 days:'),
    ('demand_snapshots', 'narrative', 'Manual', 17, 18,
     'Nhu cầu bình quân trong workbook dùng tối đa bao nhiêu snapshot, và có bắt buộc là các tháng liên tiếp không?',
     'How many snapshots can the workbook use for average demand, and must they be consecutive months?',
     'Nhu cầu bình quân trong workbook', 'Average demand in the workbook'),
    ('rag_policy_fields', 'narrative', 'Manual', 16, 17,
     'Theo phụ lục A, những trường nào nên được giữ cùng nhau trong một chunk chính sách dùng cho RAG?',
     'According to Appendix A, which fields should stay together in a policy chunk used for RAG?',
     'Mã INV-POL-001', 'Policy IDs INV-POL-001'),
    ('blind_count', 'narrative', 'SOP', 1, 1,
     'Khi áp dụng blind count, ai phân công người đếm và người đếm có được xem số lượng hệ thống không?',
     'During a blind count, who assigns the counters and may they see the system quantities?',
     'Warehouse Supervisor phân công', 'The Warehouse Supervisor assigns'),
    ('variant_count', 'narrative', 'SOP', 2, 2,
     'Có được gộp các biến thể gần giống nhau khi kiểm kê không, và cần đếm theo các chiều nào?',
     'May similar variants be combined during a count, and which identifiers must distinguish counted stock?',
     'Đếm theo SKU +', 'Count by SKU +'),
    ('small_adjustment_deadline', 'table', 'Manual', 13, 14,
     'Với điều chỉnh tồn nhỏ có đủ bằng chứng, ai phê duyệt và thời hạn xử lý là bao lâu?',
     'For a small inventory adjustment with sufficient evidence, who approves it and what is the processing deadline?',
     'Row 3:', 'Row 3:'),
    ('disposal_approval', 'table', 'Manual', 13, 14,
     'Thanh lý, scrap hoặc ghi giảm giá trị cần những bên nào phê duyệt và theo thẩm quyền nào?',
     'Which parties approve disposal, scrap, or a write-down, and which authority governs it?',
     'Row 5:', 'Row 5:'),
    ('class_b_investigation', 'table', 'Manual', 6, 7,
     'Nhóm B đóng góp khoảng bao nhiêu phần trăm giá trị tiêu thụ, được kiểm kê bao lâu một lần và có SLA điều tra bao lâu?',
     'Approximately what consumption-value share defines class B, how often is it counted, and what is its variance-investigation SLA?',
     'Row 2:', 'Row 2:'),
    ('recurring_variance', 'mixed_pdf', 'SOP', 3, 3,
     'Theo bảng ngưỡng xử lý trong SOP, chênh lệch lặp lại hoặc giá trị lớn cần hành động gì và ai duyệt?',
     'According to the SOP handling-threshold table, what action and approvers apply to recurring or high-value variances?',
     'Chênh lệch lặp lại, giá trị lớn', 'Recurring, high-value variance'),
]


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    targets = [OUT / name for name in ('cases.json', 'evidence-draft.json', 'review.csv', 'REVIEW.md', 'manifest.json')]
    if any(p.exists() for p in targets):
        raise SystemExit('Review set already exists; refusing to overwrite questions or human edits.')
    rows = [json.loads(line) for line in SOURCE.read_text(encoding='utf-8').splitlines() if line.strip()]
    cases, evidence, review = [], {}, []
    readable = ['# Draft question and evidence review', '', 'Assistant-authored; every intent requires independent human review. Offsets below are Unicode characters in frozen indexed chunk content, not parser-source offsets.', '']
    for number, (slug, category, family, vi_index, en_index, vi_q, en_q, vi_key, en_key) in enumerate(SPECS, 1):
        intent = f'F{number:02d}'
        for language, index, question, key in [('vi', vi_index, vi_q, vi_key), ('en', en_index, en_q, en_key)]:
            matches = [r for r in rows if r['language'] == language and family in r['document_name'] and r['chunk_index'] == index]
            if len(matches) != 1:
                raise ValueError((intent, language, 'ambiguous source'))
            row = matches[0]
            text = row['content']
            if category == 'mixed_pdf':
                start = text.index(key)
                end_key = 'Nghi ngờ gian lận' if language == 'vi' else 'Suspected fraud'
                end = text.index(end_key, start)
            else:
                lines = [line for line in text.splitlines() if key in line]
                if len(lines) != 1:
                    raise ValueError((intent, language, 'ambiguous excerpt'))
                start = text.index(lines[0])
                end = start + len(lines[0])
            quote = text[start:end]
            chunk_id = row['document_id'] + '::chunk::' + str(index)
            evidence_id = f'{intent}-{language}'
            evidence[evidence_id] = dict(intent_id=intent, language=language, category=category,
                chunk_id=chunk_id, document_name=row['document_name'], chunk_index=index,
                source_parser_index=row['metadata']['source_parser_index'],
                chunk_content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                start_char=start, end_char=end, quote=quote,
                annotation_status='draft_pending_human_review', reviewer='',
                equivalent_evidence_reviewed=False)
            for target in ('vi', 'en'):
                cases.append(dict(id=f'{intent}-{language}-to-{target}', intent_id=intent,
                    question=question, query_language=language, target_language=target,
                    direction=f'{language}->{target}', allowed_roles=['admin'],
                    evidence_id=f'{intent}-{target}', category=category))
            review.append(dict(intent_id=intent, language=language, question=question,
                status='pending', reviewer='', answer_supported='', translation_correct='',
                required_details_complete='', equivalent_sources_checked='',
                distinct_from_original_intents='', notes=''))
            readable += [f'## {intent} {slug} ({language}; {category})', '', question, '',
                f'Source: `{chunk_id}`', '', '> ' + quote.replace('\n', '\n> '), '']
    payloads = {'cases.json': {'dataset_id':'fresh-review-20261020', 'cases':cases},
                'evidence-draft.json': {'offset_basis':'frozen indexed chunk content; not source-parser offsets',
                    'status':'assistant draft, not independent held-out labels', 'evidence':evidence}}
    for filename, payload in payloads.items():
        (OUT / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (OUT / 'review.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(review[0]))
        writer.writeheader()
        writer.writerows(review)
    (OUT / 'REVIEW.md').write_text('\n'.join(readable), encoding='utf-8')
    manifest = dict(status='draft_pending_human_review', paired_intents=12, unique_question_texts=24,
        directional_cases=48, corpus_path=SOURCE.relative_to(ROOT).as_posix(),
        corpus_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        original_benchmark_modified=False, inference_run=False,
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in targets if p.exists()})
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    build()
