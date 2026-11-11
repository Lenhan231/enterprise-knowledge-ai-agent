ALTER TABLE public.extracted_metric_candidates
    ALTER COLUMN document_id DROP NOT NULL,
    ALTER COLUMN page_number DROP NOT NULL,
    ALTER COLUMN source_quote DROP NOT NULL,
    ALTER COLUMN source_quote_hash DROP NOT NULL,
    ADD COLUMN company text,
    ADD COLUMN allowed_roles text[] NOT NULL DEFAULT '{}'::text[],
    ADD COLUMN entry_method text NOT NULL DEFAULT 'extracted'
        CHECK (entry_method IN ('extracted', 'manual')),
    ADD COLUMN source_reference text,
    ADD COLUMN source_note text;

ALTER TABLE public.extracted_financial_metrics
    ALTER COLUMN document_id DROP NOT NULL,
    ALTER COLUMN page_number DROP NOT NULL,
    ALTER COLUMN source_quote DROP NOT NULL,
    ALTER COLUMN source_quote_hash DROP NOT NULL,
    ALTER COLUMN source_url DROP NOT NULL,
    ADD COLUMN entry_method text NOT NULL DEFAULT 'extracted'
        CHECK (entry_method IN ('extracted', 'manual')),
    ADD COLUMN source_reference text,
    ADD COLUMN source_note text,
    ADD COLUMN verified_by text,
    ADD COLUMN verified_at timestamptz;

CREATE UNIQUE INDEX extracted_financial_metrics_company_period_name_uq
    ON public.extracted_financial_metrics (company, fiscal_year, metric_name)
    WHERE status = 'verified';
