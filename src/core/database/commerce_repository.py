"""Read-only repository for explicitly configured PostgreSQL schemas.

The repository discovers readable tables but validates every generated query
against the live schema and a read-only database role.
"""

from __future__ import annotations

import os
import asyncio
from typing import Any

from core.analytics.text_to_sql import INVENTORY_SOURCES, inventory_scope_enabled, validate_commerce_sql
from core.sql_agent.schema import configured_schemas, discover_schema

try:
    import asyncpg
except ImportError:  # Keep imports usable before the optional DB dependency is installed.
    asyncpg = None  # type: ignore[assignment]


DEFAULT_TIMEOUT_MS = 5_000


class LazyCommerceRepository:
    """Document-only requests must not depend on an analytics connection."""

    def __init__(self):
        self.repository = None
        self.lock = asyncio.Lock()

    async def execute_approved_query(self, query, *args):
        async with self.lock:
            if self.repository is None:
                self.repository = await create_repository_from_env()
        return await self.repository.execute_approved_query(query, *args)

    async def get_schema(self):
        async with self.lock:
            if self.repository is None:
                self.repository = await create_repository_from_env()
        return await self.repository.get_schema()

    async def close(self):
        if self.repository is not None:
            await self.repository.close()


ROLE_CHECK_SQL = """
SELECT
    current_user AS role_name,
    role.rolsuper,
    role.rolcreaterole,
    role.rolcreatedb,
    role.rolreplication,
    role.rolbypassrls,
    bool_and(has_schema_privilege(current_user, allowed.schema_name, 'USAGE')) AS schema_usage,
    bool_or(has_schema_privilege(current_user, allowed.schema_name, 'CREATE')) AS schema_create,
    bool_and(has_any_column_privilege(
        current_user,
        format('%I.%I', approved.table_schema, approved.table_name),
        'SELECT'
    )) AS can_select,
    bool_or(has_table_privilege(
        current_user,
        format('%I.%I', approved.table_schema, approved.table_name),
        'INSERT,UPDATE,DELETE,TRUNCATE'
    )) AS can_write
FROM pg_roles AS role
CROSS JOIN unnest($1::text[]) AS allowed(schema_name)
LEFT JOIN information_schema.tables AS approved
  ON approved.table_schema = allowed.schema_name
 AND approved.table_type IN ('BASE TABLE', 'VIEW', 'FOREIGN')
WHERE role.rolname = current_user
GROUP BY role.rolsuper, role.rolcreaterole, role.rolcreatedb,
         role.rolreplication, role.rolbypassrls
"""


class CommerceRepository:
    """Execute bounded, validated read-only queries against configured schemas."""

    def __init__(self, pool: Any, *, statement_timeout_ms: int = DEFAULT_TIMEOUT_MS, allowed_sources=None,
                 allowed_schemas=('commerce',), schema_metadata=None) -> None:
        if statement_timeout_ms <= 0:
            raise ValueError("statement_timeout_ms must be positive")
        self.pool = pool
        self.allowed_sources = frozenset(allowed_sources) if allowed_sources is not None else None
        self.allowed_schemas = tuple(allowed_schemas)
        self.schema_metadata = schema_metadata or {}
        self.statement_timeout_ms = statement_timeout_ms

    async def execute_approved_query(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Revalidate and execute one bounded allowlisted SELECT."""
        validated = validate_commerce_sql(query, allowed_sources=self.allowed_sources,
            schema_columns=self.schema_metadata.get('tables'), approved_joins=self.schema_metadata.get('joins'),
            primary_keys=self.schema_metadata.get('primary_keys'), date_columns=self.schema_metadata.get('date_columns'))
        return await self._fetch(validated.sql, *args)

    async def get_schema(self) -> dict:
        """Refresh the live table/column and declared relationship metadata."""
        schema = await discover_schema(self.pool, self.allowed_schemas)
        if not schema['tables']:
            raise RuntimeError('No readable tables found in ANALYTICS_SCHEMAS')
        sources = set(schema['tables'])
        if inventory_scope_enabled():
            sources &= INVENTORY_SOURCES
        await verify_analytics_role(self.pool, allowed_sources=sources, allowed_schemas=self.allowed_schemas)
        schema['tables'] = {name: columns for name, columns in schema['tables'].items() if name in sources}
        schema['primary_keys'] = {name: keys for name, keys in schema['primary_keys'].items() if name in sources}
        schema['joins'] = frozenset(join for join in schema['joins']
                                    if all(table in sources for table, _ in join))
        schema['date_columns'] = frozenset(item for item in schema['date_columns'] if item[0] in sources)
        self.allowed_sources = frozenset(sources)
        self.schema_metadata = schema
        return schema

    async def close(self) -> None:
        """Close the underlying asyncpg pool during application shutdown."""
        await self.pool.close()

    async def _fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        from core.agents.runtime import deadline, remaining
        timeout = remaining(self.statement_timeout_ms / 1000) if deadline.get() is not None else None
        acquire_options = {'timeout': timeout} if timeout is not None else {}
        async with self.pool.acquire(**acquire_options) as connection:
            # readonly=True prevents INSERT/UPDATE/DELETE even if a future
            # caller accidentally reuses this connection for another query.
            async with connection.transaction(readonly=True):
                milliseconds = self.statement_timeout_ms
                if timeout is not None:
                    milliseconds = max(1, int(remaining(milliseconds/1000)*1000))
                execute_options = {'timeout': remaining(milliseconds/1000)} if timeout is not None else {}
                await connection.execute(f"SET LOCAL statement_timeout = '{milliseconds}ms'", **execute_options)
                fetch_options = {'timeout': remaining(milliseconds/1000)} if timeout is not None else {}
                rows = await connection.fetch(query, *args, **fetch_options)
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
        schemas = configured_schemas(os.getenv('ANALYTICS_SCHEMAS'))
        schema = await discover_schema(pool, schemas)
        sources = set(schema['tables'])
        if not sources:
            raise RuntimeError('No readable tables found in ANALYTICS_SCHEMAS')
        if inventory_scope_enabled():
            sources &= INVENTORY_SOURCES
            schema['tables'] = {name: columns for name, columns in schema['tables'].items() if name in sources}
            schema['primary_keys'] = {name: keys for name, keys in schema['primary_keys'].items() if name in sources}
        await verify_analytics_role(pool, allowed_sources=sources, allowed_schemas=schemas)
    except Exception:
        await pool.close()
        raise
    return CommerceRepository(pool, allowed_sources=sources, allowed_schemas=schemas, schema_metadata=schema)


async def verify_analytics_role(pool: Any, *, allowed_sources=None, allowed_schemas=('commerce',)) -> None:
    """Fail closed unless the connection role is read-only in configured schemas."""
    async with pool.acquire() as connection:
        info = await connection.fetchrow(ROLE_CHECK_SQL, list(allowed_schemas))
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
        raise RuntimeError("Analytics role lacks USAGE on one or more configured schemas")
    if not values.get("can_select") or not allowed_sources:
        raise RuntimeError("Analytics role lacks SELECT on readable tables in the configured schemas")
