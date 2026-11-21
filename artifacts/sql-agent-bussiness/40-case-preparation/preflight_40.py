"""Read-only database and schema preflight for the 40-case draft cohort.

This script uses the existing benchmark repository and its least-privilege
role check. It does not import or invoke the SQL Agent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from core.agents.sql.join_validation import PRIMARY_KEYS
from core.agents.sql.sql_validation import APPROVED_COLUMNS, APPROVED_JOINS
from preflight import benchmark_repository, collect_preflight, validate_database_environment


HERE = Path(__file__).resolve().parent
LATEST_SNAPSHOT = date(2026, 11, 13)
NULL_CASE_SNAPSHOT = date(2025, 10, 31)
RETURN_RANGE = (date(2024, 1, 1), date(2025, 1, 1))


def _json(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


async def collect_draft_preflight(repository):
    summary = await collect_preflight(repository)
    schema = await repository.get_schema()  # refreshes schema and re-verifies the read-only role
    tables = schema.get("tables", {})
    missing = sorted(set(APPROVED_COLUMNS) - set(tables))
    if missing:
        raise RuntimeError("Approved Commerce tables absent from live schema: " + ", ".join(missing))

    snapshots = await repository.execute_approved_query(
        "SELECT i.snapshot_date, COUNT(*) AS row_count, COUNT(DISTINCT i.product_id) AS product_count, "
        "COUNT(i.days_of_supply) AS nonnull_days_of_supply, "
        "COUNT(*) FILTER (WHERE i.days_of_supply IS NULL) AS null_days_of_supply, "
        "COUNT(*) FILTER (WHERE i.stock_on_hand IS NULL) AS null_stock_on_hand, "
        "COUNT(*) FILTER (WHERE i.fill_rate IS NULL) AS null_fill_rate, "
        "COUNT(*) FILTER (WHERE i.sell_through_rate IS NULL) AS null_sell_through_rate "
        "FROM commerce.inventory AS i GROUP BY i.snapshot_date ORDER BY i.snapshot_date ASC LIMIT 100"
    )
    duplicate_keys = await repository.execute_approved_query(
        "SELECT i.snapshot_date, i.product_id, COUNT(*) AS duplicate_rows "
        "FROM commerce.inventory AS i GROUP BY i.snapshot_date, i.product_id "
        "HAVING COUNT(*) > 1 ORDER BY i.snapshot_date ASC, i.product_id ASC LIMIT 100"
    )
    catalog_ids = await repository.execute_approved_query(
        "SELECT p.product_id FROM commerce.products AS p ORDER BY p.product_id ASC LIMIT 200"
    )
    observed_ids = await repository.execute_approved_query(
        "SELECT i.product_id FROM commerce.inventory AS i WHERE i.snapshot_date = $1 "
        "ORDER BY i.product_id ASC LIMIT 200", LATEST_SNAPSHOT,
    )
    latest_categories = await repository.execute_approved_query(
        "SELECT i.category, COUNT(*) AS row_count FROM commerce.inventory AS i "
        "WHERE i.snapshot_date = $1 GROUP BY i.category ORDER BY i.category ASC LIMIT 100",
        LATEST_SNAPSHOT,
    )
    null_snapshot = await repository.execute_approved_query(
        "SELECT i.category, COUNT(i.days_of_supply) AS nonnull_count, "
        "COUNT(*) FILTER (WHERE i.days_of_supply IS NULL) AS null_count, "
        "AVG(i.days_of_supply) AS average_days_of_supply "
        "FROM commerce.inventory AS i WHERE i.snapshot_date = $1 "
        "GROUP BY i.category ORDER BY i.category ASC LIMIT 100", NULL_CASE_SNAPSHOT,
    )
    null_snapshot_categories = await repository.execute_approved_query(
        "SELECT i.category, COUNT(*) AS row_count FROM commerce.inventory AS i "
        "WHERE i.snapshot_date = $1 GROUP BY i.category ORDER BY i.category ASC LIMIT 100",
        NULL_CASE_SNAPSHOT,
    )
    stockout_by_category = await repository.execute_approved_query(
        "SELECT i.category, COUNT(*) FILTER (WHERE i.stockout_flag IS TRUE) AS stockout_product_count, "
        "COUNT(DISTINCT i.product_id) AS observed_product_count FROM commerce.inventory AS i "
        "WHERE i.snapshot_date = $1 GROUP BY i.category "
        "ORDER BY stockout_product_count DESC, i.category ASC NULLS LAST LIMIT 100",
        LATEST_SNAPSHOT,
    )
    order_vocabulary = {}
    for column in ("order_status", "order_source", "device_type"):
        order_vocabulary[column] = await repository.execute_approved_query(
            f"SELECT o.{column}, COUNT(*) AS row_count FROM commerce.orders AS o "
            f"GROUP BY o.{column} ORDER BY o.{column} ASC NULLS LAST LIMIT 100"
        )
    order_filter_count = await repository.execute_approved_query(
        "SELECT COUNT(DISTINCT o.order_id) AS order_count FROM commerce.orders AS o "
        "WHERE o.order_date >= $1 AND o.order_date < $2 "
        "AND o.order_source = $3 AND o.device_type = $4 LIMIT 1",
        date(2025, 1, 1), date(2026, 1, 1), "paid_search", "mobile",
    )
    delivered_orders_without_items = await repository.execute_approved_query(
        "SELECT COUNT(*) AS order_count FROM commerce.orders AS o "
        "WHERE o.order_status = $1 AND NOT EXISTS ("
        "SELECT 1 FROM commerce.order_items AS oi WHERE oi.order_id = o.order_id) LIMIT 1",
        "delivered",
    )
    catalog_cogs = await repository.execute_approved_query(
        "SELECT COUNT(*) AS products, COUNT(p.cogs) AS products_with_cogs, "
        "COUNT(*) FILTER (WHERE p.cogs IS NULL) AS products_without_cogs "
        "FROM commerce.products AS p LIMIT 1"
    )
    return_reasons = await repository.execute_approved_query(
        "SELECT r.return_reason, COUNT(r.return_id) AS return_count, SUM(r.refund_amount) AS refund_amount "
        "FROM commerce.returns AS r WHERE r.return_date >= $1 AND r.return_date < $2 "
        "AND r.return_reason IS NOT NULL GROUP BY r.return_reason "
        "ORDER BY refund_amount DESC, r.return_reason ASC LIMIT 100", *RETURN_RANGE,
    )
    region_values = await repository.execute_approved_query(
        "SELECT g.region, COUNT(*) AS zip_count FROM commerce.geography AS g "
        "GROUP BY g.region ORDER BY g.region ASC LIMIT 100"
    )
    sales_profit_filter_checks = await repository.execute_approved_query(
        "SELECT COUNT(*) FILTER (WHERE s.cogs > s.revenue) AS cogs_gt_revenue_days, "
        "COUNT(*) FILTER (WHERE s.revenue > s.cogs) AS revenue_gt_cogs_days "
        "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 LIMIT 1",
        date(2024, 1, 1), date(2025, 1, 1),
    )
    inventory_units_sold_by_category = await repository.execute_approved_query(
        "SELECT i.category, SUM(i.units_sold) AS units_sold FROM commerce.inventory AS i "
        "WHERE i.snapshot_date = $1 GROUP BY i.category ORDER BY i.category ASC NULLS LAST LIMIT 100",
        NULL_CASE_SNAPSHOT,
    )
    inventory_units_received_by_segment = await repository.execute_approved_query(
        "SELECT i.segment, SUM(i.units_received) AS units_received FROM commerce.inventory AS i "
        "WHERE i.snapshot_date = $1 GROUP BY i.segment "
        "ORDER BY units_received DESC, i.segment ASC NULLS LAST LIMIT 100",
        LATEST_SNAPSHOT,
    )
    shipment_geography_coverage = await repository.execute_approved_query(
        "SELECT COUNT(*) AS shipment_rows, COUNT(*) FILTER (WHERE g.zip IS NULL) AS unmapped_zip_rows, "
        "COUNT(s.shipping_fee) AS shipping_fee_observations "
        "FROM commerce.shipments AS s JOIN commerce.orders AS o ON o.order_id = s.order_id "
        "LEFT JOIN commerce.geography AS g ON g.zip = o.zip "
        "WHERE s.ship_date >= $1 AND s.ship_date < $2 LIMIT 1",
        date(2025, 1, 1), date(2026, 1, 1),
    )
    return_geography_coverage = await repository.execute_approved_query(
        "SELECT COUNT(*) AS return_rows, COUNT(*) FILTER (WHERE g.zip IS NULL) AS unmapped_zip_rows "
        "FROM commerce.returns AS r JOIN commerce.orders AS o ON o.order_id = r.order_id "
        "LEFT JOIN commerce.geography AS g ON g.zip = o.zip "
        "WHERE r.return_date >= $1 AND r.return_date < $2 LIMIT 1",
        date(2025, 1, 1), date(2026, 1, 1),
    )
    product_categories = await repository.execute_approved_query(
        "SELECT p.category, COUNT(*) AS product_count FROM commerce.products AS p "
        "GROUP BY p.category ORDER BY p.category ASC NULLS LAST LIMIT 100"
    )

    catalog = {row["product_id"] for row in catalog_ids}
    observed = {row["product_id"] for row in observed_ids}
    schema_tables = {table: sorted(columns) for table, columns in sorted(tables.items())}
    live_keys = {table: sorted(keys) for table, keys in schema.get("primary_keys", {}).items()}
    live_joins = sorted(
        " = ".join(sorted(f"{table}.{column}" for table, column in edge))
        for edge in schema.get("joins", ())
    )
    approved_joins = sorted(
        " = ".join(sorted(f"{table}.{column}" for table, column in edge))
        for edge in APPROVED_JOINS
    )
    return {
        "format_version": "sql-40-case-preflight.v1",
        "status": "VERIFIED_READ_ONLY_PREFLIGHT",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "database_classification": summary["database_classification"],
        "database_role_read_only": True,
        "host_allowlist_verified": True,
        "database_url_matches_configured_analytics_url": True,
        "fingerprint_sha256": summary["fingerprint_sha256"],
        "coverage": summary["coverage"],
        "verified_column_types": summary["verified_column_types"],
        "unsupported_dimensions": summary["unsupported_dimensions"],
        "date_columns": sorted(f"{table}.{column}" for table, column in schema.get("date_columns", ())),
        "schema": {
            "tables": schema_tables,
            "column_types": schema.get("column_types", {}),
            "primary_keys": live_keys,
            "foreign_keys": list(schema.get("foreign_keys", ())),
            "joins": live_joins,
            "approved_primary_keys_contract": {table: sorted(keys) for table, keys in PRIMARY_KEYS.items()},
            "approved_joins_contract": approved_joins,
        },
        "targeted_checks": {
            "inventory_null_counts_by_snapshot": snapshots,
            "duplicate_snapshot_product_keys": duplicate_keys,
            "catalog_product_count": len(catalog),
            "observed_product_count_2026_11_13": len(observed),
            "catalog_products_missing_snapshot_2026_11_13": len(catalog - observed),
            "inventory_product_ids_not_in_catalog_2026_11_13": len(observed - catalog),
            "latest_snapshot_categories": latest_categories,
            "inventory_categories_2025_10_31": null_snapshot_categories,
            "null_days_of_supply_by_category_2025_10_31": null_snapshot,
            "stockout_flags_by_category_2026_11_13": stockout_by_category,
            "order_vocabulary": order_vocabulary,
            "paid_search_mobile_orders_2025": order_filter_count[0]["order_count"],
            "delivered_orders_without_order_items": delivered_orders_without_items[0]["order_count"],
            "catalog_cogs_completeness": catalog_cogs[0],
            "return_reasons_2024": return_reasons,
            "region_values": region_values,
            "sales_profit_filter_checks_2024": sales_profit_filter_checks[0],
            "inventory_units_sold_by_category_2025_10_31": inventory_units_sold_by_category,
            "inventory_units_received_by_segment_2026_11_13": inventory_units_received_by_segment,
            "shipment_geography_coverage_2025": shipment_geography_coverage[0],
            "return_geography_coverage_2025": return_geography_coverage[0],
            "product_categories": product_categories,
        },
        "limitations": [
            "information_schema exposes no declared PK/FK metadata in the inspected snapshot; joins and keys use the approved migration contract",
            "preflight confirms database and schema properties, not human approval of candidate semantics or gold SQL",
        ],
    }


async def _run(output_path: Path):
    if output_path.exists():
        raise SystemExit(f"Refusing to overwrite existing preflight artifact: {output_path}")
    validate_database_environment()
    async with benchmark_repository() as repository:
        result = await collect_draft_preflight(repository)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "fingerprint_sha256": result["fingerprint_sha256"],
        "tables": len(result["schema"]["tables"]),
        "snapshots": len(result["targeted_checks"]["inventory_null_counts_by_snapshot"]),
        "read_only_role": result["database_role_read_only"],
        "output": str(output_path),
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(HERE / "database_preflight_verified.json"))
    args = parser.parse_args()
    asyncio.run(_run(Path(args.output)))
