"""Persist privacy-minimized agent execution telemetry."""

import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from core.database.connection_limit import close_database_connection, connect_database

load_dotenv()


class AgentRunRepository:
    def __init__(self) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is not set")
        self.conn = connect_database(database_url, row_factory=dict_row)

    def record_event(
        self,
        *,
        actor_role: str,
        agent_name: str,
        retrieval_method: str,
        status: str,
        elapsed_ms: int,
        citation_count: int,
        error_type: str | None,
    ) -> None:
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO agent_run_events (
                       actor_role, agent_name, retrieval_method, status,
                       elapsed_ms, citation_count, error_type
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (actor_role, agent_name, retrieval_method, status,
                 elapsed_ms, citation_count, error_type),
            )

    def monitoring_snapshot(self) -> dict:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """SELECT count(*)::int AS total_runs,
                          count(*) FILTER (WHERE status = 'completed')::int AS completed_runs,
                          count(*) FILTER (WHERE status <> 'completed')::int AS failed_runs,
                          count(*) FILTER (WHERE status = 'rate_limited')::int AS rate_limited_runs,
                          round(100.0 * count(*) FILTER (WHERE status = 'completed')
                                / nullif(count(*), 0), 1)::float8 AS success_rate,
                          round(avg(elapsed_ms))::int AS average_elapsed_ms,
                          percentile_cont(0.95) WITHIN GROUP (ORDER BY elapsed_ms)::int AS p95_elapsed_ms,
                          count(*) FILTER (WHERE created_at >= now() - interval '1 hour')::int AS last_hour_runs
                   FROM agent_run_events
                   WHERE created_at >= now() - interval '24 hours'"""
            )
            summary = cursor.fetchone()
            cursor.execute(
                """SELECT agent_name, count(*)::int AS total_runs,
                          count(*) FILTER (WHERE status = 'completed')::int AS completed_runs,
                          round(avg(elapsed_ms))::int AS average_elapsed_ms
                   FROM agent_run_events
                   WHERE created_at >= now() - interval '24 hours'
                   GROUP BY agent_name ORDER BY total_runs DESC, agent_name"""
            )
            by_agent = cursor.fetchall()
            cursor.execute(
                """SELECT id, actor_role, agent_name, retrieval_method, status,
                          elapsed_ms, citation_count, error_type, created_at
                   FROM agent_run_events
                   WHERE created_at >= now() - interval '24 hours'
                   ORDER BY created_at DESC, id DESC LIMIT 100"""
            )
            recent_runs = cursor.fetchall()
        return {"summary": summary, "by_agent": by_agent, "recent_runs": recent_runs}

    def close(self) -> None:
        close_database_connection(self.conn)
