"""Decision domains and evidence scope for the synthetic Commerce dataset."""

COMMERCE_DECISION_PROFILES = {
    "inventory_allocation": {
        "label": "Inventory allocation",
        "query_terms": (
            "inventory", "stock", "stockout", "overstock", "fill rate", "allocation",
            "replenishment", "sku", "tồn kho", "thiếu hàng", "hết hàng", "phân bổ tồn kho",
            "product availability", "item availability", "products unavailable", "unavailable products",
            "products being unavailable",
            "out-of-stock products", "sản phẩm không có sẵn", "tình trạng sẵn hàng",
            "bổ sung hàng", "lead time", "fulfillment center", "supplier", "smart inventory",
            "low stock", "low in stock", "out of stock", "item level", "category level",
            "stock alert", "inventory visibility", "inventory feed", "supplier readiness",
            "facility capacity", "daily updates", "multi-location", "transfer workflow",
            "stock transfer", "demand planning", "inventory performance by location",
            "regional replenishment", "location-level inventory", "service target",
            "service-level target", "in-stock rate", "out-of-stock rate", "inventory health report",
            "reorder point", "reorder points", "stocktake", "stocktake results",
            "inventory records", "inventory tracking", "usual sales", "supplier reliability",
            "seasonal demand",
        ),
        "retrieval_query": (
            "inventory placement allocation stock availability stockout overstock replenishment "
            "product availability item availability unavailable products out-of-stock products "
            "low stock out of stock item level category level alerts visibility "
            "lead time fulfillment center supplier smart inventory inventory feed supplier readiness "
            "warehouse facility capacity daily updates multi-location inventory stock transfer "
            "transfer workflow demand planning inventory performance by location "
            "regional replenishment location-level inventory fill rate in-stock rate "
            "out-of-stock rate inventory health report service-level target stocktake stocktake results "
            "inventory records inventory tracking reorder point reorder points usual sales "
            "supplier reliability seasonal demand"
        ),
        "dashboard_keys": (
            "inventory_by_year", "inventory_latest_by_category", "inventory_latest_flag_overlap",
        ),
        "source_tables": ("commerce.inventory",),
        "limitations": (
            "The supplied data has no supplier lead time, demand forecast, ordering cost, holding cost, "
            "warehouse location, or approved service-level target.",
            "The schema has no separate low-stock alert or seller-defined minimum-stock threshold; do not infer low-stock status from stockout or overstock counts.",
            "Yearly stockout_snapshots count inventory rows flagged stockout, not distinct stockout incidents. "
            "Latest category stockout_products and overstock_products are overlapping flag counts, not disjoint stock pools. "
            "The separate latest-snapshot overlap aggregate reports how many rows carry both flags; none of these category aggregates "
            "establishes transferable surplus or justifies shifting inventory between categories.",
            "days_of_supply is excluded because the supplied values are anomalously high.",
        ),
    },
    "promotion_planning": {
        "label": "Promotion planning",
        "query_terms": (
            "promotion", "promotional", "campaign", "discount", "markdown", "rollback",
            "coupon", "voucher", "khuyến mãi", "khuyến mại", "chiết khấu", "giảm giá",
            "holdout", "treatment group", "control group", "incremental sales", "incrementality",
            "causal lift", "experiment-based", "ghost ads", "iroas",
            "marketing plan", "target market", "marketing goals", "campaign budget",
            "promotion budget", "measure campaign results", "review campaign results",
        ),
        "retrieval_query": (
            "promotion campaign performance reporting attributed sales advertising spend ROAS "
            "measurement budget comparison discount markdown price inventory seasonal promotion "
            "incrementality causal lift treatment control group holdout experiment incremental sales iROAS "
            "marketing plan target market marketing goals campaign budget promotion budget "
            "measure campaign results review campaign results"
        ),
        "dashboard_keys": ("promotions_by_year", "promotions_by_campaign"),
        "source_tables": ("commerce.orders", "commerce.order_items", "commerce.products", "commerce.promotions"),
        "limitations": (
            "Promotion-tagged and untagged orders are descriptive groups, not a causal uplift estimate; "
            "the dataset has no randomized holdout.",
            "Product-level catalog COGS supports a merchandise gross-profit/margin proxy from order-item prices and discounts, but this is not contribution margin. Campaign spend, campaign-attributed traffic, and a customer-level counterfactual are absent, so ROI and incremental profitability cannot be established.",
            "Campaign-window net item sales attribute tagged line items to each promotion's declared dates; a line item with two different promotion IDs can be counted in both campaigns.",
        ),
    },
    "nationwide_logistics": {
        "label": "Nationwide logistics",
        "query_terms": (
            "logistics", "delivery", "shipping", "transit", "fulfillment", "fulfilment",
            "regional", "region", "carrier", "vận chuyển", "giao hàng", "logistics", "khu vực",
            "routing", "route", "destination", "proximity", "fulfillment location",
            "closest location", "shortest distance", "destination market",
            "minimize split fulfillment", "inventory availability", "split shipment", "phân tuyến", "điểm đến",
            "lead time", "fulfillment center", "supplier",
            "facility", "delivery lead time", "shipment schedule", "capacity by day",
            "inventory feed", "dispatch readiness", "order acknowledgment",
            "network design", "network optimization", "transportation cost", "service requirements",
            "service level", "delivery window", "mode selection", "carrier score-carding",
            "shipment consolidation", "cost and service", "speed and cost", "what-if scenario",
            "business priorities", "customer needs", "fast shipping", "need for speed",
            "shipping modes", "route optimization", "geographic gaps", "long-distance shipping costs",
            "on-time delivery",
            "delivery provider selection", "parcel size and weight", "express delivery", "provider pickup",
            "shipping rates", "customer delivery expectations",
        ),
        "retrieval_query": (
            "smart order routing assign fulfillment location based on inventory availability "
            "ship from the closest location shortest distance stay within destination market "
            "minimize split fulfillment ranked locations destination proximity route split shipments delivery transit shipping cost "
            "lead time supplier fulfillment center facility capacity by day inventory feed "
            "carrier dispatch readiness order acknowledgment shipment schedule network design "
            "transportation optimization network cost service tradeoff route mode selection "
            "capacity delivery window consolidation what-if scenario speed shipping mode coverage "
            "customer expectations geographic gaps long-distance transportation costs network redesign "
            "business priorities customer needs fast shipping lowest price carrier option "
            "delivery provider selection delivery time express delivery parcel size weight provider pickup "
            "shipping rates customer delivery expectations "
            "transportation between locations choose logistics solutions balance speed and cost"
        ),
        "dashboard_keys": ("logistics_by_year_region",),
        "source_tables": ("commerce.shipments", "commerce.orders", "commerce.geography"),
        "limitations": (
            "The data has no carrier, warehouse origin, route capacity, promised SLA, service type, "
            "or controllable transport-cost breakdown.",
            "Observed ship-to-delivery time does not identify the cause of delay or prove that a network change would help.",
        ),
    },
}

