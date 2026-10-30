"""Ontology metric cho schema ``commerce`` trên Supabase.

Mỗi metric mô tả cả alias lẫn ``source``, ``formula``, ``grain`` và ``unit``.
Các Agent dùng metadata này để chọn query hợp lệ và không diễn giải vượt quá
những gì dataset thực sự chứa.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


CATALOG_PATH = Path(__file__).resolve().parents[3] / "data/semantic/vietstyle_metrics_v1.yaml"


class InventoryMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    description: str
    version: Literal["1.0.0"]
    domain: Literal["inventory_management"]
    aliases: dict[str, list[str]]
    source: str
    source_columns: dict[str, list[str]]
    formula: str | None
    scalar_formula: str | None = None
    grain: Literal["product_snapshot"]
    dimensions: list[str]
    date_field: Literal["commerce.inventory.snapshot_date"]
    temporal_semantics: str
    aggregation: str
    unit: str
    eligibility_filters: list[str]
    null_handling: str
    zero_denominator: str
    join_requirements: list[str]
    provenance: Literal["source_defined", "team_defined", "unresolved"]
    definition_status: Literal["executable", "unresolved", "draft"]
    approval_status: Literal["team_accepted", "business_approved", "unreviewed"]
    business_approval_status: str
    validation_status: str
    currency: str
    snapshot_required: bool
    evidence: list[str]
    limitations: list[str]
    examples: dict[str, str]
    clarification: str | None = None

    @model_validator(mode="after")
    def validate_definition(self):
        if not all(self.aliases.get(language) and self.examples.get(language) for language in ("en", "vi")):
            raise ValueError("English and Vietnamese aliases/examples are required")
        if not self.evidence or not self.source_columns or not self.dimensions:
            raise ValueError("Evidence, source columns and dimensions are required")
        if self.definition_status == "executable" and (not self.formula or self.provenance == "unresolved"):
            raise ValueError("Executable definitions require a resolved formula")
        if self.definition_status == "unresolved" and (self.formula is not None or not self.clarification):
            raise ValueError("Unresolved definitions cannot supply executable SQL")
        return self


def load_inventory_catalog(path=CATALOG_PATH):
    catalog = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if catalog.get("catalog_version") != "1.0.0" or catalog.get("domain") != "inventory_management":
        raise ValueError("Unsupported inventory catalog version or domain")
    metrics = {}
    for entry in catalog["metrics"]:
        definition = InventoryMetric.model_validate(entry).model_dump(exclude_none=True)
        name = definition.pop("id")
        if name in metrics:
            raise ValueError(f"Duplicate metric ID: {name}")
        definition["aliases_by_language"] = definition["aliases"]
        definition["aliases"] = tuple(alias for values in definition["aliases"].values() for alias in values)
        if definition["snapshot_required"] and definition.get("formula"):
            definition["formula"] += " within one snapshot"
        metrics[name] = definition
    if not metrics:
        raise ValueError("Inventory catalog cannot be empty")
    return metrics


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
    "gross_profit": {
        "aliases": ("gross profit", "lợi nhuận gộp"),
        "source": "commerce.sales",
        "formula": "SUM(revenue) - SUM(cogs)",
        "grain": "day",
        "aggregation": "derived",
        "unit": "currency",
        "dimensions": ("date",),
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


METRIC_ONTOLOGY.update(load_inventory_catalog())

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
    names = {metric_name for _, _, metric_name in selected}
    if "stock_on_hand" in names and len(names) > 1 and not re.search(r"stock on hand|inventory levels?|l??ng t?n kho", normalized):
        names.remove("stock_on_hand")
    if "fill_rate" in names and re.search(r"lowest|highest|worst|best|th?p nh?t|cao nh?t|t?ng s?n ph?m", normalized) and not re.search(r"average|mean|trung b?nh", normalized):
        names.remove("fill_rate")
        names.add("stored_fill_rate")
    return names
