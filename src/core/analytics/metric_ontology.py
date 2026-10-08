"""Ánh xạ tên chỉ số thương mại tiếng Việt sang dữ liệu cuộc thi."""

from __future__ import annotations

import re
import unicodedata


METRIC_ONTOLOGY = {
    "revenue": {"aliases": ("revenue", "sales", "doanh thu")},
    "cogs": {"aliases": ("cogs", "cost of goods sold", "giá vốn", "giá vốn hàng bán")},
    "order_count": {"aliases": ("order count", "number of orders", "số đơn hàng", "lượng đơn hàng")},
    "average_order_value": {"aliases": ("average order value", "aov", "giá trị đơn hàng trung bình")},
    "return_rate": {"aliases": ("return rate", "refund rate", "tỷ lệ trả hàng", "tỷ lệ hoàn hàng")},
    "rating": {"aliases": ("rating", "review score", "điểm đánh giá", "xếp hạng đánh giá")},
    "sessions": {"aliases": ("sessions", "website sessions", "lượt truy cập", "phiên truy cập")},
    "bounce_rate": {"aliases": ("bounce rate", "tỷ lệ thoát")},
    "delivery_time": {"aliases": ("delivery time", "shipping time", "thời gian giao hàng")},
    "stock_on_hand": {"aliases": ("stock on hand", "inventory level", "tồn kho", "lượng tồn kho")},
    "stockout_rate": {"aliases": ("stockout rate", "stockout", "tỷ lệ hết hàng", "hết hàng")},
    "days_of_supply": {"aliases": ("days of supply", "số ngày đủ hàng")},
    "fill_rate": {"aliases": ("fill rate", "tỷ lệ đáp ứng")},
    "sell_through_rate": {"aliases": ("sell-through rate", "sell through rate", "tỷ lệ bán hết")},
    "promotion_discount": {"aliases": ("promotion discount", "discount", "khuyến mãi", "mức giảm giá")},
}


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def resolve_metric_names(text: str) -> set[str]:
    """Ưu tiên bí danh dài nhất và trả về tên chỉ số chuẩn."""
    normalized = _normalize(text)
    matches: list[tuple[int, int, str]] = []
    for metric_name, definition in METRIC_ONTOLOGY.items():
        for alias in definition["aliases"]:
            phrase = _normalize(alias)
            pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)")
            matches.extend((match.start(), match.end(), metric_name) for match in pattern.finditer(normalized))

    selected: list[tuple[int, int, str]] = []
    for start, end, metric_name in sorted(matches, key=lambda item: (-(item[1] - item[0]), item[0])):
        if any(start < chosen_end and chosen_start < end for chosen_start, chosen_end, _ in selected):
            continue
        selected.append((start, end, metric_name))
    return {metric_name for _, _, metric_name in selected}
