"""Read the live PostgreSQL schema for a narrowly configured SQL scope."""

from __future__ import annotations

import re


def configured_schemas(value: str | None) -> tuple[str, ...]:
    schemas = tuple(dict.fromkeys(item.strip() for item in (value or "commerce").split(",") if item.strip()))
    if not schemas or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item) for item in schemas):
        raise ValueError("ANALYTICS_SCHEMAS must be a comma-separated list of schema names")
    if set(schemas) & {"pg_catalog", "information_schema"}:
        raise ValueError("System schemas cannot be enabled for analytics")
    return schemas


async def discover_schema(pool, schemas: tuple[str, ...]) -> dict:
    """Return readable tables, columns, keys, and declared foreign-key joins."""
    columns_sql = """
        SELECT table_schema, table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = ANY($1::text[])
        ORDER BY table_schema, table_name, ordinal_position
    """
    keys_sql = """
        SELECT tc.table_schema, tc.table_name, kcu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          USING (constraint_catalog, constraint_schema, constraint_name, table_schema, table_name)
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = ANY($1::text[])
        ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
    """
    foreign_keys_sql = """
        SELECT tc.table_schema, tc.table_name, kcu.column_name,
               ccu.table_schema AS foreign_schema, ccu.table_name AS foreign_table,
               ccu.column_name AS foreign_column
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          USING (constraint_catalog, constraint_schema, constraint_name, table_schema, table_name)
        JOIN information_schema.constraint_column_usage AS ccu
          USING (constraint_catalog, constraint_schema, constraint_name)
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = ANY($1::text[])
    """
    async with pool.acquire() as connection:
        async with connection.transaction(readonly=True):
            column_rows = await connection.fetch(columns_sql, list(schemas))
            key_rows = await connection.fetch(keys_sql, list(schemas))
            foreign_key_rows = await connection.fetch(foreign_keys_sql, list(schemas))
    tables: dict[str, set[str]] = {}
    date_columns = set()
    for row in column_rows:
        table = f"{row['table_schema']}.{row['table_name']}"
        tables.setdefault(table, set()).add(row['column_name'])
        if row['data_type'] in {"date", "timestamp without time zone", "timestamp with time zone"}:
            date_columns.add((table, row['column_name']))
    primary_keys: dict[str, set[str]] = {}
    for row in key_rows:
        table = f"{row['table_schema']}.{row['table_name']}"
        primary_keys.setdefault(table, set()).add(row['column_name'])
    joins = set()
    for row in foreign_key_rows:
        left = (f"{row['table_schema']}.{row['table_name']}", row['column_name'])
        right = (f"{row['foreign_schema']}.{row['foreign_table']}", row['foreign_column'])
        joins.add(frozenset((left, right)))
    return {
        "tables": {table: frozenset(names) for table, names in tables.items()},
        "primary_keys": {table: frozenset(names) for table, names in primary_keys.items()},
        "joins": frozenset(joins),
        "date_columns": frozenset(date_columns),
    }
