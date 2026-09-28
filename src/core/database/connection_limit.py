"""Bound app-created sessions to stay below the Supabase session-pool limit."""

from __future__ import annotations

import os
import threading

import psycopg
from dotenv import load_dotenv

load_dotenv()

_MAX_CONNECTIONS = int(os.getenv("DATABASE_MAX_CONNECTIONS_PER_PROCESS", "10"))
if not 1 <= _MAX_CONNECTIONS <= 12:
    raise ValueError("DATABASE_MAX_CONNECTIONS_PER_PROCESS must be between 1 and 12")

_slots = threading.BoundedSemaphore(_MAX_CONNECTIONS)
_leased: set[int] = set()
_leased_lock = threading.Lock()
_WAIT_SECONDS = 20


def connect_database(conninfo: str | None = None, **kwargs) -> psycopg.Connection:
    """Queue callers when the local DB session budget is in use."""
    if not _slots.acquire(timeout=_WAIT_SECONDS):
        raise psycopg.OperationalError("Timed out waiting for a database connection slot")
    try:
        connection = psycopg.connect(
            conninfo or os.environ["DATABASE_URL"], connect_timeout=10, **kwargs,
        )
    except BaseException:
        _slots.release()
        raise
    with _leased_lock:
        _leased.add(id(connection))
    return connection


def close_database_connection(connection: psycopg.Connection) -> None:
    """Close a leased connection and release its local session slot once."""
    with _leased_lock:
        leased = id(connection) in _leased
        _leased.discard(id(connection))
    try:
        connection.close()
    finally:
        if leased:
            _slots.release()
