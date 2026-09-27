# src/core/database/documents_repository.py
import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from core.analytics.sql_safety import validate_analytics_sql

load_dotenv()


class DocumentRepository:
    def __init__(self) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is not set")

        self.conn = psycopg.connect(database_url, row_factory=dict_row)

    def list_documents(self) -> list[dict]:
        with self.conn.cursor() as cursor:
            cursor.execute("""SELECT document_id,
                                    domain, 
                                    title, 
                                    year_or_version,
                                    format,
                                    ingestion_format,
                                    official_url,
                                    verification,
                                    rag_value,
                                    document_type,
                                    fiscal_year,
                                    company,
                                    source_type,
                                    allowed_roles,
                                    access_scope
                                    FROM documents
                                    ORDER by document_id""")
            return cursor.fetchall()

    def upsert_document(self, document: dict) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO documents (
                    document_id, domain, title, year_or_version, format,
                    ingestion_format, official_url, verification, rag_value,
                    document_type, fiscal_year, company, source_type,
                    allowed_roles, access_scope, processing_status
                ) VALUES (
                    %(document_id)s, %(domain)s, %(title)s, %(year_or_version)s,
                    %(format)s, %(ingestion_format)s, %(official_url)s,
                    %(verification)s, %(rag_value)s, %(document_type)s,
                    %(fiscal_year)s, %(company)s, %(source_type)s,
                    %(allowed_roles)s, %(access_scope)s, %(processing_status)s
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    domain = EXCLUDED.domain,
                    title = EXCLUDED.title,
                    year_or_version = EXCLUDED.year_or_version,
                    format = EXCLUDED.format,
                    ingestion_format = EXCLUDED.ingestion_format,
                    official_url = EXCLUDED.official_url,
                    verification = EXCLUDED.verification,
                    rag_value = EXCLUDED.rag_value,
                    document_type = EXCLUDED.document_type,
                    fiscal_year = EXCLUDED.fiscal_year,
                    company = EXCLUDED.company,
                    source_type = EXCLUDED.source_type,
                    allowed_roles = EXCLUDED.allowed_roles,
                    access_scope = EXCLUDED.access_scope,
                    processing_status = EXCLUDED.processing_status
                """,
                document,
            )
            self.conn.commit()

    def register_upload(self, document: dict) -> None:
        """Register an uploaded original already stored in private object storage."""
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO documents (
                    document_id, domain, title, year_or_version, format,
                    ingestion_format, official_url, verification, rag_value,
                    document_type, fiscal_year, company, source_type,
                    allowed_roles, access_scope, storage_path, processing_status,
                    uploaded_by, uploaded_at
                ) VALUES (
                    %(document_id)s, %(domain)s, %(title)s, %(year_or_version)s,
                    %(format)s, %(ingestion_format)s, %(official_url)s,
                    %(verification)s, %(rag_value)s, %(document_type)s,
                    %(fiscal_year)s, %(company)s, %(source_type)s,
                    %(allowed_roles)s, %(access_scope)s, %(storage_path)s,
                    'uploaded', %(uploaded_by)s, now()
                )
                """,
                document,
            )
            self.conn.commit()

    def corpus_dashboard(
        self, role: str, username: str = "", include_analytics: bool = False,
        company: str | None = None,
    ) -> dict:
        """Aggregate visible documents and indexed chunks from persisted state."""
        role_filter = "(d.allowed_roles && %s::text[] OR %s = 'admin' OR (%s = 'document_uploader' AND d.uploaded_by = %s))"
        visible = ([role], role, role, username)
        company_filter = " AND d.company = %s::text" if company is not None else ""
        visible_filter = role_filter + company_filter
        visible_params = visible + ((company,) if company is not None else ())
        with self.conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT d.document_id, d.company, d.domain, d.title, d.document_type,
                       d.format, d.fiscal_year, d.official_url, d.allowed_roles,
                       d.access_scope, d.processing_status, count(c.id)::int AS chunks
                FROM documents d
                LEFT JOIN document_chunks c
                  ON c.metadata->>'document_id' = d.document_id
                 AND coalesce(d.processing_status, 'ready') = 'ready'
                WHERE d.source_type IN ('public_enterprise_document', 'user_upload')
                  AND {visible_filter}
                GROUP BY d.document_id
                ORDER BY d.company, d.fiscal_year NULLS LAST, d.title
                """,
                visible_params,
            )
            documents = cursor.fetchall()
            cursor.execute(
                f"""SELECT d.company, d.domain, d.fiscal_year,
                           count(DISTINCT d.document_id)::int AS documents,
                           count(c.id)::int AS chunks
                    FROM documents d LEFT JOIN document_chunks c
                      ON c.metadata->>'document_id' = d.document_id
                     AND coalesce(d.processing_status, 'ready') = 'ready'
                    WHERE d.source_type IN ('public_enterprise_document', 'user_upload')
                      AND {visible_filter}
                    GROUP BY d.company, d.domain, d.fiscal_year
                    ORDER BY d.company, d.domain, d.fiscal_year NULLS LAST""",
                visible_params,
            )
            domains = cursor.fetchall()
            cursor.execute(
                f"""SELECT d.document_id, d.company, d.fiscal_year, d.title, d.processing_status,
                           count(c.id)::int AS chunks,
                           round(avg(length(c.content)))::int AS avg_chunk_chars,
                           count(c.id) FILTER (WHERE coalesce(c.content, '') = '')::int AS empty_chunks
                    FROM documents d LEFT JOIN document_chunks c
                      ON c.metadata->>'document_id' = d.document_id
                     AND coalesce(d.processing_status, 'ready') = 'ready'
                    WHERE d.source_type IN ('public_enterprise_document', 'user_upload')
                      AND {visible_filter}
                    GROUP BY d.document_id ORDER BY d.title""",
                visible_params,
            )
            quality = cursor.fetchall()
            cursor.execute(
                f"""SELECT d.company, d.fiscal_year, d.processing_status, count(*)::int AS documents
                    FROM documents d
                    WHERE d.source_type IN ('public_enterprise_document', 'user_upload')
                      AND {visible_filter}
                    GROUP BY d.company, d.fiscal_year, d.processing_status
                    ORDER BY d.company, d.fiscal_year NULLS LAST, d.processing_status""",
                visible_params,
            )
            processing = cursor.fetchall()
            if include_analytics:
                cursor.execute(
                    f"""SELECT d.company, m.metric_name, m.metric_label, m.fiscal_year,
                              m.metric_value, m.unit, m.document_id, m.page_number,
                              m.source_url, d.allowed_roles
                       FROM extracted_financial_metrics m
                       JOIN documents d USING (document_id)
                       WHERE m.status = 'verified'
                         AND (d.allowed_roles @> %s::text[] OR %s = 'admin'){company_filter}
                       ORDER BY d.company, m.metric_name, m.fiscal_year""",
                    ([role], role) + ((company,) if company is not None else ()),
                )
                financial = cursor.fetchall()
                if role == "admin":
                    cursor.execute(
                        f"""SELECT c.id, c.document_id, d.company, d.title, c.metric_name, c.metric_label,
                                   c.candidate_values, c.normalized_value, c.unit,
                                   c.fiscal_year, c.page_number, c.source_quote, c.status,
                                   d.official_url, c.evidence_count,
                                   (SELECT max(ch.metadata->>'text_extraction_method')
                                    FROM document_chunks ch
                                    WHERE ch.metadata->>'document_id' = c.document_id
                                      AND ch.metadata->>'page_number' = c.page_number::text)
                                     AS text_extraction_method
                            FROM (
                                SELECT candidate.id, candidate.document_id,
                                       candidate.metric_name, candidate.metric_label,
                                       candidate.candidate_values, candidate.normalized_value,
                                       candidate.unit, candidate.page_number,
                                       candidate.source_quote, candidate.status,
                                       candidate.created_at,
                                       coalesce(candidate.fiscal_year,
                                           CASE WHEN d.fiscal_year ~ '^[0-9]{{4}}$'
                                                THEN d.fiscal_year::integer END) AS fiscal_year,
                                       row_number() OVER (
                                           PARTITION BY candidate.document_id, candidate.metric_name
                                           ORDER BY candidate.created_at DESC, candidate.id DESC
                                       ) AS review_rank,
                                       count(*) OVER (
                                           PARTITION BY candidate.document_id, candidate.metric_name
                                       )::int AS evidence_count
                                FROM extracted_metric_candidates candidate
                                JOIN documents d USING (document_id)
                                WHERE candidate.status = 'needs_review'
                                  AND d.processing_status = 'ready' AND {visible_filter}
                                  AND NOT EXISTS (
                                      SELECT 1 FROM extracted_financial_metrics verified
                                      WHERE verified.document_id = candidate.document_id
                                        AND verified.metric_name = candidate.metric_name
                                        AND verified.status = 'verified'
                                  )
                            ) c
                            JOIN documents d USING (document_id)
                            WHERE c.review_rank = 1
                            ORDER BY d.company, c.fiscal_year NULLS LAST, d.title, c.page_number""",
                        visible_params,
                    )
                    candidates = cursor.fetchall()
                else:
                    candidates = []
            else:
                financial, candidates = [], []
        return {
            "documents": documents,
            "domains": domains,
            "quality": quality,
            "processing": processing,
            "financial": financial,
            "candidates": candidates,
            "document_count": len(documents),
            "chunk_count": sum(row["chunks"] for row in documents),
        }

    def execute_authorized_analytics(
        self, query: str, role: str, username: str, company: str | None = None
    ) -> dict:
        """Run validated SELECT SQL inside role-filtered CTEs and a read-only transaction."""
        query = validate_analytics_sql(query)
        metric_cte = """authorized_financial_metrics AS (
            SELECT company, fiscal_year, metric_name, metric_label, metric_value, unit,
                   document_id, page_number, source_url, source_quote
            FROM public.extracted_financial_metrics
            WHERE status = 'verified'
              AND (allowed_roles @> %s::text[] OR %s = 'admin')
              AND (%s::text IS NULL OR company = %s)
        )"""
        document_cte = """authorized_documents AS (
            SELECT d.document_id, d.company, d.domain, d.title, d.document_type, d.format,
                   CASE WHEN d.fiscal_year ~ '^[0-9]{4}$' THEN d.fiscal_year::integer END AS fiscal_year,
                   d.processing_status, d.official_url
            FROM public.documents d
            WHERE source_type IN ('public_enterprise_document', 'user_upload')
              AND (allowed_roles && %s::text[] OR %s = 'admin'
                   OR (%s = 'document_uploader' AND uploaded_by = %s))
              AND (%s::text IS NULL OR company = %s)
        )"""
        document_ids: set[str] = set()
        evidence = []
        documents = []
        self.conn.rollback()
        with self.conn.transaction():
            with self.conn.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute(
                    f"WITH {metric_cte}, {document_cte} {query}",
                    ([role], role, company, company, [role], role, role, username, company, company),
                )
                columns = [item.name for item in cursor.description]
                results = [dict(row) if isinstance(row, dict) else dict(zip(columns, row))
                           for row in cursor.fetchall()]
                for row in results:
                    ids = row.get("evidence_document_ids")
                    if isinstance(ids, (list, tuple)):
                        document_ids.update(value for value in ids if isinstance(value, str))
                if len(document_ids) > 250:
                    raise ValueError("Analytics matched too many source documents; narrow the request")
                if document_ids:
                    ids = sorted(document_ids)
                    cursor.execute(
                        """SELECT company, fiscal_year, metric_name, metric_label, metric_value,
                                  unit, document_id, page_number, source_url, source_quote
                           FROM public.extracted_financial_metrics
                           WHERE status = 'verified' AND document_id = ANY(%s)
                             AND (allowed_roles @> %s::text[] OR %s = 'admin')
                           ORDER BY company, fiscal_year, metric_name
                           LIMIT 501""",
                        (ids, [role], role),
                    )
                    evidence = cursor.fetchall()
                    if len(evidence) > 500:
                        raise ValueError("Analytics returned too many metric sources; narrow the request")
                    cursor.execute(
                        """SELECT document_id, company, domain, title, official_url
                           FROM public.documents
                           WHERE document_id = ANY(%s)
                             AND source_type IN ('public_enterprise_document', 'user_upload')
                             AND (allowed_roles && %s::text[] OR %s = 'admin'
                                  OR (%s = 'document_uploader' AND uploaded_by = %s))
                           ORDER BY title""",
                        (ids, [role], role, role, username),
                    )
                    documents = cursor.fetchall()
        return {"results": results, "evidence": evidence, "documents": documents}

    def save_metric_candidates(self, document_id: str, candidates: list[dict]) -> None:
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO extracted_metric_candidates (
                       document_id, metric_name, metric_label, candidate_values,
                       fiscal_year, page_number, source_quote, source_quote_hash
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (document_id, metric_name, page_number, source_quote_hash)
                   DO UPDATE SET candidate_values = EXCLUDED.candidate_values,
                                 metric_label = EXCLUDED.metric_label,
                                 fiscal_year = EXCLUDED.fiscal_year,
                                 source_quote = EXCLUDED.source_quote,
                                 status = 'needs_review', normalized_value = NULL, unit = NULL,
                                 reviewed_by = NULL, reviewed_at = NULL, created_at = now()
                   WHERE extracted_metric_candidates.status IN ('needs_review', 'superseded')""",
                [(document_id, row["metric_name"], row["metric_label"],
                  psycopg.types.json.Jsonb(row["candidate_values"]), row["fiscal_year"],
                  row["page_number"], row["source_quote"], row["source_quote_hash"])
                 for row in candidates],
            )
            cursor.execute(
                """UPDATE extracted_metric_candidates AS old
                   SET status = 'superseded'
                   WHERE old.document_id = %s AND old.status = 'needs_review'
                     AND NOT EXISTS (
                         SELECT 1
                         FROM unnest(%s::text[], %s::text[]) AS incoming(metric_name, source_quote_hash)
                         WHERE incoming.metric_name = old.metric_name
                           AND incoming.source_quote_hash = old.source_quote_hash
                     )""",
                (document_id,
                 [row["metric_name"] for row in candidates],
                 [row["source_quote_hash"] for row in candidates]),
            )

    def review_metric_candidate(
        self, candidate_id: int, status: str, value: float | None,
        unit: str | None, reviewer: str, company: str | None = None,
    ) -> bool:
        if status not in {"verified", "rejected"} or (status == "verified" and (value is None or not unit)):
            raise ValueError("Verified metrics require a normalized value and unit")
        with self.conn.transaction(), self.conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """UPDATE extracted_metric_candidates AS candidate
                   SET status=%s, normalized_value=%s, unit=%s, reviewed_by=%s, reviewed_at=now()
                   FROM documents d
                   WHERE candidate.id=%s AND candidate.status='needs_review'
                     AND d.document_id=candidate.document_id AND d.processing_status='ready'
                     AND (%s::text IS NULL OR d.company=%s::text)
                   RETURNING candidate.*""",
                (status, value if status == "verified" else None,
                 unit if status == "verified" else None, reviewer, candidate_id,
                 company, company),
            )
            candidate = cursor.fetchone()
            if candidate is None:
                return False
            if status == "verified":
                cursor.execute(
                    """INSERT INTO extracted_financial_metrics (
                           company, fiscal_year, metric_name, metric_label, metric_value,
                           unit, document_id, page_number, source_quote, source_quote_hash,
                           source_url, allowed_roles, status
                       ) SELECT d.company, coalesce(c.fiscal_year,
                                CASE WHEN d.fiscal_year ~ '^[0-9]{4}$' THEN d.fiscal_year::integer END),
                                c.metric_name, c.metric_label, c.normalized_value, c.unit,
                                d.document_id, c.page_number, c.source_quote,
                                c.source_quote_hash, d.official_url, d.allowed_roles, 'verified'
                         FROM extracted_metric_candidates c JOIN documents d USING(document_id)
                         WHERE c.id=%s
                         ON CONFLICT (document_id, fiscal_year, metric_name) DO NOTHING""",
                    (candidate_id,),
                )
                if cursor.rowcount == 0:
                    raise ValueError("A verified value already exists for this document, year, and metric")
        return True

    def update_processing_status(self, document_id: str, status: str) -> None:
        if status not in {"uploaded", "processing", "ready", "failed"}:
            raise ValueError("Invalid processing status")
        with self.conn.cursor() as cursor:
            cursor.execute(
                "UPDATE documents SET processing_status = %s WHERE document_id = %s",
                (status, document_id),
            )
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()
