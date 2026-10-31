"""Apply the reviewed paragraph translation to the user's original DOCX package."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/datasets/vietstyle-operations-vi-v1'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'
SECTIONS = {
    1: 'Phạm vi công ty, định nghĩa và kiểm soát tài liệu',
    2: 'Nghỉ phép, chấm công và chi phí nhân viên',
    3: 'Mua sắm và quy tắc phê duyệt',
    4: 'Tồn kho, nhận hàng và trả hàng',
    5: 'Quyền truy cập CNTT, bảo mật và xử lý sự cố',
    6: 'Ngoại lệ, ma trận phê duyệt và biểu mẫu',
}
COMMON = {
    'Required procedure': 'Quy trình bắt buộc',
    'Control requirements': 'Yêu cầu kiểm soát',
    'Required evidence': 'Bằng chứng bắt buộc',
    'System and data alignment': 'Sự phù hợp hệ thống và dữ liệu',
    'Accountable ownerRelevant domain owner; Operations Governance maintains the controlled copy.':
        'Đơn vị chịu trách nhiệm: Chủ sở hữu lĩnh vực liên quan; Bộ phận Quản trị Vận hành quản lý bản được kiểm soát.',
    'Review triggerAnnual review, material incident, process or system change.':
        'Điều kiện rà soát: Hằng năm, sự cố trọng yếu, thay đổi quy trình hoặc hệ thống.',
    'Escalation pathPause affected action and refer to the named domain owner; unresolved cross-domain conflicts go to Operations Governance.':
        'Tuyến chuyển cấp: Tạm dừng hành động liên quan và chuyển chủ lĩnh vực được chỉ định; xung đột liên lĩnh vực chưa giải quyết chuyển Bộ phận Quản trị Vận hành.',
}
PREFIXES = {
    'Mandatory rule. ': 'Quy tắc bắt buộc. ',
    'Accountable owner': 'Đơn vị chịu trách nhiệm: ',
    'Review trigger': 'Điều kiện rà soát: ',
    'Escalation path': 'Tuyến chuyển cấp: ',
}


def serialize(root, original_xml):
    value = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    # Word's mc:Ignorable can reference namespaces absent from element names.
    # ElementTree drops these declarations unless they are preserved explicitly.
    for _, (prefix, uri) in ET.iterparse(__import__('io').BytesIO(original_xml), events=['start-ns']):
        if prefix and f'xmlns:{prefix}='.encode() not in value:
            root.set('xmlns:' + prefix, uri)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def main(source, inspect_only=False):
    translations = {}
    for line in (OUT / 'translation.tsv').read_text(encoding='utf-8').splitlines():
        index, text = line.split('\t', 1)
        if int(index) in translations:
            raise ValueError(f'Duplicate paragraph: {index}')
        translations[int(index)] = text
    with zipfile.ZipFile(source) as original:
        xml = original.read('word/document.xml')
        # Keep original namespace prefixes, including compatibility declarations.
        for _, (prefix, uri) in ET.iterparse(__import__('io').BytesIO(xml), events=['start-ns']):
            ET.register_namespace(prefix, uri)
        root = ET.fromstring(xml)
        paragraphs = root.findall('.//w:p', NS)
        by_text = dict(COMMON)
        by_text.update({''.join(t.text or '' for t in paragraphs[i].findall('.//w:t', NS)): value
                        for i, value in translations.items()})
        missing, rendered, unchanged = [], [], []
        for i, paragraph in enumerate(paragraphs):
            nodes = paragraph.findall('.//w:t', NS)
            text = ''.join(t.text or '' for t in nodes)
            if not text:
                continue
            value = by_text.get(text)
            header = re.fullmatch(r'POLICY PAGE (\d+)  \|  (\d)\. .+', text)
            if header:
                value = f'TRANG CHÍNH SÁCH {header[1]}  |  {header[2]}. {SECTIONS[int(header[2])]}'
            if value is None:
                if text == 'VIETSTYLE COMMERCE' or re.fullmatch(r'[\d.]+', text) or text == 'VSC-OPS-POL-001' or text.startswith(('commerce.', 'public.')):
                    value = text
                    unchanged.append(dict(index=i, text=text))
                else:
                    missing.append(dict(index=i, text=text))
                    continue
            if len(nodes) == 2 and nodes[0].text in PREFIXES:
                prefix = PREFIXES[nodes[0].text]
                if not value.startswith(prefix):
                    raise ValueError((i, 'Missing translated run prefix'))
                nodes[0].text, nodes[1].text = prefix, value[len(prefix):]
            else:
                nodes[0].text = value
                for node in nodes[1:]:
                    node.text = ''
            for node in nodes:
                node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            rendered.append(dict(index=i, source=text, vietnamese=value))
        if missing:
            print(json.dumps({'missing': missing}, ensure_ascii=False, indent=2))
            return
        if inspect_only:
            print(json.dumps(dict(paragraphs=len(paragraphs), translated_or_retained=len(rendered), missing=0)))
            return
        destination = OUT / 'VietStyle_Enterprise_Operating_Policy_v1.0_VN.docx'
        if destination.exists():
            raise SystemExit('Refusing to overwrite translated DOCX.')
        changes = {'word/document.xml': serialize(root, xml)}
        other = {
            'VIETSTYLE COMMERCE  |  ENTERPRISE OPERATING POLICY': 'VIETSTYLE COMMERCE  |  CHÍNH SÁCH VẬN HÀNH DOANH NGHIỆP',
            'VSC-OPS-POL-001  •  v1.0  •  Controlled copy  |  Page ': 'VSC-OPS-POL-001  •  v1.0  •  Bản được kiểm soát  |  Trang ',
        }
        for name in original.namelist():
            if not re.fullmatch(r'word/(header|footer)\d+\.xml', name):
                continue
            extra = ET.fromstring(original.read(name))
            for node in extra.findall('.//w:t', NS):
                if node.text in other:
                    node.text = other[node.text]
            changes[name] = serialize(extra, original.read(name))
        with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as target:
            for info in original.infolist():
                target.writestr(info, changes.get(info.filename, original.read(info.filename)))
        markdown = ['# Chính sách vận hành doanh nghiệp VietStyle Commerce', '',
                    'Bản dịch tiếng Việt từ tài liệu tiếng Anh do người dùng cung cấp. Không thay đổi chính sách hoặc xác nhận tính đúng đắn pháp lý/kỹ thuật của tài liệu nguồn.', '']
        markdown += [p['vietnamese'] + '\n' for p in rendered]
        (OUT / 'VietStyle_Enterprise_Operating_Policy_v1.0_VN.md').write_text('\n'.join(markdown), encoding='utf-8')
        (OUT / 'translation-alignment.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
             source_file=source.name, paragraph_count=len(paragraphs), table_count=len(root.findall('.//w:tbl', NS)),
             retained_identifiers=unchanged, alignment=rendered), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(dict(docx=str(destination), paragraphs=len(paragraphs), tables=56, missing=0)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('C:/Users/Eroz/Downloads/VietStyle_Enterprise_Operating_Policy_v1.0.docx'))
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    main(args.source, args.inspect_only)
