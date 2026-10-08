"""Ontology metric cho schema ``commerce`` trên Supabase.

Mỗi metric mô tả cả alias lẫn ``source``, ``formula``, ``grain`` và ``unit``.
Các Agent dùng metadata này để chọn query hợp lệ và không diễn giải vượt quá
những gì dataset thực sự chứa.
"""

from __future__ import annotations

import re
import unicodedata


METRIC_ONTOLOGY = {
    # commerce.sales: chỉ số tổng hợp theo ngày ở cấp toàn công ty.
    "revenue": {
        "aliases": ("revenue", "sales", "doanh thu"),
        "source": "commerce.sales",
        "formula": "SUM(revenue)",
        "grain": "day",
        "aggregation": "sum",
        "unit": "currency",
        "dimensions": ("date",),
        "currency": "dataset_currency_unknown",
        "limitations": ("Không có region, category hoặc product.",),
    },
    "cogs": {
        "aliases": ("cogs", "cost of goods sold", "giá vốn", "giá vốn hàng bán"),
        "source": "commerce.sales",
        "formula": "SUM(cogs)",
        "grain": "day",
        "aggregation": "sum",
        "unit": "currency",
        "dimensions": ("date",),
        "currency": "dataset_currency_unknown",
        "limitations": ("Chỉ là COGS cấp toàn công ty.",),
    },
    # Metric riêng để tránh nhầm với sales.Revenue khi cần phân tích vùng.
    "regional_revenue": {
        "aliases": ("regional revenue", "revenue by region", "doanh thu theo khu vực"),
        "source": "commerce.orders + commerce.order_items + commerce.geography",
        "formula": "SUM(quantity * unit_price - discount_amount)",
        "grain": "order_item",
        "aggregation": "sum",
        "unit": "currency",
        "dimensions": ("order_date", "region"),
        "currency": "dataset_currency_unknown",
        # Chính sách MVP: chỉ xem đơn đã giao là doanh thu thực hiện.
        "filters": ("orders.order_status = 'delivered'",),
        "limitations": ("Có thể không khớp sales.Revenue do khác pipeline và định nghĩa.",),
    },
    "order_count": {
        "aliases": ("order count", "number of orders", "số đơn hàng", "lượng đơn hàng"),
        "source": "commerce.orders (+ commerce.geography khi lọc theo region)",
        "formula": "COUNT(DISTINCT order_id)",
        "grain": "order",
        "aggregation": "count_distinct",
        "unit": "orders",
        "dimensions": ("order_date", "order_status", "region"),
    },
    "average_order_value": {
        "aliases": ("average order value", "aov", "giá trị đơn hàng trung bình"),
        "source": "commerce.orders + commerce.order_items (+ commerce.geography khi lọc theo region)",
        "formula": "SUM(quantity * unit_price - discount_amount) / COUNT(DISTINCT order_id)",
        "grain": "order",
        "aggregation": "ratio",
        "unit": "currency_per_order",
        "dimensions": ("order_date", "region"),
    },
    "return_rate": {
        "aliases": ("return rate", "refund rate", "tỷ lệ trả hàng", "tỷ lệ hoàn hàng"),
        "source": "commerce.returns + commerce.orders (+ commerce.geography khi lọc theo region)",
        "formula": "COUNT(DISTINCT returns.order_id)::numeric / NULLIF(COUNT(DISTINCT orders.order_id), 0)",
        "grain": "order",
        "aggregation": "ratio",
        "unit": "percent",
        "dimensions": ("return_date", "region", "product_id"),
        "limitations": ("Đây là tỷ lệ đơn có return, không phải tỷ lệ số lượng sản phẩm trả.",),
    },
    "rating": {
        "aliases": ("rating", "review score", "điểm đánh giá", "xếp hạng đánh giá"),
        "source": "commerce.reviews",
        "formula": "AVG(rating)",
        "grain": "review",
        "aggregation": "mean",
        "unit": "score",
        "dimensions": ("review_date", "product_id"),
    },
    "sessions": {
        "aliases": ("sessions", "website sessions", "lượt truy cập", "phiên truy cập"),
        "source": "commerce.web_traffic",
        "formula": "SUM(sessions)",
        "grain": "day",
        "aggregation": "sum",
        "unit": "sessions",
        "dimensions": ("date", "traffic_source"),
    },
    "bounce_rate": {
        "aliases": ("bounce rate", "tỷ lệ thoát"),
        "source": "commerce.web_traffic",
        "formula": "AVG(bounce_rate)",
        "grain": "day",
        "aggregation": "mean",
        "unit": "percent",
        "dimensions": ("date", "traffic_source"),
    },
    "delivery_time": {
        "aliases": ("delivery time", "shipping time", "thời gian giao hàng"),
        "source": "commerce.shipments + commerce.orders + commerce.geography khi lọc theo region",
        "formula": "AVG(delivery_date - ship_date)",
        "grain": "shipment",
        "aggregation": "mean",
        "unit": "days",
        "dimensions": ("ship_date", "region"),
    },
    "stock_on_hand": {
        "aliases": ("stock on hand", "inventory", "inventory level", "tồn kho", "lượng tồn kho"),
        "source": "commerce.inventory",
        "formula": "SUM(stock_on_hand) within one snapshot",
        "grain": "product_snapshot",
        "aggregation": "sum",
        "unit": "units",
        "dimensions": ("snapshot_date", "category", "segment", "product_id"),
        "limitations": ("Không cộng stock_on_hand giữa các snapshot khác nhau.",),
    },
    "stockout_rate": {
        "aliases": ("stockout rate", "stockout", "tỷ lệ hết hàng", "hết hàng"),
        "source": "commerce.inventory",
        "formula": "COUNT(*) FILTER (WHERE stockout_flag IS TRUE)::numeric / NULLIF(COUNT(*), 0)",
        "grain": "product_snapshot",
        "aggregation": "ratio",
        "unit": "percent",
        "dimensions": ("snapshot_date", "category", "segment"),
        "limitations": ("Đo tỷ lệ SKU bị gắn cờ, không phải tỷ lệ product-days hết hàng.",),
    },
    "days_of_supply": {
        "aliases": ("days of supply", "số ngày đủ hàng"),
        "source": "commerce.inventory",
        "formula": "AVG(days_of_supply) within one snapshot",
        "grain": "product_snapshot",
        "aggregation": "mean",
        "unit": "days",
        "dimensions": ("snapshot_date", "category", "segment"),
    },
    "fill_rate": {
        "aliases": ("fill rate", "tỷ lệ đáp ứng"),
        "source": "commerce.inventory",
        "formula": "AVG(fill_rate) within one snapshot",
        "grain": "product_snapshot",
        "aggregation": "mean",
        "unit": "percent",
        "dimensions": ("snapshot_date", "category", "segment"),
    },
    "sell_through_rate": {
        "aliases": ("sell-through rate", "sell through rate", "tỷ lệ bán hết"),
        "source": "commerce.inventory",
        "formula": "AVG(sell_through_rate) within one snapshot",
        "grain": "product_snapshot",
        "aggregation": "mean",
        "unit": "percent",
        "dimensions": ("snapshot_date", "category", "segment"),
    },
    "promotion_discount": {
        "aliases": ("promotion discount", "discount", "khuyến mãi", "mức giảm giá"),
        "source": "commerce.order_items + commerce.promotions",
        "formula": "SUM(discount_amount)",
        "grain": "order_item",
        "aggregation": "sum",
        "unit": "currency",
        "dimensions": ("order_date", "promo_id"),
    },
}


def get_metric_definition(metric_name: str) -> dict:
    """Trả về định nghĩa chuẩn; báo lỗi rõ ràng với metric không được hỗ trợ."""
    try:
        return METRIC_ONTOLOGY[metric_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported metric: {metric_name}") from exc


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
