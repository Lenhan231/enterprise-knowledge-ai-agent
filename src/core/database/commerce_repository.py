"""Read-only repository for the Supabase ``commerce`` schema.

The repository exposes only approved query templates. It intentionally does
not accept arbitrary SQL from users or agents.
"""

from __future__ import annotations

import os
from typing import Any

from core.analytics.text_to_sql import APPROVED_COLUMNS, validate_commerce_sql

try:
    import asyncpg
except ImportError:  # Keep imports usable before the optional DB dependency is installed.
    asyncpg = None  # type: ignore[assignment]


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


class CommerceRepository:
    """Execute bounded, validated read-only queries against approved commerce data."""

    def __init__(self, pool: Any, *, statement_timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        if statement_timeout_ms <= 0:
            raise ValueError("statement_timeout_ms must be positive")
        self.pool = pool
        self.statement_timeout_ms = statement_timeout_ms

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
