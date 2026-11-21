"""Language and display labels for generated analytics content."""
import re
import unicodedata

from core.agents.sql.metric_ontology import METRIC_ONTOLOGY

_VIETNAMESE_TEXT = re.compile(
    r'[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]',
    re.IGNORECASE,
)
_VIETNAMESE_PHRASE = re.compile(
    r'\b(?:bao cao|bieu do|doanh thu|ton kho|tao dashboard|cho toi|hien thi|so luong|tieng viet)\b',
    re.IGNORECASE,
)


def is_vietnamese(question):
    text = unicodedata.normalize('NFC', question)
    text = re.sub(r"""["“][^"”]*["”]|'[^']*'""", '', text)
    return bool(_VIETNAMESE_TEXT.search(text) or _VIETNAMESE_PHRASE.search(text))


VIETNAMESE_STATUS = {
    'complete': 'Hoàn tất', 'partial': 'Hoàn tất một phần', 'failed': 'Thất bại',
    'empty': 'Không có dữ liệu', 'unavailable': 'Không khả dụng',
    'clarification_required': 'Cần làm rõ',
}

_FIELD_LABELS = {
    'date': 'Ngày', 'period': 'Kỳ', 'snapshot_date': 'Ngày chốt tồn kho',
    'day': 'Ngày', 'month': 'Tháng', 'quarter': 'Quý', 'year': 'Năm',
    'category': 'Danh mục', 'region': 'Khu vực', 'segment': 'Phân khúc',
    'product': 'Sản phẩm', 'product_id': 'Mã sản phẩm', 'product_name': 'Tên sản phẩm',
    'order_id': 'Mã đơn hàng', 'order_source': 'Nguồn đơn hàng', 'currency': 'Tiền tệ',
    'quantity': 'Số lượng', 'units': 'Số đơn vị', 'count': 'Số lượng', 'page_views': 'Lượt xem trang',
    'gross_margin': 'Biên lợi nhuận gộp', 'discount_amount': 'Số tiền giảm giá',
}


def vietnamese_field(name):
    canonical = re.sub(r'^(?:total|sum)_|_(?:total|sum)$', '', name.casefold().replace(' ', '_'))
    if canonical in _FIELD_LABELS:
        return _FIELD_LABELS[canonical]
    for suffix, label in (('_difference', 'Chênh lệch'), ('_percent_change', 'Mức thay đổi theo tỷ lệ')):
        if canonical.endswith(suffix):
            return f'{label} {vietnamese_field(canonical.removesuffix(suffix)).lower()}'
    aliases = METRIC_ONTOLOGY.get(canonical, {}).get('aliases', ())
    label = next((alias for alias in aliases if is_vietnamese(alias)), None)
    return label[0].upper() + label[1:] if label else name