# Query scope is data-schema metadata, not a list of benchmark questions. Keep
# identifiers needed for joins available to SQL generation, but exclude direct
# customer attributes from the decision-support surface.
COMMERCE_QUERY_TABLES = {
    "inventory_allocation": {
        "inventory": ("snapshot_date", "product_id", "stock_on_hand", "units_received", "units_sold", "stockout_days", "fill_rate", "stockout_flag", "overstock_flag", "reorder_flag", "sell_through_rate", "product_name", "category", "segment", "year", "month"),
        "products": ("product_id", "product_name", "category", "segment", "size", "color", "price", "cogs"),
    },
    "promotion_planning": {
        "promotions": ("promo_id", "promo_name", "promo_type", "discount_value", "start_date", "end_date", "applicable_category", "promo_channel", "stackable_flag", "min_order_value"),
        "orders": ("order_id", "order_date", "order_status", "payment_method", "device_type", "order_source"),
        "order_items": ("order_item_id", "order_id", "product_id", "quantity", "unit_price", "discount_amount", "promo_id", "promo_id_2"),
        "products": ("product_id", "product_name", "category", "segment", "price", "cogs"),
    },
    "nationwide_logistics": {
        "shipments": ("order_id", "ship_date", "delivery_date", "shipping_fee"),
        "orders": ("order_id", "order_date", "order_status", "zip"),
        "geography": ("zip", "city", "region", "district"),
    },
}

# Explicitly missing business dimensions, kept beside the approved schema so
# fallback answers cannot substitute a coarser aggregate for a requested slice.
COMMERCE_UNAVAILABLE_DIMENSIONS = {
    "inventory_allocation": {
        "region": {"columns": ("region",), "aliases": ("region", "regional", "vùng", "khu vực")},
        "warehouse/location": {"columns": ("warehouse", "location", "fulfillment_center"), "aliases": ("warehouse", "warehouse location", "location", "fulfillment center", "kho hàng", "địa điểm", "trung tâm hoàn tất đơn")},
        "supplier": {"columns": ("supplier", "supplier_id", "vendor"), "aliases": ("supplier", "vendor", "nhà cung cấp")},
        "demand forecast": {"columns": ("demand_forecast", "forecast_demand"), "aliases": ("demand forecast", "forecast demand", "dự báo nhu cầu")},
        "supplier lead time": {"columns": ("supplier_lead_time",), "aliases": ("supplier lead time", "lead time nhà cung cấp", "thời gian cung ứng")},
    },
    "nationwide_logistics": {
        "carrier": {"columns": ("carrier", "carrier_id", "delivery_provider"), "aliases": ("carrier", "delivery provider", "shipping provider", "đơn vị vận chuyển", "nhà vận chuyển")},
        "warehouse/origin": {"columns": ("warehouse", "origin", "origin_warehouse"), "aliases": ("warehouse", "origin", "origin warehouse", "kho xuất phát", "kho hàng")},
        "route/lane": {"columns": ("route", "lane", "shipping_route"), "aliases": ("route", "lane", "shipping route", "tuyến giao hàng", "tuyến vận chuyển")},
        "capacity": {"columns": ("capacity", "route_capacity", "delivery_capacity"), "aliases": ("capacity", "route capacity", "delivery capacity", "năng lực giao hàng", "công suất")},
        "promised service level": {"columns": ("promised_sla", "service_level_agreement"), "aliases": ("promised sla", "service level agreement", "delivery sla", "cam kết giao hàng", "thời hạn cam kết")},
    },
}


def unavailable_commerce_dimensions(question: str, domain: str, available_columns: set[str]) -> list[str]:
    """Find explicitly requested schema dimensions that this domain cannot answer."""
    text = question.casefold()
    unavailable = []
    for dimension, definition in COMMERCE_UNAVAILABLE_DIMENSIONS.get(domain, {}).items():
        if any(alias in text for alias in definition["aliases"]) and not set(definition["columns"]).intersection(available_columns):
            unavailable.append(dimension)
    return unavailable


def resolve_commerce_decision_domain(question: str) -> str | None:
    text = " ".join(question.casefold().replace("_", " ").split())
    scores = {
        domain: sum(term in text for term in profile["query_terms"])
        for domain, profile in COMMERCE_DECISION_PROFILES.items()
    }
    best = max(scores.values(), default=0)
    winners = [domain for domain, score in scores.items() if score == best and score]
    return winners[0] if len(winners) == 1 else None
