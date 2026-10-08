# src/core/database/documents_repository.py
import os
import re

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from core.database.connection_limit import close_database_connection, connect_database
from core.analytics.sql_safety import UnsafeAnalyticsQuery, validate_analytics_sql, validate_commerce_sql
from core.analytics.commerce_decision_support import COMMERCE_DECISION_PROFILES, COMMERCE_QUERY_TABLES

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

    def list_knowledge_documents(self) -> list[dict]:
        """List indexed source documents and their retrieval status for Admin."""
        with self.conn.cursor() as cursor:
            cursor.execute("""SELECT d.document_id, d.title, d.company, d.domain,
                                    d.document_type, d.format, d.source_url,
                                    d.source_type, d.processing_status,
                                    d.knowledge_base_active,
                                    d.allowed_roles,
                                    count(c.id)::int AS chunk_count,
                                    max(c.metadata->>'source_publisher') AS source_publisher,
                                    max(c.metadata->>'external_reference_type') AS reference_type,
                                    max(c.metadata->>'evidence_class') AS evidence_class,
                                    bool_or(c.metadata->>'synthetic_company_policy' = 'true') AS synthetic_company_policy,
                                    ARRAY(
                                        SELECT DISTINCT jsonb_array_elements_text(x.metadata->'knowledge_domains')
                                        FROM public.document_chunks x
                                        WHERE x.metadata->>'document_id' = d.document_id
                                          AND jsonb_typeof(x.metadata->'knowledge_domains') = 'array'
                                    ) AS knowledge_domains
                               FROM public.documents d
                               LEFT JOIN public.document_chunks c
                                 ON c.metadata->>'document_id' = d.document_id
                              GROUP BY d.document_id
                              ORDER BY d.knowledge_base_active DESC, d.title""")
            return cursor.fetchall()

    def set_document_allowed_roles(self, document_id: str, allowed_roles: list[str]) -> bool:
        """Replace a saved document's retrieval roles without reprocessing its chunks."""
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute("""UPDATE public.documents
                                SET allowed_roles = %s::text[]
                              WHERE document_id = %s
                                AND EXISTS (
                                    SELECT 1 FROM public.document_chunks c
                                    WHERE c.metadata->>'document_id' = documents.document_id
                                )
                          RETURNING document_id""", (allowed_roles, document_id))
            return cursor.fetchone() is not None

    def set_knowledge_base_active(self, document_id: str, active: bool) -> bool:
        """Toggle retrieval eligibility without deleting source, chunks, or metrics."""
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute("""UPDATE public.documents
                                SET knowledge_base_active = %s
                              WHERE document_id = %s
                                AND (%s IS FALSE OR (
                                    processing_status = 'ready'
                                    AND EXISTS (
                                        SELECT 1 FROM public.document_chunks c
                                        WHERE c.metadata->>'document_id' = documents.document_id
                                    )
                                ))
                          RETURNING document_id""", (active, document_id, active))
            return cursor.fetchone() is not None

    def upsert_document(self, document: dict) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO documents (
                    document_id, domain, title, year_or_version, format,
                    source_url, verification,
                    document_type, fiscal_year, company, source_type,
                    allowed_roles, storage_path, processing_status,
                    knowledge_base_active
                ) VALUES (
                    %(document_id)s, %(domain)s, %(title)s, %(year_or_version)s,
                    %(format)s, %(source_url)s,
                    %(verification)s, %(document_type)s,
                    %(fiscal_year)s, %(company)s, %(source_type)s,
                    %(allowed_roles)s, %(storage_path)s, %(processing_status)s,
                    %(knowledge_base_active)s
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
                    storage_path = COALESCE(EXCLUDED.storage_path, documents.storage_path),
                    processing_status = EXCLUDED.processing_status
                """,
                {**document, "storage_path": document.get("storage_path"),
                 "knowledge_base_active": document.get("knowledge_base_active", True)},
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

    def corpus_dashboard(
        self, role: str, username: str = "", company: str | None = None,
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
                       d.processing_status, count(c.id)::int AS chunks,
                       ARRAY(
                           SELECT DISTINCT jsonb_array_elements_text(reference.metadata->'knowledge_domains')
                           FROM document_chunks reference
                           WHERE reference.metadata->>'document_id' = d.document_id
                             AND jsonb_typeof(reference.metadata->'knowledge_domains') = 'array'
                       ) AS knowledge_domains,
                       max(c.metadata->>'source_publisher') AS source_publisher,
                       max(c.metadata->>'external_reference_type') AS external_reference_type
                FROM documents d
                LEFT JOIN document_chunks c
                  ON c.metadata->>'document_id' = d.document_id
                 AND coalesce(d.processing_status, 'ready') = 'ready'
                WHERE d.source_type IN ('public_enterprise_document', 'user_upload', 'synthetic_demo_policy')
                  AND d.knowledge_base_active IS TRUE
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
                    WHERE d.source_type IN ('public_enterprise_document', 'user_upload', 'synthetic_demo_policy')
                      AND d.knowledge_base_active IS TRUE
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
                    WHERE d.source_type IN ('public_enterprise_document', 'user_upload', 'synthetic_demo_policy')
                      AND d.knowledge_base_active IS TRUE
                      AND {visible_filter}
                    GROUP BY d.document_id ORDER BY d.title""",
                visible_params,
            )
            quality = cursor.fetchall()
            cursor.execute(
                f"""SELECT d.company, d.fiscal_year, d.processing_status, count(*)::int AS documents
                    FROM documents d
                    WHERE d.source_type IN ('public_enterprise_document', 'user_upload', 'synthetic_demo_policy')
                      AND d.knowledge_base_active IS TRUE
                      AND {visible_filter}
                    GROUP BY d.company, d.fiscal_year, d.processing_status
                    ORDER BY d.company, d.fiscal_year NULLS LAST, d.processing_status""",
                visible_params,
            )
            processing = cursor.fetchall()
        return {
            "documents": documents,
            "domains": domains,
            "quality": quality,
            "processing": processing,
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
                    ids = row.get("evidence_metric_ids")
                    if isinstance(ids, (list, tuple)):
                        metric_ids.update(value for value in ids if isinstance(value, int))
                    document_evidence_ids = row.get("evidence_document_ids")
                    if isinstance(document_evidence_ids, (list, tuple)):
                        document_ids.update(value for value in document_evidence_ids if isinstance(value, str))
                if len(metric_ids) > 500 or len(document_ids) > 250:
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
        return {"results": results, "evidence": evidence, "documents": documents}

    def commerce_dashboard(self, keys: tuple[str, ...] | None = None) -> dict:
        """Return descriptive dashboard aggregates from the private synthetic Commerce schema."""
        queries = {
            "overview": """SELECT min(date)::text AS first_day, max(date)::text AS last_day,
                       sum(revenue)::double precision AS revenue,
                       sum(cogs)::double precision AS cogs,
                       (sum(revenue) - sum(cogs))::double precision AS gross_profit,
                       CASE WHEN sum(revenue) = 0 THEN NULL
                            ELSE ((sum(revenue) - sum(cogs)) / sum(revenue))::double precision END AS gross_margin
                    FROM commerce.sales""",
            "sales_by_year": """SELECT extract(year FROM date)::int AS year,
                       sum(revenue)::double precision AS revenue,
                       sum(cogs)::double precision AS cogs,
                       (sum(revenue) - sum(cogs))::double precision AS gross_profit,
                       CASE WHEN sum(revenue) = 0 THEN NULL
                            ELSE ((sum(revenue) - sum(cogs)) / sum(revenue))::double precision END AS gross_margin
                    FROM commerce.sales GROUP BY 1 ORDER BY 1""",
            "inventory_by_year": """SELECT year, count(*)::int AS sku_snapshots,
                       count(DISTINCT product_id)::int AS products,
                       round(avg(stock_on_hand)::numeric, 0)::bigint AS avg_stock_on_hand,
                       count(*) FILTER (WHERE stockout_flag)::int AS stockout_snapshots,
                       count(*) FILTER (WHERE overstock_flag)::int AS overstock_snapshots,
                       round(avg(stockout_days)::numeric, 2)::double precision AS avg_stockout_days,
                       round(avg(fill_rate)::numeric, 4)::double precision AS avg_fill_rate
                    FROM commerce.inventory GROUP BY year ORDER BY year""",
            "inventory_year_end_by_category": """WITH year_end AS (
                       SELECT year, max(snapshot_date) AS snapshot_date
                       FROM commerce.inventory GROUP BY year
                    )
                    SELECT i.year, i.snapshot_date::text AS snapshot_date, i.category,
                       count(*)::int AS products, sum(i.stock_on_hand)::bigint AS stock_on_hand,
                       count(*) FILTER (WHERE i.stockout_flag)::int AS stockout_products,
                       count(*) FILTER (WHERE i.overstock_flag)::int AS overstock_products,
                       count(*) FILTER (WHERE i.stockout_flag AND i.overstock_flag)::int AS both_flagged_products
                    FROM commerce.inventory i JOIN year_end y USING (year, snapshot_date)
                    GROUP BY i.year, i.snapshot_date, i.category ORDER BY i.year, i.category""",
            "inventory_latest_by_category": """WITH latest AS (SELECT max(snapshot_date) AS snapshot_date FROM commerce.inventory)
                    SELECT i.snapshot_date::text AS snapshot_date, i.category, count(*)::int AS products,
                       sum(i.stock_on_hand)::bigint AS stock_on_hand,
                       count(*) FILTER (WHERE i.stockout_flag)::int AS stockout_products,
                       count(*) FILTER (WHERE i.overstock_flag)::int AS overstock_products,
                       count(*) FILTER (WHERE i.stockout_flag AND i.overstock_flag)::int AS both_flagged_products
                    FROM commerce.inventory i JOIN latest l USING (snapshot_date)
                    GROUP BY i.snapshot_date, i.category ORDER BY i.category""",
            "inventory_latest_flag_overlap": """WITH latest AS (SELECT max(snapshot_date) AS snapshot_date FROM commerce.inventory)
                    SELECT i.snapshot_date::text AS snapshot_date, count(*)::int AS product_rows,
                       count(*) FILTER (WHERE i.stockout_flag)::int AS stockout_flagged_rows,
                       count(*) FILTER (WHERE i.overstock_flag)::int AS overstock_flagged_rows,
                       count(*) FILTER (WHERE i.stockout_flag AND i.overstock_flag)::int AS both_flagged_rows
                    FROM commerce.inventory i JOIN latest l USING (snapshot_date)
                    GROUP BY i.snapshot_date""",
            "promotions_by_year": """SELECT * FROM commerce.dashboard_promotions_by_year
                    ORDER BY year, used_promotion""",
            "promotions_by_campaign": """SELECT * FROM commerce.dashboard_promotions_by_campaign
                    ORDER BY year DESC, net_item_sales DESC, campaign""",
            "logistics_by_year_region": """SELECT * FROM commerce.dashboard_logistics_by_year_region
                    ORDER BY year, region""",
        }
        if keys is not None:
            unknown = set(keys) - queries.keys()
            if unknown:
                raise ValueError(f"Unsupported Commerce dashboard aggregates: {', '.join(sorted(unknown))}")
            queries = {key: queries[key] for key in keys}

        result = {}
        with self.conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '10s'")
            for name, sql in queries.items():
                cursor.execute(sql)
                rows = cursor.fetchall()
                result[name] = rows[0] if name == "overview" and rows else rows
        data_notes = ["Commerce records are synthetic competition data, not actual company operating results."]
        selected_keys = set(queries)
        if selected_keys & {"promotions_by_year", "promotions_by_campaign"}:
            data_notes.extend((
                "Promotion comparisons are descriptive; the data has no randomized holdout and does not establish causal uplift.",
                "Promotion tables include merchandise gross-profit and margin proxies from transaction item prices, discounts, and catalog COGS. They are not contribution margin or campaign ROI; catalog cost assumptions and campaign costs are not validated.",
            ))
        if selected_keys & {"inventory_by_year", "inventory_year_end_by_category", "inventory_latest_by_category", "inventory_latest_flag_overlap"}:
            data_notes.append("The stored days_of_supply values are anomalously large, so they are excluded from decision summaries.")
        if "logistics_by_year_region" in selected_keys:
            data_notes.append("Geography is grouped into dataset regions; carrier, warehouse origin, route capacity and promised SLA are not available.")
        return {**result, "data_notes": data_notes}

    def commerce_decision_snapshot(self, domain: str) -> dict:
        """Return a bounded, read-only SQL evidence slice for one Commerce decision domain."""
        profile = COMMERCE_DECISION_PROFILES.get(domain)
        if profile is None:
            raise ValueError(f"Unsupported Commerce decision domain: {domain}")
        dashboard = self.commerce_dashboard(profile["dashboard_keys"])
        selected = {}
        for key in profile["dashboard_keys"]:
            rows = dashboard.get(key, [])
            if key == "inventory_latest_flag_overlap":
                selected[key] = rows
                continue
            if key == "inventory_latest_by_category":
                ranked = sorted(
                    rows,
                    key=lambda row: row.get("stockout_products", 0) + row.get("overstock_products", 0),
                    reverse=True,
                )
                selected[key] = ranked[:12]
                continue
            if key == "promotions_by_campaign":
                rows_by_year = {}
                for row in rows:
                    rows_by_year.setdefault(int(row["year"]), []).append(row)
                years = sorted(rows_by_year)[-3:]
                selected[key] = [
                    row for year in years
                    for row in sorted(rows_by_year[year], key=lambda item: item.get("net_item_sales", 0), reverse=True)[:12]
                ]
                continue
            years = sorted({int(row["year"]) for row in rows if row.get("year") is not None})
            recent = set(years[-3:])
            selected[key] = [row for row in rows if int(row["year"]) in recent]
        return {
            "domain": domain,
            "domain_label": profile["label"],
            "source_tables": list(profile["source_tables"]),
            "observations": selected,
            "limitations": list(profile["limitations"]),
            "dataset_note": "Synthetic Kaggle Datathon 2026 Round 1 Commerce data; not observed results from a real retailer.",
        }

    def execute_commerce_analytics(self, query: str, domain: str) -> list[dict]:
        """Run a domain-scoped, validated SELECT over synthetic Commerce data."""
        table_columns = COMMERCE_QUERY_TABLES.get(domain)
        if table_columns is None:
            raise ValueError(f"Unsupported Commerce decision domain: {domain}")
        query = validate_commerce_sql(query, table_columns)
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '5s'")
            try:
                cursor.execute(query)
                columns = [item.name for item in cursor.description]
                return [dict(row) if isinstance(row, dict) else dict(zip(columns, row))
                        for row in cursor.fetchall()]
            except psycopg.Error as error:
                detail = f" ({type(error).__name__}, SQLSTATE {error.sqlstate})" if error.sqlstate else f" ({type(error).__name__})"
                database_message = error.diag.message_primary
                if database_message:
                    database_message = re.sub(r"'[^']*'", "'<value>'", database_message)
                    detail += f": {database_message[:180]}"
                raise UnsafeAnalyticsQuery(f"The Commerce SELECT could not be executed{detail}") from error

    def latest_commerce_inventory_snapshot(self) -> str | None:
        """Return the latest inventory snapshot date for bounded latest-snapshot queries."""
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT max(snapshot_date)::text AS snapshot_date FROM commerce.inventory")
            row = cursor.fetchone()
            return row["snapshot_date"] if row else None

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

    def accessible_synthetic_policy_source(self, document_id: str, company: str, role: str) -> dict | None:
        """Check corpus ACL before serving a manifest-registered demo policy file."""
        with self.conn.cursor() as cursor:
            cursor.execute(
                """SELECT title, format
                   FROM public.documents
                   WHERE document_id = %s AND company = %s
                     AND source_type = 'synthetic_demo_policy'
                     AND processing_status = 'ready'
                     AND knowledge_base_active IS TRUE
                     AND (allowed_roles && ARRAY[%s]::text[] OR %s = 'admin')""",
                (document_id, company, role, role),
            )
            return cursor.fetchone()

    def close(self) -> None:
        close_database_connection(self.conn)
