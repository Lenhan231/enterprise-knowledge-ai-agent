# src/core/database/documents_repository.py
import hashlib
import os
import re

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from core.database.connection_limit import close_database_connection, connect_database
from core.analytics.sql_safety import validate_analytics_sql
from core.analytics.metric_ontology import METRIC_ONTOLOGY
from core.analytics.business_metric_catalog import BUSINESS_REPORTING_PERIOD_SQL, BUSINESS_VALUE_QUALIFIER_SQL

load_dotenv()


class DocumentRepository:
    def __init__(self) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is not set")

        self.conn = connect_database(database_url, row_factory=dict_row)

    def list_documents(self) -> list[dict]:
        with self.conn.cursor() as cursor:
            cursor.execute("""SELECT document_id,
                                    domain, 
                                    title, 
                                    year_or_version,
                                    format,
                                    source_url,
                                    verification,
                                    document_type,
                                    fiscal_year,
                                    company,
                                    source_type,
                                    allowed_roles
                                    FROM documents
                                    ORDER by document_id""")
            return cursor.fetchall()

    def upsert_document(self, document: dict) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO documents (
                    document_id, domain, title, year_or_version, format,
                    source_url, verification,
                    document_type, fiscal_year, company, source_type,
                    allowed_roles, processing_status
                ) VALUES (
                    %(document_id)s, %(domain)s, %(title)s, %(year_or_version)s,
                    %(format)s, %(source_url)s,
                    %(verification)s, %(document_type)s,
                    %(fiscal_year)s, %(company)s, %(source_type)s,
                    %(allowed_roles)s, %(processing_status)s
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    domain = EXCLUDED.domain,
                    title = EXCLUDED.title,
                    year_or_version = EXCLUDED.year_or_version,
                    format = EXCLUDED.format,
                    source_url = EXCLUDED.source_url,
                    verification = EXCLUDED.verification,
                    document_type = EXCLUDED.document_type,
                    fiscal_year = EXCLUDED.fiscal_year,
                    company = EXCLUDED.company,
                    source_type = EXCLUDED.source_type,
                    allowed_roles = EXCLUDED.allowed_roles,
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
                    source_url, verification,
                    document_type, fiscal_year, company, source_type,
                    allowed_roles, storage_path, processing_status,
                    uploaded_by, uploaded_at
                ) VALUES (
                    %(document_id)s, %(domain)s, %(title)s, %(year_or_version)s,
                    %(format)s, %(source_url)s,
                    %(verification)s, %(document_type)s,
                    %(fiscal_year)s, %(company)s, %(source_type)s,
                    %(allowed_roles)s, %(storage_path)s,
                    'uploaded', %(uploaded_by)s, now()
                )
                """,
                document,
            )
            self.conn.commit()

    def uploaded_pdf_for_metric_extraction(self, document_id: str, company: str) -> dict | None:
        """Only allow replay against ready uploaded PDFs in the active company."""
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute(
                """SELECT document_id, company, title, domain, document_type,
                          fiscal_year, source_url, allowed_roles, processing_status
                   FROM public.documents
                   WHERE document_id = %s AND company = %s
                     AND source_type = 'user_upload' AND format = 'PDF'
                     AND processing_status = 'ready'""",
                (document_id, company),
            )
            return cursor.fetchone()

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
                       d.format, d.fiscal_year, d.source_url, d.allowed_roles,
                       d.processing_status, count(c.id)::int AS chunks
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
                    f"""SELECT m.company, m.metric_name, m.metric_label, m.fiscal_year,
                              m.metric_value, m.unit, m.document_id, m.page_number,
                              m.source_url, m.entry_method, m.source_reference, m.source_note,
                              m.source_chunk_id, m.source_chunk_index, m.source_content_hash,
                              m.allowed_roles
                       FROM extracted_financial_metrics m
                       WHERE m.status = 'verified'
                         AND (m.allowed_roles @> %s::text[] OR %s = 'admin')
                         AND (%s::text IS NULL OR m.company = %s::text)
                       ORDER BY m.company, m.metric_name, m.fiscal_year""",
                    ([role], role, company, company),
                )
                financial = cursor.fetchall()
                cursor.execute(
                    f"""SELECT id, company, domain, metric_name, metric_label, fiscal_year,
                              metric_value, unit, scope, source_document_id, page_number,
                              source_quote, source_url, allowed_roles, verified_by,
                              source_chunk_id, source_chunk_index, source_content_hash,
                              extraction_method, extractor_version, extraction_config,
                              {BUSINESS_VALUE_QUALIFIER_SQL} AS value_qualifier,
                              {BUSINESS_REPORTING_PERIOD_SQL} AS reporting_period
                       FROM public.business_metric_evidence
                       WHERE status = 'verified'
                         AND (allowed_roles @> %s::text[] OR %s = 'admin')
                         AND (%s::text IS NULL OR company = %s::text)
                       ORDER BY company, domain, metric_name, fiscal_year""",
                    ([role], role, company, company),
                )
                business_metrics = cursor.fetchall()
                if role == "admin":
                    cursor.execute(
                        f"""SELECT id, company, domain, metric_name, metric_label, fiscal_year,
                              metric_value AS normalized_value, unit, scope, source_document_id,
                              source_document_id AS document_id, page_number, source_quote,
                              source_url, status, allowed_roles, entered_by AS entry_method,
                              extraction_method, extractor_version, extraction_config,
                              {BUSINESS_VALUE_QUALIFIER_SQL} AS value_qualifier,
                              {BUSINESS_REPORTING_PERIOD_SQL} AS reporting_period,
                              source_chunk_id, source_chunk_index, source_content_hash,
                              ARRAY[metric_value::text] AS candidate_values
                           FROM public.business_metric_evidence
                           WHERE status = 'needs_review'
                             AND (%s::text IS NULL OR company = %s::text)
                           ORDER BY fiscal_year, metric_name, source_document_id, page_number""",
                        (company, company),
                    )
                    business_candidates = cursor.fetchall()
                    cursor.execute(
                        f"""SELECT c.id, c.document_id, coalesce(c.company, d.company) AS company,
                                   coalesce(d.title, c.source_reference, 'Manual entry') AS title,
                                   c.metric_name, c.metric_label,
                                   c.candidate_values, c.normalized_value, c.unit,
                                   c.fiscal_year, c.page_number, c.source_quote, c.status,
                                   d.source_url, c.evidence_count, c.entry_method,
                                   c.source_reference, c.source_note, c.allowed_roles,
                                   c.extraction_method, c.extractor_model,
                                   c.prompt_version, c.selection_evidence,
                                   c.source_chunk_id, c.source_chunk_index, c.source_content_hash,
                                   (SELECT max(ch.metadata->>'text_extraction_method')
                                    FROM document_chunks ch
                                    WHERE ch.metadata->>'document_id' = c.document_id
                                      AND ch.metadata->>'page_number' = c.page_number::text)
                                     AS text_extraction_method
                            FROM (
                                SELECT candidate.id, candidate.document_id,
                                       candidate.company, candidate.allowed_roles,
                                       candidate.metric_name, candidate.metric_label,
                                       candidate.candidate_values, candidate.normalized_value,
                                       candidate.unit, candidate.page_number,
                                       candidate.source_quote, candidate.status,
                                       candidate.entry_method, candidate.source_reference,
                                       candidate.source_note,
                                       candidate.extraction_method, candidate.extractor_model,
                                       candidate.prompt_version, candidate.selection_evidence,
                                       candidate.source_chunk_id, candidate.source_chunk_index,
                                       candidate.source_content_hash,
                                       candidate.created_at,
                                       coalesce(candidate.fiscal_year,
                                           CASE WHEN d.fiscal_year ~ '^[0-9]{{4}}$'
                                                THEN d.fiscal_year::integer END) AS fiscal_year,
                                       row_number() OVER (
                                           PARTITION BY coalesce(candidate.document_id, 'manual-' || candidate.id::text), candidate.metric_name
                                           ORDER BY candidate.created_at DESC, candidate.id DESC
                                       ) AS review_rank,
                                       count(*) OVER (
                                           PARTITION BY coalesce(candidate.document_id, 'manual-' || candidate.id::text), candidate.metric_name
                                       )::int AS evidence_count
                                FROM extracted_metric_candidates candidate
                                LEFT JOIN documents d USING (document_id)
                                WHERE candidate.status = 'needs_review'
                                  AND (candidate.document_id IS NULL OR d.processing_status = 'ready')
                                  AND (%s::text IS NULL OR coalesce(candidate.company, d.company) = %s::text)
                                  AND (candidate.document_id IS NULL OR {visible_filter})
                                  AND NOT EXISTS (
                                      SELECT 1 FROM extracted_financial_metrics verified
                                      WHERE verified.company = coalesce(candidate.company, d.company)
                                        AND verified.metric_name = candidate.metric_name
                                        AND verified.fiscal_year = coalesce(candidate.fiscal_year,
                                            CASE WHEN d.fiscal_year ~ '^[0-9]{{4}}$'
                                                 THEN d.fiscal_year::integer END)
                                        AND verified.status = 'verified'
                                  )
                            ) c
                            LEFT JOIN documents d USING (document_id)
                            WHERE c.review_rank = 1
                            ORDER BY coalesce(c.company, d.company), c.fiscal_year NULLS LAST,
                                     coalesce(d.title, c.source_reference), c.page_number""",
                        (company, company) + visible_params,
                        )
                    candidates = cursor.fetchall()
                else:
                    candidates, business_candidates = [], []
            else:
                financial, candidates, business_metrics, business_candidates = [], [], [], []
        return {
            "documents": documents,
            "domains": domains,
            "quality": quality,
            "processing": processing,
            "financial": financial,
            "candidates": candidates,
            "business_metrics": business_metrics,
            "business_candidates": business_candidates,
            "document_count": len(documents),
            "chunk_count": sum(row["chunks"] for row in documents),
        }

    def execute_authorized_analytics(
        self, query: str, role: str, username: str, company: str | None = None
    ) -> dict:
        """Run validated SELECT SQL inside role-filtered CTEs and a read-only transaction."""
        query = validate_analytics_sql(query)
        metric_cte = """authorized_financial_metrics AS (
            SELECT id AS metric_id, company, fiscal_year, metric_name, metric_label, metric_value, unit,
                   document_id, page_number, source_url, source_quote, source_reference,
                   source_chunk_id, source_chunk_index, source_content_hash,
                   source_note, entry_method
            FROM public.extracted_financial_metrics
            WHERE status = 'verified'
              AND (allowed_roles @> %s::text[] OR %s = 'admin')
              AND (%s::text IS NULL OR company = %s)
        )"""
        business_metric_cte = f"""authorized_business_metrics AS (
            SELECT id AS business_metric_id, company, domain AS metric_domain, fiscal_year,
                   metric_name, metric_label, metric_value, unit, scope,
                   {BUSINESS_VALUE_QUALIFIER_SQL} AS value_qualifier,
                   {BUSINESS_REPORTING_PERIOD_SQL} AS reporting_period,
                   source_document_id AS document_id, page_number, source_url,
                   source_quote, source_chunk_id, source_chunk_index,
                   source_content_hash, extraction_method, extractor_version, extraction_config
            FROM public.business_metric_evidence
            WHERE status = 'verified'
              AND (allowed_roles @> %s::text[] OR %s = 'admin')
              AND (%s::text IS NULL OR company = %s)
        )"""
        document_cte = """authorized_documents AS (
            SELECT d.document_id, d.company, d.domain, d.title, d.document_type, d.format,
                   CASE WHEN d.fiscal_year ~ '^[0-9]{4}$' THEN d.fiscal_year::integer END AS fiscal_year,
                   d.processing_status, d.source_url
            FROM public.documents d
            WHERE source_type IN ('public_enterprise_document', 'user_upload')
              AND (allowed_roles && %s::text[] OR %s = 'admin'
                   OR (%s = 'document_uploader' AND uploaded_by = %s))
              AND (%s::text IS NULL OR company = %s)
        )"""
        metric_ids: set[int] = set()
        business_metric_ids: set[int] = set()
        document_ids: set[str] = set()
        evidence = []
        documents = []
        self.conn.rollback()
        with self.conn.transaction():
            with self.conn.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute(
                    f"WITH {metric_cte}, {business_metric_cte}, {document_cte} {query}",
                    ([role], role, company, company, [role], role, company, company,
                     [role], role, role, username, company, company),
                )
                columns = [item.name for item in cursor.description]
                results = [dict(row) if isinstance(row, dict) else dict(zip(columns, row))
                           for row in cursor.fetchall()]
                for row in results:
                    ids = row.get("evidence_metric_ids")
                    if isinstance(ids, (list, tuple)):
                        metric_ids.update(value for value in ids if isinstance(value, int))
                    ids = row.get("evidence_business_metric_ids")
                    if isinstance(ids, (list, tuple)):
                        business_metric_ids.update(value for value in ids if isinstance(value, int))
                    document_evidence_ids = row.get("evidence_document_ids")
                    if isinstance(document_evidence_ids, (list, tuple)):
                        document_ids.update(value for value in document_evidence_ids if isinstance(value, str))
                if len(metric_ids) > 500 or len(business_metric_ids) > 500 or len(document_ids) > 250:
                    raise ValueError("Analytics matched too many source documents; narrow the request")
                if metric_ids:
                    ids = sorted(metric_ids)
                    cursor.execute(
                        """SELECT id AS metric_id, company, fiscal_year, metric_name, metric_label,
                                  metric_value, unit, document_id, page_number, source_url, source_quote,
                                  source_reference, source_note, entry_method, source_chunk_id,
                                  source_chunk_index, source_content_hash
                           FROM public.extracted_financial_metrics
                           WHERE status='verified' AND id = ANY(%s)
                             AND (allowed_roles @> %s::text[] OR %s = 'admin')
                           ORDER BY company, fiscal_year, metric_name LIMIT 501""",
                        (ids, [role], role),
                    )
                    evidence = cursor.fetchall()
                    if len(evidence) > 500:
                        raise ValueError("Analytics returned too many metric sources; narrow the request")
                    source_document_ids = sorted({
                        row["document_id"] for row in evidence if row["document_id"]
                    })
                    if source_document_ids:
                        cursor.execute(
                            """SELECT document_id, company, domain, title, source_url
                               FROM public.documents WHERE document_id = ANY(%s)
                                 AND (allowed_roles && %s::text[] OR %s = 'admin'
                                      OR (%s = 'document_uploader' AND uploaded_by = %s))
                               ORDER BY title""",
                            (source_document_ids, [role], role, role, username),
                        )
                        documents = cursor.fetchall()
                if business_metric_ids:
                    cursor.execute(
                        f"""SELECT id AS business_metric_id, company, domain AS metric_domain,
                                  fiscal_year, metric_name, metric_label, metric_value, unit, scope,
                                  {BUSINESS_VALUE_QUALIFIER_SQL} AS value_qualifier,
                                  {BUSINESS_REPORTING_PERIOD_SQL} AS reporting_period,
                                  source_document_id AS document_id, page_number, source_url, source_quote,
                                  source_chunk_id, source_chunk_index, source_content_hash,
                                  extraction_method, extractor_version, extraction_config
                           FROM public.business_metric_evidence
                           WHERE status = 'verified' AND id = ANY(%s)
                             AND (allowed_roles @> %s::text[] OR %s = 'admin')
                             AND (%s::text IS NULL OR company = %s)
                           ORDER BY company, fiscal_year, domain, metric_name LIMIT 501""",
                        (sorted(business_metric_ids), [role], role, company, company),
                    )
                    business_evidence = cursor.fetchall()
                    if len(business_evidence) > 500:
                        raise ValueError("Analytics returned too many business metric sources; narrow the request")
                    source_document_ids = sorted({row["document_id"] for row in business_evidence if row["document_id"]})
                    if source_document_ids:
                        cursor.execute(
                            """SELECT document_id, company, domain, title, source_url
                               FROM public.documents WHERE document_id = ANY(%s)
                                 AND (allowed_roles && %s::text[] OR %s = 'admin'
                                      OR (%s = 'document_uploader' AND uploaded_by = %s))
                               ORDER BY title""",
                            (source_document_ids, [role], role, role, username),
                        )
                        documents.extend(cursor.fetchall())
                if document_ids:
                    ids = sorted(document_ids)
                    cursor.execute(
                        """SELECT document_id, company, domain, title, source_url
                           FROM public.documents
                           WHERE document_id = ANY(%s)
                             AND source_type IN ('public_enterprise_document', 'user_upload')
                             AND (allowed_roles && %s::text[] OR %s = 'admin'
                                  OR (%s = 'document_uploader' AND uploaded_by = %s))
                           ORDER BY title""",
                        (ids, [role], role, role, username),
                    )
                    documents.extend(cursor.fetchall())
        return {"results": results, "evidence": evidence,
                "business_evidence": locals().get("business_evidence", []), "documents": documents}

    def save_metric_candidates(self, document_id: str, candidates: list[dict]) -> None:
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, chunk_index, content, metadata->>'page_number' AS page_number
                   FROM public.document_chunks
                   WHERE metadata->>'document_id' = %s
                   ORDER BY chunk_index""",
                (document_id,),
            )
            source_chunks = cursor.fetchall()

            def link_source_chunk(row: dict) -> tuple[int | None, int | None, str | None]:
                quote = " ".join(str(row.get("source_quote") or "").casefold().split())
                page = str(row.get("page_number") or "")
                on_page = [chunk for chunk in source_chunks if chunk["page_number"] == page]
                page_chunks = on_page or source_chunks
                exact = [chunk for chunk in page_chunks
                         if quote and quote in " ".join(chunk["content"].casefold().split())]
                if len(exact) == 1:
                    match = exact[0]
                else:
                    definition = METRIC_ONTOLOGY.get(row["metric_name"], {})
                    labels = {str(row.get("metric_label") or ""), *definition.get("source_labels", ())}
                    labels.update(definition.get("aliases", ()))
                    labels = {" ".join(label.casefold().split()) for label in labels if label}
                    values = [re.sub(r"\D", "", str(value)) for value in row.get("candidate_values", ())]
                    values = [value for value in values if len(value) >= 2]
                    quote_tokens = set(re.findall(r"[a-z]+|\d+", quote))
                    matched = []
                    for chunk in page_chunks:
                        content = " ".join(chunk["content"].casefold().split())
                        digits = re.sub(r"\D", "", content)
                        if values and all(value in digits for value in values):
                            label_score = max((len(label) for label in labels if label in content), default=0)
                            if label_score:
                                content_tokens = set(re.findall(r"[a-z]+|\d+", content))
                                quote_score = len(quote_tokens & content_tokens)
                                matched.append((label_score, quote_score, chunk))
                    matched.sort(key=lambda item: (item[0], item[1]), reverse=True)
                    if not matched or (len(matched) > 1 and matched[0][:2] == matched[1][:2]):
                        return None, None, None
                    match = matched[0][2]
                return (match["id"], match["chunk_index"],
                        hashlib.sha256(match["content"].encode()).hexdigest())

            cursor.executemany(
                """INSERT INTO extracted_metric_candidates (
                       document_id, metric_name, metric_label, candidate_values,
                       fiscal_year, page_number, source_quote, source_quote_hash, unit,
                       extraction_method, extractor_model, prompt_version, selection_evidence,
                       source_chunk_id, source_chunk_index, source_content_hash
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (document_id, metric_name, page_number, source_quote_hash)
                   DO UPDATE SET candidate_values = EXCLUDED.candidate_values,
                                 metric_label = EXCLUDED.metric_label,
                                 fiscal_year = EXCLUDED.fiscal_year,
                                 source_quote = EXCLUDED.source_quote,
                                 unit = EXCLUDED.unit,
                                 extraction_method = EXCLUDED.extraction_method,
                                 extractor_model = EXCLUDED.extractor_model,
                                 prompt_version = EXCLUDED.prompt_version,
                                 selection_evidence = EXCLUDED.selection_evidence,
                                 source_chunk_id = EXCLUDED.source_chunk_id,
                                 source_chunk_index = EXCLUDED.source_chunk_index,
                                 source_content_hash = EXCLUDED.source_content_hash,
                                 status = 'needs_review', normalized_value = NULL,
                                 reviewed_by = NULL, reviewed_at = NULL, created_at = now()
                   WHERE extracted_metric_candidates.status IN ('needs_review', 'superseded')""",
                [(document_id, row["metric_name"], row["metric_label"],
                  psycopg.types.json.Jsonb(row["candidate_values"]), row["fiscal_year"],
                  row["page_number"], row["source_quote"], row["source_quote_hash"],
                  row.get("unit"),
                  row.get("extraction_method", "rule_based_page_evidence"),
                  row.get("extractor_model"), row.get("prompt_version"),
                  psycopg.types.json.Jsonb(row.get("selection_evidence", {})),
                  *link_source_chunk(row))
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

    def create_manual_metric_candidate(
        self, *, company: str, metric_name: str, metric_label: str,
        metric_value: str, fiscal_year: int, unit: str,
        source_reference: str | None, source_note: str, allowed_roles: list[str],
    ) -> int:
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.extracted_metric_candidates (
                       company, metric_name, metric_label, candidate_values,
                       fiscal_year, unit, status, extraction_method, entry_method,
                       source_reference, source_note, allowed_roles, selection_evidence
                   ) VALUES (%s, %s, %s, %s, %s, %s, 'needs_review', 'manual_entry',
                             'manual', %s, %s, %s, %s)
                   RETURNING id""",
                (company, metric_name, metric_label,
                 psycopg.types.json.Jsonb([metric_value]), fiscal_year, unit,
                 source_reference, source_note, allowed_roles,
                 psycopg.types.json.Jsonb({"entry_method": "manual"})),
            )
            return cursor.fetchone()[0]

    def create_business_metric_candidate(self, *, company: str, metric: dict, fiscal_year: int,
                                         metric_value: float, unit: str, scope: str,
                                         source_document_id: str, page_number: int,
                                         source_quote: str, source_url: str,
                                         allowed_roles: list[str], entered_by: str,
                                         extraction_method: str = "manual",
                                         extractor_version: str = "manual-v1",
                                         extraction_config: dict | None = None,
                                         source_chunk_index: int | None = None,
                                         source_content_hash: str | None = None) -> int:
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.business_metric_evidence (
                       company, domain, metric_name, metric_label, fiscal_year, metric_value,
                       unit, scope, source_document_id, page_number, source_quote, source_url,
                       allowed_roles, entered_by, extraction_method, extractor_version,
                       extraction_config, source_chunk_index, source_content_hash
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                             %s, %s, %s, %s, %s)
                   RETURNING id""",
                (company, metric["domain"], metric["name"], metric["label"], fiscal_year,
                 metric_value, unit, scope, source_document_id, page_number,
                 source_quote, source_url, allowed_roles, entered_by,
                 extraction_method, extractor_version,
                 psycopg.types.json.Jsonb(extraction_config or {}),
                 source_chunk_index, source_content_hash),
            )
            return cursor.fetchone()[0]

    def save_business_metric_candidates(self, candidates: list[dict], entered_by: str = "parser") -> int:
        """Persist parser observations as pending; updates never replace reviewed data."""
        if not candidates:
            return 0
        import hashlib
        def normalized(value: str) -> str:
            return " ".join(value.split()).casefold()

        with self.conn.transaction(), self.conn.cursor() as cursor:
            for row in candidates:
                chunk_index = row.get("source_chunk_index")
                chunk_id = None
                content_hash = row.get("source_content_hash")
                if row.get("extraction_method") in {"parser_rule", "llm_parser"}:
                    cursor.execute(
                        """SELECT id, chunk_index, content
                           FROM public.document_chunks
                           WHERE metadata->>'document_id' = %s
                             AND metadata->>'page_number' = %s
                           ORDER BY chunk_index""",
                        (row["source_document_id"], str(row["page_number"])),
                    )
                    source_chunk = next((chunk for chunk in cursor.fetchall()
                                         if normalized(row["source_quote"]) in normalized(chunk["content"])), None)
                    if source_chunk is None:
                        raise ValueError(
                            f"No saved parser chunk contains metric evidence for "
                            f"{row['source_document_id']} PDF page {row['page_number']}"
                        )
                    if isinstance(source_chunk, dict):
                        chunk_id = source_chunk["id"]
                        chunk_index = source_chunk["chunk_index"]
                        chunk_content = source_chunk["content"]
                    else:
                        chunk_id, chunk_index, chunk_content = source_chunk
                    content_hash = hashlib.sha256(chunk_content.encode()).hexdigest()
                    # A refreshed official source may correct an older, unlinked
                    # research candidate. Update only one unreviewed source_research
                    # row for this metric/year; reviewed evidence is never eligible.
                    cursor.execute(
                        """UPDATE public.business_metric_evidence AS target
                           SET domain = %s, metric_label = %s, metric_value = %s,
                               unit = %s, scope = %s, page_number = %s,
                               source_quote = %s, source_url = %s,
                               extraction_method = %s, extractor_version = %s,
                               extraction_config = %s, source_chunk_id = %s,
                               source_chunk_index = %s, source_content_hash = %s,
                               entered_by = 'parser'
                           WHERE target.id = (
                               SELECT min(candidate.id)
                               FROM public.business_metric_evidence AS candidate
                               WHERE candidate.company = %s
                                 AND candidate.metric_name = %s
                                 AND candidate.fiscal_year = %s
                                 AND candidate.source_document_id = %s
                                 AND candidate.status = 'needs_review'
                                 AND candidate.entered_by = 'source_research'
                                 AND candidate.source_chunk_id IS NULL
                                 AND NOT EXISTS (
                                     SELECT 1
                                     FROM public.business_metric_evidence AS collision
                                     WHERE collision.id <> candidate.id
                                       AND collision.company = candidate.company
                                       AND collision.metric_name = candidate.metric_name
                                       AND collision.fiscal_year = candidate.fiscal_year
                                       AND collision.source_document_id = candidate.source_document_id
                                       AND collision.page_number = %s
                                 )
                               HAVING count(*) = 1
                           )
                           RETURNING target.id""",
                        (row["domain"], row["metric_label"], row["metric_value"], row["unit"],
                         row["scope"], row["page_number"], row["source_quote"], row["source_url"],
                         row["extraction_method"], row["extractor_version"],
                         psycopg.types.json.Jsonb(row["extraction_config"]), chunk_id,
                         chunk_index, content_hash, row["company"], row["metric_name"],
                         row["fiscal_year"], row["source_document_id"], row["page_number"]),
                    )
                    if cursor.fetchone():
                        continue
                    cursor.execute(
                        """UPDATE public.business_metric_evidence AS target
                           SET page_number = %s, source_quote = %s, source_url = %s,
                               extraction_method = %s, extractor_version = %s,
                               extraction_config = %s, source_chunk_id = %s,
                               source_chunk_index = %s, source_content_hash = %s,
                               entered_by = 'parser'
                           WHERE target.id = (
                               SELECT min(candidate.id)
                               FROM public.business_metric_evidence AS candidate
                               WHERE candidate.company = %s
                                 AND candidate.metric_name = %s
                                 AND candidate.fiscal_year = %s
                                 AND candidate.source_document_id = %s
                                 AND candidate.status = 'needs_review'
                                 AND candidate.metric_value = %s
                                 AND candidate.unit = %s
                                 AND candidate.entered_by = 'source_research'
                                 AND NOT EXISTS (
                                     SELECT 1
                                     FROM public.business_metric_evidence AS collision
                                     WHERE collision.id <> candidate.id
                                       AND collision.company = candidate.company
                                       AND collision.metric_name = candidate.metric_name
                                       AND collision.fiscal_year = candidate.fiscal_year
                                       AND collision.source_document_id = candidate.source_document_id
                                       AND collision.page_number = %s
                                 )
                               HAVING count(*) = 1
                           )
                           RETURNING target.id""",
                        (row["page_number"], row["source_quote"], row["source_url"],
                         row["extraction_method"], row["extractor_version"],
                         psycopg.types.json.Jsonb(row["extraction_config"]), chunk_id,
                         chunk_index, content_hash, row["company"], row["metric_name"],
                         row["fiscal_year"], row["source_document_id"],
                         row["metric_value"], row["unit"], row["page_number"]),
                    )
                    if cursor.fetchone():
                        continue
                cursor.execute(
                    """INSERT INTO public.business_metric_evidence (
                           company, domain, metric_name, metric_label, fiscal_year, metric_value,
                           unit, scope, source_document_id, page_number, source_quote, source_url,
                           allowed_roles, entered_by, extraction_method, extractor_version,
                           extraction_config, source_chunk_id, source_chunk_index, source_content_hash
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                 %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (company, metric_name, fiscal_year, source_document_id, page_number)
                       DO UPDATE SET source_quote = EXCLUDED.source_quote,
                                     extraction_method = EXCLUDED.extraction_method,
                                     extractor_version = EXCLUDED.extractor_version,
                                     extraction_config = EXCLUDED.extraction_config,
                                     source_chunk_id = EXCLUDED.source_chunk_id,
                                     source_chunk_index = EXCLUDED.source_chunk_index,
                                     source_content_hash = EXCLUDED.source_content_hash
                       WHERE business_metric_evidence.status = 'needs_review'
                         AND business_metric_evidence.metric_value = EXCLUDED.metric_value
                         AND business_metric_evidence.unit = EXCLUDED.unit
                         AND business_metric_evidence.entered_by IN ('parser', 'source_research')""",
                    (row["company"], row["domain"], row["metric_name"], row["metric_label"],
                     row["fiscal_year"], row["metric_value"], row["unit"], row["scope"],
                     row["source_document_id"], row["page_number"], row["source_quote"],
                     row["source_url"], row["allowed_roles"], entered_by,
                     row["extraction_method"], row["extractor_version"],
                     psycopg.types.json.Jsonb(row["extraction_config"]),
                     chunk_id, chunk_index, content_hash),
                )
            return len(candidates)

    def review_business_metric(self, metric_id: int, status: str, value: float | None,
                               unit: str | None, reviewer: str, company: str) -> bool:
        if status not in {"verified", "rejected"} or (status == "verified" and (value is None or not unit)):
            raise ValueError("Verified business metrics require a value and unit")
        try:
            with self.conn.transaction(), self.conn.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.business_metric_evidence
                       SET status=%s,
                           metric_value=CASE WHEN %s='verified' THEN %s ELSE metric_value END,
                           unit=CASE WHEN %s='verified' THEN %s ELSE unit END,
                           verified_by=CASE WHEN %s='verified' THEN %s ELSE NULL END,
                           verified_at=CASE WHEN %s='verified' THEN now() ELSE NULL END
                       WHERE id=%s AND company=%s AND status='needs_review'""",
                    (status, status, value, status, unit, status, reviewer, status, metric_id, company),
                )
                return cursor.rowcount == 1
        except psycopg.errors.UniqueViolation as error:
            raise ValueError("A verified value already exists for this domain, year, and metric") from error

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
                   WHERE candidate.id=%s AND candidate.status='needs_review'
                     AND (candidate.document_id IS NULL OR EXISTS (
                         SELECT 1 FROM documents d
                         WHERE d.document_id=candidate.document_id
                           AND d.processing_status='ready'
                           AND (%s::text IS NULL OR d.company=%s::text)
                     ))
                     AND (candidate.document_id IS NOT NULL OR
                          (%s::text IS NULL OR candidate.company=%s::text))
                   RETURNING candidate.*""",
                (status, value if status == "verified" else None,
                 unit if status == "verified" else None, reviewer, candidate_id,
                 company, company, company, company),
            )
            candidate = cursor.fetchone()
            if candidate is None:
                return False
            if status == "verified":
                cursor.execute(
                    """INSERT INTO extracted_financial_metrics (
                           company, fiscal_year, metric_name, metric_label, metric_value,
                           unit, document_id, page_number, source_quote, source_quote_hash,
                           source_url, allowed_roles, status, entry_method,
                           source_reference, source_note, verified_by, verified_at,
                           source_chunk_id, source_chunk_index, source_content_hash
                       ) SELECT coalesce(c.company, d.company), coalesce(c.fiscal_year,
                                CASE WHEN d.fiscal_year ~ '^[0-9]{4}$' THEN d.fiscal_year::integer END),
                                c.metric_name, c.metric_label, c.normalized_value, c.unit,
                                d.document_id, c.page_number, c.source_quote,
                                c.source_quote_hash, d.source_url,
                                coalesce(nullif(c.allowed_roles, '{}'::text[]), d.allowed_roles),
                                'verified', c.entry_method, c.source_reference, c.source_note,
                                %s, now(), c.source_chunk_id, c.source_chunk_index,
                                c.source_content_hash
                         FROM extracted_metric_candidates c
                         LEFT JOIN documents d USING(document_id)
                   WHERE c.id=%s
                         ON CONFLICT (company, fiscal_year, metric_name)
                             WHERE status = 'verified' DO NOTHING""",
                    (reviewer, candidate_id),
                )
                if cursor.rowcount == 0:
                    raise ValueError("A verified value already exists for this company, year, and metric")
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

    def uploaded_source(self, document_id: str, company: str, role: str, username: str) -> dict | None:
        """Return private Storage coordinates only to a role allowed on the upload."""
        with self.conn.cursor() as cursor:
            cursor.execute(
                """SELECT title, format, storage_path
                   FROM public.documents
                   WHERE document_id = %s AND company = %s
                     AND source_type = 'user_upload'
                     AND processing_status = 'ready'
                     AND storage_path IS NOT NULL
                     AND (allowed_roles && ARRAY[%s]::text[] OR %s = 'admin'
                          OR (%s = 'document_uploader' AND uploaded_by = %s))""",
                (document_id, company, role, role, role, username),
            )
            return cursor.fetchone()

    def save_business_metric_extraction_run(self, run: dict) -> int:
        """Persist the selector and model outcome without duplicating source text."""
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.business_metric_extraction_runs (
                       document_id, company, decision_domain, extractor_version,
                       prompt_version, model_name, status, input_chunk_count,
                       selected_chunk_count, candidate_count, audit
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (run["document_id"], run["company"], run["decision_domain"],
                 run["extractor_version"], run["prompt_version"], run["model_name"],
                 run["status"], run["input_chunk_count"], run["selected_chunk_count"],
                 run["candidate_count"], psycopg.types.json.Jsonb(run["audit"])),
            )
            return cursor.fetchone()[0]

    def business_metric_extraction_runs(self, document_id: str, company: str) -> list[dict]:
        """Return recent admin audit traces for one source document."""
        with self.conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, document_id, decision_domain, extractor_version,
                          prompt_version, model_name, status, input_chunk_count,
                          selected_chunk_count, candidate_count, audit, created_at
                   FROM public.business_metric_extraction_runs
                   WHERE document_id = %s AND company = %s
                   ORDER BY created_at DESC, id DESC LIMIT 20""",
                (document_id, company),
            )
            return cursor.fetchall()

    def close(self) -> None:
        close_database_connection(self.conn)
