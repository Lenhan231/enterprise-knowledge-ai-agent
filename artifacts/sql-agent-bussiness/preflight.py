"""Fail-closed non-production database preflight for the SQL business benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
DATABASE_ENV = "SQL_BENCHMARK_DATABASE_URL"
CLASSIFICATION_ENV = "SQL_BENCHMARK_DB_CLASSIFICATION"
FROZEN_ACK_ENV = "SQL_BENCHMARK_FROZEN_SNAPSHOT_ACK"
FROZEN_CLASSIFICATION = "frozen-analytics-snapshot"
FROZEN_ACK_VALUE = "I_CONFIRM_ANALYTICS_SNAPSHOT_IS_FROZEN"
PILOT_CASES = ROOT / "artifacts/sql-agent-bussiness/cases.json"


class PreflightBlocked(RuntimeError):
    pass


def validate_database_environment(environ=None):
    environ = os.environ if environ is None else environ
    url = environ.get(DATABASE_ENV, "").strip()
    if not url:
        raise PreflightBlocked(
            f"{DATABASE_ENV} is not configured; the benchmark will not reuse ANALYTICS_DATABASE_URL."
        )
    classification = environ.get(CLASSIFICATION_ENV, "").strip().casefold()
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise PreflightBlocked(f"{DATABASE_ENV} must be a PostgreSQL URL.")
    analytics_url = environ.get("ANALYTICS_DATABASE_URL", "").strip()
    if classification == "non-production":
        if analytics_url and url == analytics_url:
            raise PreflightBlocked("The benchmark URL matches ANALYTICS_DATABASE_URL; refusing possible production access.")
    elif classification == FROZEN_CLASSIFICATION:
        if not analytics_url or url != analytics_url:
            raise PreflightBlocked(
                f"{FROZEN_CLASSIFICATION} requires SQL_BENCHMARK_DATABASE_URL to exactly match ANALYTICS_DATABASE_URL."
            )
        if environ.get(FROZEN_ACK_ENV, "").strip() != FROZEN_ACK_VALUE:
            raise PreflightBlocked(
                f"Set {FROZEN_ACK_ENV}={FROZEN_ACK_VALUE} only after confirming the analytics snapshot is frozen."
            )
    else:
        raise PreflightBlocked(
            f"Set {CLASSIFICATION_ENV}=non-production for a dedicated test database, or "
            f"{CLASSIFICATION_ENV}={FROZEN_CLASSIFICATION} with the explicit freeze acknowledgement."
        )
    # A second explicit allow-list makes it harder to accidentally point the
    # benchmark at a shared/production host. Values contain hostnames only.
    allowed_hosts = {
        host.strip().casefold()
        for host in environ.get("SQL_BENCHMARK_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    }
    if not allowed_hosts or parsed.hostname.casefold() not in allowed_hosts:
        raise PreflightBlocked("The database host is not in SQL_BENCHMARK_ALLOWED_HOSTS.")
    return url


@asynccontextmanager
async def benchmark_repository():
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    database_url = validate_database_environment()
    previous_url = os.environ.get("ANALYTICS_DATABASE_URL")
    os.environ["ANALYTICS_DATABASE_URL"] = database_url
    try:
        from core.database.commerce_repository import create_repository_from_env

        repository = await create_repository_from_env()
        try:
            yield repository
        finally:
            await repository.close()
    finally:
        if previous_url is None:
            os.environ.pop("ANALYTICS_DATABASE_URL", None)
        else:
            os.environ["ANALYTICS_DATABASE_URL"] = previous_url


async def collect_preflight(repository):
    schema = await repository.get_schema()
    tables = schema.get("tables", {})
    required = {"commerce.sales", "commerce.orders", "commerce.order_items", "commerce.inventory"}
    missing = sorted(required - set(tables))
    if missing:
        raise PreflightBlocked("Required benchmark tables are unavailable: " + ", ".join(missing))

    case_set = json.loads(PILOT_CASES.read_text(encoding="utf-8"))
    expected_types = {}
    for case in case_set.get("cases", ()):
        for item in (case.get("semantic", {}).get("filters", {}).values()):
            if not isinstance(item, dict) or not item.get("column_type"):
                continue
            field = f"{item.get('source')}.{item.get('column')}"
            expected = str(item["column_type"]).casefold()
            if field in expected_types and expected_types[field] != expected:
                raise PreflightBlocked(f"Frozen cases declare conflicting column types for {field}.")
            expected_types[field] = expected
    live_types = schema.get("column_types", {})
    verified_types = {}
    for field, expected in expected_types.items():
        source, column = field.rsplit(".", 1)
        actual = live_types.get(source, {}).get(column)
        if not isinstance(actual, str):
            raise PreflightBlocked(f"Could not verify live database type for {field}.")
        if actual.casefold() != expected:
            raise PreflightBlocked(
                f"Frozen case requires {field} to be {expected}; live schema reports {actual}. "
                "Create a new case/reference version before benchmarking this schema."
            )
        verified_types[field] = actual.casefold()

    sales = await repository.execute_approved_query(
        "SELECT COUNT(*) AS rows, MIN(s.date) AS date_min, MAX(s.date) AS date_max "
        "FROM commerce.sales AS s LIMIT 1"
    )
    sales_2025 = await repository.execute_approved_query(
        "SELECT COUNT(*) AS rows, SUM(s.revenue) AS revenue "
        "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 LIMIT 1",
        date(2025, 1, 1), date(2026, 1, 1),
    )
    orders = await repository.execute_approved_query(
        "SELECT COUNT(*) AS rows, MIN(o.order_date) AS date_min, MAX(o.order_date) AS date_max "
        "FROM commerce.orders AS o LIMIT 1"
    )
    delivered_2025 = await repository.execute_approved_query(
        "SELECT COUNT(DISTINCT o.order_id) AS delivered_orders "
        "FROM commerce.orders AS o WHERE o.order_status = $1 AND o.order_date >= $2 AND o.order_date < $3 LIMIT 1",
        "delivered", date(2025, 1, 1), date(2026, 1, 1),
    )
    inventory = await repository.execute_approved_query(
        "SELECT COUNT(*) AS rows, MIN(i.snapshot_date) AS snapshot_min, "
        "MAX(i.snapshot_date) AS snapshot_max, COUNT(DISTINCT i.snapshot_date) AS snapshot_count "
        "FROM commerce.inventory AS i LIMIT 1"
    )
    inventory_snapshot = await repository.execute_approved_query(
        "SELECT COUNT(*) AS rows FROM commerce.inventory AS i "
        "WHERE i.snapshot_date = $1 LIMIT 1", date(2026, 11, 13),
    )
    coverage = {
        "commerce.sales": {**sales[0], "rows_2025": sales_2025[0]["rows"],
                            "revenue_2025": sales_2025[0]["revenue"]},
        "commerce.orders": {**orders[0], "delivered_orders_2025": delivered_2025[0]["delivered_orders"]},
        "commerce.inventory": {**inventory[0], "rows_at_2026_11_13": inventory_snapshot[0]["rows"]},
    }
    for field, actual in verified_types.items():
        source, column = field.rsplit(".", 1)
        coverage.setdefault(source, {})[f"{column}_type"] = actual
    unsupported = {
        "inventory_has_warehouse": "warehouse" in tables.get("commerce.inventory", ()),
        "supplier_tables": sorted(name for name in tables if "supplier" in name.casefold()),
        "lead_time_columns": sorted(
            f"{table}.{column}" for table, columns in tables.items()
            for column in columns if "lead_time" in column.casefold()
        ),
    }
    date_columns = sorted(f"{table}.{column}" for table, column in schema.get("date_columns", ()))
    data_fingerprint = hashlib.sha256(json.dumps(
        {"coverage": coverage, "unsupported_dimensions": unsupported, "date_columns": date_columns,
         "verified_column_types": verified_types},
        sort_keys=True, default=str, separators=(",", ":"),
    ).encode()).hexdigest()
    return {
        "database_classification": os.environ.get(CLASSIFICATION_ENV, "").strip().casefold(),
        "database_role_read_only": True,
        "coverage": coverage,
        "verified_column_types": verified_types,
        "unsupported_dimensions": unsupported,
        "date_columns": date_columns,
        "fingerprint_sha256": data_fingerprint,
    }


async def _main(output):
    async with benchmark_repository() as repository:
        result = await collect_preflight(repository)
    serialized = json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n"
    if output:
        Path(output).write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    import asyncio
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    arguments = parser.parse_args()
    try:
        asyncio.run(_main(arguments.output))
    except PreflightBlocked as error:
        print(f"NOT RUN: {error}", file=sys.stderr)
        raise SystemExit(2) from error
