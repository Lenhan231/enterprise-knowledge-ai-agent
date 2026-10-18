"""Bound app-created sessions to stay below the Supabase session-pool limit."""

from __future__ import annotations

import os
import threading
import atexit

import psycopg
from psycopg.rows import tuple_row
from psycopg_pool import ConnectionPool, PoolTimeout
from pgvector.psycopg import register_vector
from dotenv import load_dotenv

load_dotenv()

_MAX_CONNECTIONS = int(os.getenv("DATABASE_MAX_CONNECTIONS_PER_PROCESS", "10"))
if not 1 <= _MAX_CONNECTIONS <= 12:
    raise ValueError("DATABASE_MAX_CONNECTIONS_PER_PROCESS must be between 1 and 12")

_slots = threading.BoundedSemaphore(_MAX_CONNECTIONS)
_leased: dict[int, ConnectionPool] = {}
_leased_lock = threading.Lock()
_pools: dict[tuple, ConnectionPool] = {}
_pools_lock = threading.Lock()
_WAIT_SECONDS = 20


def _connection_pool(conninfo: str, connect_options: dict) -> ConnectionPool:
    key = (conninfo, tuple(sorted(connect_options.items())))
    with _pools_lock:
        pool = _pools.get(key)
        if pool is None:
            pool = ConnectionPool(
                conninfo,
                min_size=0,
                max_size=_MAX_CONNECTIONS,
                kwargs={"connect_timeout": 10, **connect_options},
                configure=register_vector,
                timeout=_WAIT_SECONDS,
                max_idle=240,
                open=True,
            )
            _pools[key] = pool
        return pool


def connect_database(conninfo: str | None = None, **kwargs) -> psycopg.Connection:
    """Borrow a reusable connection without exceeding the process session budget."""
    if not _slots.acquire(timeout=_WAIT_SECONDS):
        raise psycopg.OperationalError("Timed out waiting for a database connection slot")
    row_factory = kwargs.pop("row_factory", tuple_row)
    pool = None
    try:
        pool = _connection_pool(conninfo or os.environ["DATABASE_URL"], kwargs)
        connection = pool.getconn(timeout=_WAIT_SECONDS)
        connection.row_factory = row_factory
    except BaseException:
        if pool is not None and "connection" in locals():
            pool.putconn(connection)
        _slots.release()
        raise
    with _leased_lock:
        _leased[id(connection)] = pool
    return connection


def close_database_connection(connection: psycopg.Connection) -> None:
    """Return a borrowed connection to its pool and release the local lease once."""
    with _leased_lock:
        pool = _leased.pop(id(connection), None)
    if pool is not None:
        try:
            pool.putconn(connection)
        finally:
            _slots.release()


def close_database_pools() -> None:
    """Close process pools during interpreter shutdown."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.close()


atexit.register(close_database_pools)
