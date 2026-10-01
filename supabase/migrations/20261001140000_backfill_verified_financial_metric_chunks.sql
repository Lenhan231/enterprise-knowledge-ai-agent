BEGIN;

WITH targets(document_id, fiscal_year, metric_name, page_number, expected_value, source_label) AS (
    VALUES
        ('VNM-AR-2020-VI', 2020, 'profit_after_tax', 2, 11236::numeric, 'profit after tax'),
        ('VNM-AR-2020-VI', 2020, 'total_consolidated_revenue', 8, 59723::numeric, 'consolidated net revenue'),
        ('VNM-AR-2021-VI', 2021, 'total_assets', 10, 53332::numeric, 'total assets'),
        ('VNM-AR-2020-VI', 2020, 'total_assets', 9, 48432::numeric, 'total assets'),
        ('VNM-AR-2020-VI', 2020, 'profit_before_tax', 9, 13519::numeric, 'profit before tax'),
        ('VNM-AR-2020-VI', 2020, 'cost_of_goods_sold', 73, 31967662837839::numeric, 'cost of sales'),
        ('VNM-AR-2020-VI', 2020, 'gross_profit', 73, 27668623387708::numeric, 'gross profit')
), candidates AS (
    SELECT m.id AS metric_id, c.id AS chunk_id, c.chunk_index,
           encode(digest(c.content, 'sha256'), 'hex') AS content_hash,
           CASE
               WHEN position(
                   regexp_replace(lower(m.source_quote), '[^[:alnum:]]', '', 'g')
                   IN regexp_replace(lower(c.content), '[^[:alnum:]]', '', 'g')
               ) > 0 THEN 0
               ELSE 1
           END AS match_rank
    FROM targets t
    JOIN public.extracted_financial_metrics m
      ON m.document_id = t.document_id
     AND m.fiscal_year = t.fiscal_year
     AND m.metric_name = t.metric_name
     AND m.page_number = t.page_number
     AND m.metric_value = t.expected_value
     AND m.status = 'verified'
     AND m.source_chunk_id IS NULL
    JOIN public.document_chunks c
      ON c.metadata->>'document_id' = t.document_id
     AND c.metadata->>'page_number' = t.page_number::text
    WHERE
        position(
            regexp_replace(lower(m.source_quote), '[^[:alnum:]]', '', 'g')
            IN regexp_replace(lower(c.content), '[^[:alnum:]]', '', 'g')
        ) > 0
        OR (
            position(lower(t.source_label) IN lower(c.content)) > 0
            AND position(
                regexp_replace(t.expected_value::text, '[^0-9]', '', 'g')
                IN regexp_replace(c.content, '[^0-9]', '', 'g')
            ) > 0
        )
), ranked AS (
    SELECT *, min(match_rank) OVER (PARTITION BY metric_id) AS best_rank
    FROM candidates
), unique_matches AS (
    SELECT *, count(*) OVER (PARTITION BY metric_id) AS best_match_count
    FROM ranked
    WHERE match_rank = best_rank
)
UPDATE public.extracted_financial_metrics AS target
SET source_chunk_id = match.chunk_id,
    source_chunk_index = match.chunk_index,
    source_content_hash = match.content_hash
FROM unique_matches AS match
WHERE target.id = match.metric_id
  AND match.best_match_count = 1;

DO $$
DECLARE unresolved integer;
BEGIN
    SELECT count(*) INTO unresolved
    FROM (VALUES
        ('VNM-AR-2020-VI', 2020, 'profit_after_tax', 2),
        ('VNM-AR-2020-VI', 2020, 'total_consolidated_revenue', 8),
        ('VNM-AR-2021-VI', 2021, 'total_assets', 10),
        ('VNM-AR-2020-VI', 2020, 'total_assets', 9),
        ('VNM-AR-2020-VI', 2020, 'profit_before_tax', 9),
        ('VNM-AR-2020-VI', 2020, 'cost_of_goods_sold', 73),
        ('VNM-AR-2020-VI', 2020, 'gross_profit', 73)
    ) AS expected(document_id, fiscal_year, metric_name, page_number)
    JOIN public.extracted_financial_metrics m
      ON m.document_id = expected.document_id
     AND m.fiscal_year = expected.fiscal_year
     AND m.metric_name = expected.metric_name
     AND m.page_number = expected.page_number
     AND m.status = 'verified'
    WHERE m.source_chunk_id IS NULL OR m.source_content_hash IS NULL;

    IF unresolved > 0 THEN
        RAISE EXCEPTION 'Financial metric provenance backfill left % verified KPI rows unresolved', unresolved;
    END IF;
END $$;

COMMIT;
