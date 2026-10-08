"""Load the competition's original training CSVs into commerce tables."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql


ROOT = Path(__file__).resolve().parents[2]
TABLES = {
    "geography": ("zip", "city", "region", "district"),
    "products": ("product_id", "product_name", "category", "segment", "size", "color", "price", "cogs"),
    "customers": ("customer_id", "zip", "city", "signup_date", "gender", "age_group", "acquisition_channel"),
    "promotions": ("promo_id", "promo_name", "promo_type", "discount_value", "start_date", "end_date", "applicable_category", "promo_channel", "stackable_flag", "min_order_value"),
    "orders": ("order_id", "order_date", "customer_id", "zip", "order_status", "payment_method", "device_type", "order_source"),
    "order_items": ("order_id", "product_id", "quantity", "unit_price", "discount_amount", "promo_id", "promo_id_2"),
    "payments": ("order_id", "payment_method", "payment_value", "installments"),
    "shipments": ("order_id", "ship_date", "delivery_date", "shipping_fee"),
    "returns": ("return_id", "order_id", "product_id", "return_date", "return_reason", "return_quantity", "refund_amount"),
    "reviews": ("review_id", "order_id", "product_id", "customer_id", "review_date", "rating", "review_title"),
    "inventory": ("snapshot_date", "product_id", "stock_on_hand", "units_received", "units_sold", "stockout_days", "days_of_supply", "fill_rate", "stockout_flag", "overstock_flag", "reorder_flag", "sell_through_rate", "product_name", "category", "segment", "year", "month"),
    "web_traffic": ("date", "sessions", "unique_visitors", "page_views", "bounce_rate", "avg_session_duration_sec", "traffic_source"),
    "sales": ("date", "revenue", "cogs"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path, help="Directory returned by kagglehub.competition_download")
    args = parser.parse_args()
    data_dir = args.data_dir.expanduser().resolve()

    missing = [f"{table}.csv" for table in TABLES if not (data_dir / f"{table}.csv").is_file()]
    if missing:
        parser.error("CSV files missing: " + ", ".join(missing))

    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required (value is not displayed)")

    # Refuse to append or replace an existing competition load implicitly.
    with psycopg.connect(database_url, connect_timeout=15) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('commerce.geography') IS NOT NULL")
            if not cursor.fetchone()[0]:
                parser.error("commerce tables do not exist; apply the datathon schema migration first")
            existing_counts = sql.SQL(" UNION ALL ").join(
                sql.SQL("SELECT count(*) FROM commerce.{}").format(sql.Identifier(table))
                for table in TABLES
            )
            cursor.execute(existing_counts)
            if any(count for (count,) in cursor.fetchall()):
                parser.error("commerce already contains competition rows; refusing to append or overwrite")

            counts: dict[str, int] = {}
            for table, columns in TABLES.items():
                copy_query = sql.SQL("COPY commerce.{} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)").format(
                    sql.Identifier(table),
                    sql.SQL(", ").join(map(sql.Identifier, columns)),
                )
                with (data_dir / f"{table}.csv").open("r", encoding="utf-8-sig", newline="") as source:
                    with cursor.copy(copy_query) as copy:
                        while block := source.read(1024 * 1024):
                            copy.write(block)
                cursor.execute(sql.SQL("SELECT count(*) FROM commerce.{}").format(sql.Identifier(table)))
                counts[table] = cursor.fetchone()[0]

            for view in (
                "dashboard_promotions_by_year",
                "dashboard_promotions_by_campaign",
                "dashboard_logistics_by_year_region",
            ):
                cursor.execute(sql.SQL("REFRESH MATERIALIZED VIEW commerce.{}").format(sql.Identifier(view)))

    for table, count in counts.items():
        print(f"{table}: {count:,} rows")
    print(f"Imported {sum(counts.values()):,} rows from {len(counts)} source CSVs.")
    print("sample_submission.csv was not imported.")


if __name__ == "__main__":
    main()
