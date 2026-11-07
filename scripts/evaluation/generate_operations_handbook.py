"""Render a fixed synthetic handbook and a separate, unscored review packet.

Uses existing PyMuPDF only. No models, external APIs, or database access.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import fitz

from operations_handbook_content import pages

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / 'artifacts/datasets/bao-an-operations-vi-v1'
FONT_DIR = Path('C:/Windows/Fonts')
REGULAR = FONT_DIR / 'arial.ttf'
BOLD = FONT_DIR / 'arialbd.ttf'
NAVY = (0.08, 0.16, 0.26)
TEAL = (0.0, 0.40, 0.42)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def wrap(text, font, size, width):
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            trial = line + (' ' if line else '') + word
            if font.text_length(trial, fontsize=size) > width:
                if not line or font.text_length(word, fontsize=size) > width:
                    raise ValueError(f'Word exceeds width: {word}')
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


def segments(page):
    values = [dict(id=f"P{page['page']:02d}-B{i+1}", kind='paragraph', text=text)
              for i, text in enumerate(page['paragraphs'])]
    if page['table']:
        values += [dict(id=f"P{page['page']:02d}-T{i}", kind='table_header' if i == 0 else 'table_row',
                        text=' | '.join(row)) for i, row in enumerate(page['table'])]
    return values


def render(data, target):
    regular, bold = fitz.Font(fontfile=str(REGULAR)), fitz.Font(fontfile=str(BOLD))
    for item in data:
        for segment in item['segments']:
            for char in segment['text']:
                if not char.isspace() and not regular.has_glyph(ord(char)):
                    raise ValueError(f'Font missing glyph {char!r}')
    doc = fitz.open()
    layouts = []
    for item in data:
        page = doc.new_page(width=595.28, height=841.89)
        page.insert_font(fontname='BA', fontfile=str(REGULAR))
        page.insert_font(fontname='BAB', fontfile=str(BOLD))
        page.draw_rect(fitz.Rect(0, 0, 595.28, 8), color=None, fill=TEAL)
        page.insert_text((42, 36), 'BẢO AN  /  SỔ TAY VẬN HÀNH  /  MÔ PHỎNG', fontname='BAB', fontsize=9, color=TEAL)
        y = 68
        title_size = 22 if item['page'] == 1 else 17
        for line in wrap(item['title'], bold, title_size, 511):
            page.insert_text((42, y), line, fontname='BAB', fontsize=title_size, color=NAVY)
            y += title_size * 1.35
        label = f"{item['code']}  |  Chủ sở hữu: {item['owner']}  |  Phiên bản 1.0"
        for line in wrap(label, regular, 9, 511):
            page.insert_text((42, y + 3), line, fontname='BA', fontsize=9, color=TEAL)
            y += 13
        y += 18
        for paragraph in item['paragraphs']:
            for line in wrap(paragraph, regular, 11, 511):
                if y > 770:
                    raise ValueError(f"Text overflows page {item['page']}")
                page.insert_text((42, y), line, fontname='BA', fontsize=11, color=NAVY)
                y += 15.8
            y += 11
        if item['table']:
            y += 5
            columns = len(item['table'][0])
            widths = [511 / columns] * columns
            if columns == 3:
                widths = [120, 195, 196]
            if columns == 4:
                widths = [75, 226, 90, 120]
            for index, row in enumerate(item['table']):
                face = bold if index == 0 else regular
                cell_lines = [wrap(cell, face, 9.5, width - 12) for cell, width in zip(row, widths)]
                height = max(len(lines) for lines in cell_lines) * 13 + 14
                if y + height > 776:
                    raise ValueError(f"Table overflows page {item['page']}; adjust authored content/layout")
                x = 42
                for width, lines in zip(widths, cell_lines):
                    page.draw_rect(fitz.Rect(x, y, x + width, y + height), color=(0.73, 0.79, 0.81),
                                   fill=(0.88, 0.94, 0.94) if index == 0 else (0.97, 0.98, 0.99), width=0.5)
                    for j, line in enumerate(lines):
                        page.insert_text((x + 6, y + 15 + j * 13), line,
                                         fontname='BAB' if index == 0 else 'BA', fontsize=9.5, color=NAVY)
                    x += width
                y += height
        page.draw_line((42, 794), (553, 794), color=TEAL, width=0.7)
        page.insert_text((42, 811), 'Dữ liệu giả lập • Hiệu lực mô phỏng: 01/12/2026 • BA v1.0', fontname='BA', fontsize=8, color=NAVY)
        page.insert_text((501, 811), f"{item['page']:02d} / 50", fontname='BAB', fontsize=9, color=TEAL)
        layouts.append(dict(page=item['page'], body_bottom=round(y, 2), scanned=item['scanned']))
        if item['scanned']:
            # Render the complete page, then replace it with an image without a text layer.
            # ponytail: clean 173-DPI scans test OCR necessity, not severe scan degradation.
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2.4, 2.4), colorspace=fitz.csGRAY)
            image = pixmap.tobytes('png')
            rectangle = page.rect
            doc.delete_page(doc.page_count - 1)
            scan = doc.new_page(width=rectangle.width, height=rectangle.height)
            scan.insert_image(rectangle, stream=image)
    doc.set_metadata(dict(title='Sổ tay vận hành Công ty Bảo An — Dữ liệu mô phỏng',
                          author='Synthetic evaluation dataset', subject='Vietnamese enterprise RAG evaluation',
                          creationDate='D:20261023000000+07\'00\'', modDate='D:20261023000000+07\'00\''))
    # Arial aliases space/hyphen/semicolon glyphs to other Unicode code points.
    # Map used glyphs back to authored characters so IDs and evidence extract intact.
    used_text = json.dumps(data, ensure_ascii=False) + 'BẢO AN / SỔ TAY VẬN HÀNH / MÔ PHỎNG Chủ sở hữu: Phiên bản 1.0 Dữ liệu giả lập • Hiệu lực mô phỏng: 01/12/2026 • BA v1.0 0123456789'
    fonts = {info[0]: info for page in doc for info in page.get_fonts()}
    for xref, info in fonts.items():
        face = bold if 'Bold' in info[3] else regular
        mapping = {}
        for char in sorted(set(used_text), key=ord):
            glyph = face.has_glyph(ord(char))
            if glyph and char.isprintable():
                mapping.setdefault(glyph, ord(char))
        entries = [f'<{glyph:04x}> <{code:04x}>' for glyph, code in sorted(mapping.items())]
        cmap = ['/CIDInit /ProcSet findresource begin', '12 dict begin', 'begincmap',
                '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def',
                '/CMapName /BA-Unicode def', '/CMapType 2 def',
                '1 begincodespacerange', '<0000> <FFFF>', 'endcodespacerange']
        for start in range(0, len(entries), 100):
            block = entries[start:start + 100]
            cmap += [f'{len(block)} beginbfchar', *block, 'endbfchar']
        cmap += ['endcmap', 'CMapName currentdict /CMap defineresource pop', 'end', 'end']
        unicode_xref = int(doc.xref_get_key(xref, 'ToUnicode')[1].split()[0])
        doc.update_stream(unicode_xref, '\n'.join(cmap).encode('ascii'))
    doc.save(target, garbage=4, deflate=True)
    doc.close()
    return layouts


def question_specs():
    # Each requirement can have alternatives; tuple values select exact authored segments.
    return [
        ('N01', 'narrative', 'Đợt nghỉ phép 4 ngày công cần báo trước bao lâu và ai xác nhận?',
         'For four working days of planned leave, how much notice is required and who confirms it?',
         [[(7, 'Nghỉ từ 1')]], 'Báo trước 7 ngày làm việc; trưởng bộ phận duyệt và Nhân sự xác nhận số dư.'),
        ('N02', 'narrative', 'Nghỉ bù cho 6 giờ làm thêm đã xác nhận được bao nhiêu ngày và phải dùng trong bao lâu?',
         'How much compensatory leave follows six confirmed overtime hours, and when must it be used?',
         [[(9, 'Một đợt')], [(9, 'Nghỉ bù')]], '0,5 ngày; dùng trong 30 ngày lịch từ xác nhận Nhân sự.'),
        ('N03', 'table', 'Hạn khách sạn tại TP.HCM và ăn uống mỗi người là bao nhiêu, tính theo đơn vị nào?',
         'What are the per-person hotel and meal limits in Ho Chi Minh City, and what time units apply?',
         [[(11, 'Khách sạn Hà Nội')], [(11, 'Ăn uống')]], 'Khách sạn 900.000 VND/người/đêm; ăn uống 200.000 VND/người/ngày.'),
        ('N04', 'calculation', 'Dự toán công tác 5.000.000 VND được tạm ứng tối đa bao nhiêu và quyết toán trong hạn nào?',
         'For an approved VND 5,000,000 trip estimate, what is the maximum advance and settlement deadline?',
         [[(12, 'Tạm ứng tối đa')], [(12, 'Nộp quyết toán')]], 'Tối đa 4.000.000 VND; quyết toán trong 5 ngày làm việc từ kết thúc chuyến đi.'),
        ('N05', 'boundary', 'Hàng hóa đúng 20.000.000 VND cần ai duyệt và tối thiểu mấy báo giá?',
         'For goods costing exactly VND 20,000,000, who approves and how many quotations are required?',
         [[(16, 'G1'), (47, 'MA-01-G1')], [(17, 'Mua hàng hóa')]], 'Trưởng bộ phận; ít nhất 1 báo giá.'),
        ('N06', 'boundary', 'Hàng hóa 20.000.001 VND cần ai duyệt và tối thiểu mấy báo giá?',
         'For goods costing VND 20,000,001, who approves and how many quotations are required?',
         [[(16, 'G2'), (47, 'MA-01-G2')], [(17, 'Mua hàng hóa')]], 'Trưởng bộ phận và Tài chính; ít nhất 3 báo giá độc lập.'),
        ('N07', 'multi_page_table', 'So sánh người duyệt hàng hóa 25 triệu với dịch vụ 25 triệu trong ma trận MA-01.',
         'In matrix MA-01, compare approvers for VND 25 million in goods versus VND 25 million in services.',
         [[(47, 'MA-01-G2'), (16, 'G2')], [(48, 'MA-01-S1'), (19, 'Dịch vụ có')]],
         'Hàng hóa: trưởng bộ phận + Tài chính; dịch vụ: trưởng bộ phận + Mua sắm.'),
        ('N08', 'exception', 'Thiết bị CNTT 60 triệu mua khẩn có được miễn thẩm định không và cần các cấp duyệt bổ sung nào?',
         'Can an urgent VND 60 million IT equipment purchase skip assessment, and which additional approvals apply?',
         [[(24, 'Thiết bị CNTT,')], [(24, 'Thiết bị CNTT có')], [(16, 'G2'), (47, 'MA-01-G2')], [(21, 'Giám đốc Vận hành phải')]],
         'Không miễn; thẩm định CNTT, thêm Giám đốc CNTT, cấp G2 trưởng bộ phận + Tài chính, và GĐ Vận hành trước cam kết mua khẩn.'),
        ('N09', 'exception', 'Chỉ định nguồn được miễn yêu cầu nào và có miễn duyệt ngân sách hoặc bảo mật không?',
         'What does sole-source approval waive, and does it waive budget approval or security review?',
         [[(18, 'Chấp thuận chỉ định')]], 'Chỉ miễn đủ số báo giá; không miễn ngân sách, cấp giá trị, bảo mật hoặc nghiệm thu.'),
        ('N10', 'narrative', 'PO tăng tổng cam kết từ 90 triệu lên 110 triệu được duyệt theo phần tăng hay toàn bộ, và ai duyệt?',
         'If a PO commitment rises from VND 90 million to 110 million, is approval based on the increase or the total, and by whom?',
         [[(20, 'Nếu thay đổi')], [(16, 'G3'), (47, 'MA-01-G3')]], 'Theo tổng 110 triệu; GĐ Vận hành và GĐ Tài chính.'),
        ('N11', 'table', 'ROP tham khảo và đơn vị của BA-014 khác BA-041 như thế nào?',
         'How do the reference reorder points and units differ for BA-014 and BA-041?',
         [[(36, 'BA-014 |')], [(36, 'BA-041 |')]], 'BA-014: 40 chiếc; BA-041: 18 chiếc. Không phải tồn hiện tại.'),
        ('N12', 'table', 'Tra đúng mã BA-107 và BA-170: tên vật tư, đơn vị và ROP là gì?',
         'For exact codes BA-107 and BA-170, what are their item names, units, and reference reorder points?',
         [[(36, 'BA-107 |')], [(36, 'BA-170 |')]], 'BA-107 nhãn kho chống ẩm: 12 cuộn; BA-170 nhãn văn phòng thường: 8 cuộn.'),
        ('N13', 'multi_section', 'Hàng trả về đang QUARANTINE có được cấp phát khẩn không và ai giải phóng?',
         'Can returned goods in QUARANTINE be issued urgently, and who can release them?',
         [[(28, 'Nếu tồn không đủ')], [(33, 'Chỉ QA'), (48, 'MA-01-QA')]], 'Không dùng hàng QUARANTINE bù phiếu khẩn; QA ký giải phóng sau kiểm tra đạt.'),
        ('N14', 'boundary', 'Sai lệch không lặp 2 đơn vị, trị giá 1 triệu, không nghi gian lận thuộc mức nào và ai duyệt?',
         'Which level applies to a non-recurring two-unit variance worth VND 1 million with no fraud suspicion, and who approves?',
         [[(30, 'Mức W1')], [(30, 'W1 |'), (48, 'MA-01-W1')]], 'W1; Quản lý Kho, đồng thời tuân thủ độc lập người duyệt.'),
        ('N15', 'exception', 'Sai lệch 1 đơn vị trị giá 100.000 VND nhưng lặp trong 30 ngày có còn W1 không?',
         'Does a one-unit VND 100,000 variance recurring within 30 days remain W1?',
         [[(30, 'Sai khác lặp lại')], [(30, 'W2 |'), (48, 'MA-01-W2')]], 'Không; W2 bất kể giá trị, Kiểm soát Tồn kho và Tài chính duyệt.'),
        ('N16', 'calculation', 'Nhu cầu 10 đơn vị/ngày với tham số mặc định: ROP và target stock là bao nhiêu?',
         'At demand of 10 units per day with default parameters, what are the reorder point and target stock?',
         [[(31, 'Nhu cầu/ngày')], [(31, 'Inventory position')]], 'ROP 150 đơn vị; target stock 220 đơn vị. Số 10 là giả định đầu vào câu hỏi.'),
        ('N17', 'calculation', 'AVAILABLE 80, Open PO 50, Backorder 20: inventory position bao nhiêu và có tự phát hành PO không?',
         'With AVAILABLE 80, Open PO 50, and Backorder 20, what is inventory position, and may a PO be issued automatically?',
         [[(31, 'Inventory position')], [(31, 'Nếu inventory position')]], '110 đơn vị; không tự phát hành PO. Chưa đủ nhu cầu/ngày để so với ROP.'),
        ('N18', 'multi_section', 'Có yêu cầu chưa đáp ứng trong khi báo 95 ngày cung ứng: trạng thái gì và cần xác minh gì?',
         'When an unmet request coexists with reported 95 days of supply, what status and checks are required?',
         [[(32, 'Khi có yêu cầu')], [(32, 'Đối chiếu tồn')], [(32, 'Kế hoạch Vật tư ghi')]], 'DATA CONFLICT, dừng mua tự động; kiểm tồn/trạng thái/PO/backorder/đơn vị/snapshot/công thức; Kế hoạch và Kho xác nhận.'),
        ('N19', 'multi_section', 'Hồ sơ kiểm kê đang điều tra đã quá 36 tháng có được xóa không?',
         'May inventory-count records under investigation be deleted after 36 months?',
         [[(35, 'Biên bản nhận hàng')], [(46, 'Hồ sơ có điều tra')]], 'Không; giữ đến giải tỏa yêu cầu bảo toàn. Thời hạn thông thường không đủ để xóa.'),
        ('N20', 'narrative', 'Mất thiết bị phải báo trong bao lâu, và hạn CNTT khóa tài khoản khẩn tính từ lúc nào?',
         'How soon must a lost device be reported, and when does the urgent account-lock deadline start?',
         [[(41, 'Mất thiết bị')], [(38, 'Yêu cầu khóa')]], 'Báo trong 15 phút từ phát hiện; khóa trong 30 phút từ xác minh nguồn yêu cầu.'),
        ('N21', 'table', 'P1 và P2 có mục tiêu bắt đầu phản hồi và chu kỳ cập nhật khác nhau thế nào?',
         'How do P1 and P2 differ in response-start targets and update intervals?',
         [[(42, 'P1 |')], [(42, 'P2 |')]], 'P1 ≤15 phút, cập nhật 30 phút; P2 ≤2 giờ, cập nhật 4 giờ. Không phải hạn giải quyết xong.'),
        ('N22', 'narrative', 'RPO và RTO mô phỏng là bao nhiêu, có đồng nghĩa nhau không?',
         'What are the simulated RPO and RTO, and do they mean the same thing?',
         [[(40, 'Mục tiêu mô phỏng')]], 'RPO 24 giờ mất dữ liệu theo thời gian; RTO 8 giờ khôi phục dịch vụ; không đồng nghĩa.'),
        ('N23', 'ocr', 'Trên phiếu BG-026, mã tài sản, sê-ri và hạn hoàn trả là gì?',
         'On form BG-026, what are the asset code, serial number, and return deadline?',
         [[(43, 'Thiết bị LT-026')], [(43, 'Ngày dự kiến')]],
         'LT-026, SIM-LT026; 17/12/2026 trước 17:00. Cần OCR trang 43.'),
        ('N24', 'ocr_calculation', 'Trong SIM-INC-004, mất bao lâu từ phát hiện đến thông báo và từ tiếp nhận đến phản hồi?',
         'In SIM-INC-004, how long elapsed from detection to notification and from receipt to response?',
         [[(44, 'Phát hiện lúc')], [(44, 'Đóng phiếu lúc')]], '8 phút và 7 phút; phân biệt hai mốc. Cần OCR trang 44.'),
        ('N25', 'exception', 'Ngoại lệ tối đa bao lâu và có thể cho phép dùng chung tài khoản không?',
         'How long can an exception last, and can it authorize shared accounts?',
         [[(45, 'Một ngoại lệ')], [(45, 'Không ngoại lệ')]], 'Tối đa 30 ngày lịch; không được miễn quy tắc không dùng chung tài khoản.'),
        ('N26', 'narrative', 'Tài khoản tạm được giữ tối đa bao lâu và có tự thành vĩnh viễn khi chưa thu hồi không?',
         'How long can temporary access last, and does it become permanent if not revoked?',
         [[(38, 'Quyền tạm')]], '14 ngày lịch; không tự thành vĩnh viễn, gia hạn phải có đề nghị mới.'),
        ('N27', 'unanswerable', 'Lương tháng hiện tại của nhân viên Kế hoạch B là bao nhiêu?',
         'What is Planning Employee B\'s current monthly salary?', [], 'Không được cung cấp; không suy ra từ vai trò hoặc biên bản bàn giao.'),
        ('N28', 'unanswerable', 'Tồn AVAILABLE hiện tại của BA-014 là bao nhiêu chiếc?',
         'How many BA-014 units are currently AVAILABLE?', [], 'Không có snapshot tồn thực tế; ROP 40 không phải tồn khả dụng.'),
        ('N29', 'unanswerable', 'Mật khẩu tài khoản quản trị CNTT là gì?',
         'What is the IT administrator account password?', [], 'Không có mật khẩu trong tài liệu; không tạo hoặc suy đoán bí mật.'),
        ('N30', 'unanswerable', 'Một thùng BA-107 chứa bao nhiêu cuộn?',
         'How many BA-107 rolls are in one carton?', [], 'Chưa cung cấp hệ số thùng; không nội suy từ SKU khác.'),
    ]


def make_questions(data):
    questions = []
    for identity, category, vi, en, requirements, answer in question_specs():
        evidence = []
        for number, alternatives in enumerate(requirements, 1):
            converted = []
            for page_number, prefix in alternatives:
                page = data[page_number - 1]
                matches = [s for s in page['segments'] if s['text'].startswith(prefix)]
                if len(matches) != 1:
                    raise ValueError((identity, page_number, prefix, len(matches)))
                segment = matches[0]
                spans = [segment]
                if segment['kind'] == 'table_row':
                    spans.insert(0, next(s for s in page['segments'] if s['kind'] == 'table_header'))
                converted.append(dict(page=page_number, policy_code=page['code'],
                                      requires_ocr=page['scanned'],
                                      all_of=[dict(segment_id=s['id'], start_char=0, end_char=len(s['text']),
                                                   quote=s['text']) for s in spans]))
            evidence.append(dict(id=f'{identity}.R{number}', alternatives=converted))
        questions.append(dict(id=identity, category=category, question_vi=vi, question_en=en,
                              target_document_language='vi', answerable=bool(requirements),
                              expected_answer_draft_vi=answer, requirements=evidence,
                              review_status='draft_pending_independent_review', reviewer='',
                              equivalent_sources_exhaustive=False))
    return questions


def generate(output):
    if not REGULAR.is_file() or not BOLD.is_file():
        raise SystemExit('Arial regular/bold font files are required; no font download is attempted.')
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f'Refusing to overwrite existing dataset: {output}')
    output.mkdir(parents=True, exist_ok=True)
    data = pages()
    for item in data:
        item['segments'] = segments(item)
    write_json(output / 'source.json', dict(dataset_id='bao-an-operations-vi-v1', language='vi',
               synthetic=True, effective_date='2026-12-01', pages=data))
    layouts = render(data, output / 'bao-an-operations.vi.pdf')
    markdown = ['# Sổ tay vận hành Công ty Bảo An', '', '**Dữ liệu hoàn toàn giả lập — phiên bản 1.0.**', '']
    for item in data:
        markdown += [f"## Trang {item['page']:02d} — {item['title']}", '', f"{item['code']} | {item['owner']}", '']
        markdown += [s['text'] + '\n' for s in item['segments']]
    (output / 'handbook.vi.md').write_text('\n'.join(markdown), encoding='utf-8')
    questions = make_questions(data)
    write_json(output / 'questions.draft.json', dict(schema_version=1,
        status='assistant-authored draft, not independent labels; no benchmark run',
        offset_basis='Unicode indexes within source.json segments, not PDF bytes or retrieval chunks',
        scoring='AND over requirements; OR over alternatives; AND over all_of spans; unanswerable separately',
        questions=questions))
    review = ['# Rà soát câu hỏi và bằng chứng / Question review', '',
              '30 ý hỏi, 60 văn bản VI/EN, một PDF tiếng Việt. Chưa chạy retrieval hoặc generation. Nhãn do trợ lý soạn; cần người khác xác minh và bổ sung nguồn thay thế.', '',
              'Offset của trích dẫn thuộc segment trong source.json; không dùng trực tiếp với scorer cũ. Không đưa câu hỏi/đáp án vào index. Các câu không có đáp án chấm riêng bằng tiêu chí từ chối/báo thiếu dữ liệu.', '']
    for q in questions:
        review += [f"## {q['id']} — {q['category']}", '', q['question_vi'], '', q['question_en'], '',
                   '**Đáp án dự kiến (nháp):** ' + q['expected_answer_draft_vi'], '']
        for requirement in q['requirements']:
            review += [f"### {requirement['id']} — chọn một nguồn thay thế đầy đủ", '']
            for alternative in requirement['alternatives']:
                review += [f"Trang {alternative['page']} / {alternative['policy_code']}" + (' / CẦN OCR' if alternative['requires_ocr'] else ''), '']
                review += ['> ' + s['quote'] for s in alternative['all_of']]
                review += ['']
        if not q['answerable']:
            review += ['Không có span đáp án. Người rà phải kiểm toàn bộ tài liệu để xác nhận thông tin thực sự vắng mặt.', '']
    (output / 'REVIEW.md').write_text('\n'.join(review), encoding='utf-8')
    fields = ['id', 'status', 'reviewer', 'question_clear', 'translation_matches', 'evidence_complete',
              'alternative_sources_checked', 'answerability_checked', 'contradictions_checked', 'notes']
    with (output / 'review.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(dict(id=q['id'], status='pending') for q in questions)
    with fitz.open(output / 'bao-an-operations.vi.pdf') as doc:
        if len(doc) != 50:
            raise ValueError('PDF page count is not 50')
        digital = [i + 1 for i, p in enumerate(doc) if p.get_text().strip()]
        scans = [i + 1 for i, p in enumerate(doc) if not p.get_text().strip() and p.get_images()]
        if scans != [43, 44] or len(digital) != 48:
            raise ValueError(('Unexpected PDF text/image layers', digital, scans))
        missing_segments = []
        for item in data:
            if item['scanned']:
                continue
            extracted = ''.join(doc[item['page'] - 1].get_text().split())
            for segment in item['segments']:
                expected = ''.join(segment['text'].replace('|', ' ').split())
                if expected not in extracted:
                    missing_segments.append(segment['id'])
        if missing_segments:
            raise ValueError(('Rendered segments do not match authored text', missing_segments))
    validation = dict(page_count=50, digital_pages=48, scan_pages=scans, table_pages=[p['page'] for p in data if p['table']],
                      continued_table_pages=[47, 48], vietnamese_glyph_coverage='passed',
                      digital_segment_text_alignment='passed (whitespace and table separators excluded)', body_layout_bounds='passed',
                      question_intents=len(questions), bilingual_question_texts=2 * len(questions),
                      answerable_intents=sum(q['answerable'] for q in questions),
                      unanswerable_intents=sum(not q['answerable'] for q in questions),
                      exact_evidence_selectors='passed', independent_human_review=False,
                      ocr_accuracy_measured=False, benchmark_run=False, layouts=layouts)
    write_json(output / 'validation.json', validation)
    readme = '''# Bảo An: synthetic Vietnamese operations handbook

## Start here

- bao-an-operations.vi.pdf: exactly 50 A4 pages, Vietnamese; 48 digital pages and two image-only form pages (43–44).
- handbook.vi.md and source.json: editable reference text and structured authoring source, including page/segment IDs. These include scan transcriptions and must NOT be indexed alongside the PDF in an OCR experiment.
- REVIEW.md: 30 draft intents / 60 VI+EN question texts with source evidence; four unanswerable intents. Only VI document retrieval exists here, so there are two query-language directions, not four.
- questions.draft.json: requirements and alternative evidence. Offsets are segment-local Unicode indexes in source.json, not parser offsets and not retrieval chunk IDs. This is not directly compatible with the old evidence-v3 scorer.
- review.csv: independent label/translation/alternative/answerability review checklist.
- validation.json and manifest.json: structural checks and initial file hashes.

## Content and testing intent

Pages 1–4: document control and definitions; 5–14: HR/expenses; 15–24: procurement; 25–36: warehouse/returns; 37–44: IT/security; 45–50: exceptions, matrices, forms. Every policy, threshold, organization, person, and event is fictional. This is a new synthetic dataset, not evidence of real enterprise performance and not part of the Review2 measured results.

Tests cover similar rules with different scope, inclusive/exclusive thresholds, exact item IDs, arithmetic with stated inputs, table header/row association, multiple sections, the approval matrix continuing across pages47–48, and image-only form extraction. The two clean grayscale scans are approximately173 DPI; they test OCR necessity, not severe noise or handwriting. Other mixed table/prose pages remain digital.

The PDF deliberately repeats some rules in its matrix. Initial alternative labels are not exhaustive; reviewers must search all sections. Do not require one exact chunk if a different passage fully supports the answer. Multi-section questions need all required components; table evidence includes a header and row.

## Before experiments

1. Review the PDF's business consistency and both language versions of each question. Mark independent review truthfully; don't assume assistant labels are certified.
2. Add valid equivalent evidence; confirm unanswerable questions are unsupported. The original corpus was written together with questions, so this is a controlled synthetic challenge, not an independently authored held-out test.
3. Freeze a reviewed version and new manifest before inference. Keep questions, answers, source.json and Markdown out of the search index; ingest ONLY the PDF for the PDF/OCR test.
4. Record parser/OCR mode and model versions. Map parsed evidence back to authored page/segment text with verified alignment. Record table, header, mixed-content, scan and multi-page extraction failures separately.
5. Run the current system unchanged as baseline, recording chunk count, lengths, candidate recall@30, complete evidence@10, Recall/MRR/nDCG, and latency. Score answer correctness, citations, refusal and OCR separately using reviewed labels. No predictions or measured results are supplied here.
6. Tune on separate development questions. Preserve an untouched reviewed test subset; bilingual versions of one intent belong together. Do not tune and report the same questions as independent test evidence.

## Reproduce

From the repository root on Windows, using the existing PyMuPDF installation:

```
.venv/Scripts/python.exe -X utf8 scripts/evaluation/generate_operations_handbook.py --output artifacts/datasets/bao-an-operations-vi-v1-rebuild
```

The builder uses Arial from C:/Windows/Fonts, refuses to overwrite a nonempty folder, and makes no network/model/database calls. Content is authored in scripts/evaluation/operations_handbook_content.py. Document hashes can vary with PDF serializer IDs across builds; each generated manifest describes its own outputs. After authoring edits, regenerate into a new version rather than overwriting frozen inputs.
'''
    (output / 'README.md').write_text(readme, encoding='utf-8')
    manifest = dict(dataset_id='bao-an-operations-vi-v1', created='2026-10-23', synthetic=True,
                    language='vi', page_count=50, question_label_status='draft_pending_independent_review',
                    no_inference=True, files={p.name:digest(p) for p in sorted(output.iterdir()) if p.is_file()},
                    builder_sources={str(p.relative_to(ROOT)).replace('\\', '/'):digest(p)
                                     for p in (Path(__file__).resolve(), Path(__file__).with_name('operations_handbook_content.py'))})
    write_json(output / 'manifest.json', manifest)
    print(json.dumps(dict(output=str(output), pages=50, digital_pages=48, scan_pages=scans,
                          questions=len(questions), label_status='draft', pdf_bytes=(output / 'bao-an-operations.vi.pdf').stat().st_size), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args()
    generate(args.output.resolve())
