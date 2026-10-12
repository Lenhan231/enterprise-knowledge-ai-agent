"""Read-only repository for the Supabase ``commerce`` schema.

The repository exposes only approved query templates. It intentionally does
not accept arbitrary SQL from users or agents.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from core.analytics.text_to_sql import APPROVED_COLUMNS, validate_commerce_sql

try:
    import asyncpg
except ImportError:  # Keep imports usable before the optional DB dependency is installed.
    asyncpg = None  # type: ignore[assignment]


MAX_LIMIT = 1_000
MAX_RANGE_DAYS = 3_660
DEFAULT_TIMEOUT_MS = 5_000


ROLE_CHECK_SQL = """
SELECT
    current_user AS role_name,
    role.rolsuper,
    role.rolcreaterole,
    role.rolcreatedb,
    role.rolreplication,
    role.rolbypassrls,
    has_schema_privilege(current_user, 'commerce', 'USAGE') AS schema_usage,
    has_schema_privilege(current_user, 'commerce', 'CREATE') AS schema_create,
    bool_and(has_any_column_privilege(
        current_user,
        format('%I.%I', 'commerce', approved.table_name),
        'SELECT'
    )) AS can_select,
    bool_or(has_table_privilege(
        current_user,
        format('%I.%I', 'commerce', approved.table_name),
        'INSERT,UPDATE,DELETE,TRUNCATE'
    )) AS can_write
FROM pg_roles AS role
CROSS JOIN unnest($1::text[]) AS approved(table_name)
WHERE role.rolname = current_user
GROUP BY role.rolsuper, role.rolcreaterole, role.rolcreatedb,
         role.rolreplication, role.rolbypassrls
"""


REVENUE_COGS_BY_MONTH = """
SELECT
    date_trunc('month', date)::date AS month,
    SUM(revenue) AS revenue,
    SUM(cogs) AS cogs
FROM commerce.sales
WHERE date >= $1
  AND date < $2
GROUP BY 1
ORDER BY 1
LIMIT $3
"""


REVENUE_BY_REGION = """
SELECT
    COALESCE(g.region, 'Unknown') AS region,
    SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
FROM commerce.orders AS o
JOIN commerce.order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN commerce.geography AS g
    ON g.zip = o.zip
WHERE o.order_status = 'delivered'
  AND o.order_date >= $1
  AND o.order_date < $2
GROUP BY g.region
ORDER BY revenue DESC
LIMIT $3
"""


INVENTORY_BY_CATEGORY = """
SELECT
    COALESCE(category, 'Unknown') AS category,
    COUNT(*) AS products_observed,
    SUM(stock_on_hand) AS stock_on_hand,
    COUNT(*) FILTER (WHERE stockout_flag IS TRUE) AS stockout_products,
    COUNT(*) FILTER (WHERE reorder_flag IS TRUE) AS reorder_products,
    COUNT(*) FILTER (WHERE overstock_flag IS TRUE) AS overstock_products,
    AVG(days_of_supply) AS avg_days_of_supply,
    AVG(fill_rate) AS avg_fill_rate,
    AVG(sell_through_rate) AS avg_sell_through_rate
FROM commerce.inventory
WHERE snapshot_date = $1
GROUP BY category
ORDER BY category
LIMIT $2
"""


class CommerceRepository:
    """Execute the three approved read-only commerce operations."""

    def __init__(self, pool: Any, *, statement_timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        if statement_timeout_ms <= 0:
            raise ValueError("statement_timeout_ms must be positive")
        self.pool = pool
        self.statement_timeout_ms = statement_timeout_ms

    async def revenue_cogs_by_month(
        self,
        start_date: date,
        end_date: date,
        *,
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        self._validate_period(start_date, end_date)
        return await self._fetch(REVENUE_COGS_BY_MONTH, start_date, end_date, self._limit(limit))

    async def revenue_by_region(
        self,
        start_date: date,
        end_date: date,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        self._validate_period(start_date, end_date)
        return await self._fetch(REVENUE_BY_REGION, start_date, end_date, self._limit(limit))

    async def inventory_by_category(
        self,
        snapshot_date: date,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self._fetch(INVENTORY_BY_CATEGORY, snapshot_date, self._limit(limit))

    async def execute_approved_query(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Revalidate and execute one bounded allowlisted SELECT."""
        validated = validate_commerce_sql(query)
        return await self._fetch(validated.sql, *args)

    async def close(self) -> None:
        """Close the underlying asyncpg pool during application shutdown."""
        await self.pool.close()

    async def _fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            # readonly=True prevents INSERT/UPDATE/DELETE even if a future
            # caller accidentally reuses this connection for another query.
            async with connection.transaction(readonly=True):
                await connection.execute(
                    f"SET LOCAL statement_timeout = '{self.statement_timeout_ms}ms'"
                )
                rows = await connection.fetch(query, *args)
                return [dict(row) for row in rows]

    @staticmethod
    def _limit(value: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("limit must be a positive integer")
        return min(value, MAX_LIMIT)

    @staticmethod
    def _validate_period(start_date: date, end_date: date) -> None:
        if start_date >= end_date:
            raise ValueError("start_date must be earlier than end_date")
        if (end_date - start_date).days > MAX_RANGE_DAYS:
            raise ValueError(f"date range cannot exceed {MAX_RANGE_DAYS} days")


async def create_repository_from_env() -> CommerceRepository:
    """Create a repository using the dedicated least-privilege analytics URL."""
    if asyncpg is None:
        raise RuntimeError("Install asyncpg before connecting to Supabase PostgreSQL")

    database_url = os.getenv("ANALYTICS_DATABASE_URL")
    if not database_url:
        raise RuntimeError("Set ANALYTICS_DATABASE_URL to a least-privilege commerce reader")

    pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=1,
        max_size=5,
        command_timeout=DEFAULT_TIMEOUT_MS / 1_000,
    )
    try:
        await verify_analytics_role(pool)
    except Exception:
        await pool.close()
        raise
    return CommerceRepository(pool)


async def verify_analytics_role(pool: Any) -> None:
    """Fail closed unless the connection role can only read approved sources."""
    table_names = sorted(source.split(".", 1)[1] for source in APPROVED_COLUMNS)
    async with pool.acquire() as connection:
        info = await connection.fetchrow(ROLE_CHECK_SQL, table_names)
    if info is None:
        raise RuntimeError("Analytics database role could not be verified")
    values = dict(info)
    privileged = any(values.get(flag) for flag in (
        "rolsuper", "rolcreaterole", "rolcreatedb", "rolreplication", "rolbypassrls",
        "schema_create", "can_write",
    ))
    if privileged:
        raise RuntimeError("ANALYTICS_DATABASE_URL must use a least-privilege read-only role")
    if not values.get("schema_usage"):
        raise RuntimeError("Analytics role lacks USAGE on schema commerce")
    if not values.get("can_select"):
        raise RuntimeError("Analytics role lacks SELECT on one or more approved commerce tables")
