"""Thumbs up/down on answers; stores the rated question and answer for review (see the migration)."""

import os

from dotenv import load_dotenv
from psycopg.rows import dict_row

from core.database.connection_limit import close_database_connection, connect_database

load_dotenv()


class AnswerFeedbackRepository:
    def __init__(self) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is not set")
        self.conn = connect_database(database_url, row_factory=dict_row)

    def record(self, *, actor_role: str, agent_name: str, rating: str, question: str, answer: str,
               comment: str | None, claim_status: str | None) -> None:
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO answer_feedback
                       (actor_role, agent_name, rating, question, answer, comment, claim_status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (actor_role, agent_name, rating, question, answer, comment, claim_status),
            )

    def snapshot(self) -> dict:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """SELECT count(*) FILTER (WHERE rating = 'up')::int AS up,
                          count(*) FILTER (WHERE rating = 'down')::int AS down
                   FROM answer_feedback WHERE created_at >= now() - interval '30 days'"""
            )
            summary = cursor.fetchone()
            cursor.execute(
                """SELECT id, actor_role, agent_name, rating, question, answer, comment, claim_status, created_at
                   FROM answer_feedback ORDER BY created_at DESC, id DESC LIMIT 50"""
            )
            recent = cursor.fetchall()
        return {"summary": summary, "recent": recent}

    def close(self) -> None:
        close_database_connection(self.conn)
