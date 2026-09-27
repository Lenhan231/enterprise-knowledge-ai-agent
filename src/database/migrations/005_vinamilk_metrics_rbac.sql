-- Separate source-derived analytics from vector chunks. Values remain hidden
-- from the dashboard until reviewed against the referenced report page.
CREATE TABLE IF NOT EXISTS public.extracted_financial_metrics (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company text NOT NULL,
    fiscal_year integer NOT NULL,
    metric_name text NOT NULL,
    metric_label text NOT NULL,
    metric_value numeric NOT NULL,
    unit text NOT NULL,
    document_id text NOT NULL REFERENCES public.documents(document_id),
    page_number integer NOT NULL CHECK (page_number > 0),
    source_quote text NOT NULL,
    source_quote_hash text NOT NULL,
    source_url text NOT NULL,
    allowed_roles text[] NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'needs_review'
        CHECK (status IN ('needs_review', 'verified', 'rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, fiscal_year, metric_name)
);

CREATE INDEX IF NOT EXISTS extracted_financial_metrics_dashboard_idx
    ON public.extracted_financial_metrics (company, metric_name, fiscal_year)
    WHERE status = 'verified';

ALTER TABLE public.extracted_financial_metrics ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.extracted_financial_metrics FROM anon, authenticated;

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('enterprise-documents', 'enterprise-documents', false, 52428800, ARRAY['application/pdf'])
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Keep the bucket private. There are no direct anon/authenticated storage
-- policies; the application accesses it only with a server-side secret key.

-- Uploaded originals live in Supabase Storage. This table is only the upload
-- and processing registry; the bytes never enter PostgreSQL rows.
ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS storage_path text,
    ADD COLUMN IF NOT EXISTS processing_status text NOT NULL DEFAULT 'ready'
        CHECK (processing_status IN ('uploaded', 'processing', 'ready', 'failed')),
    ADD COLUMN IF NOT EXISTS uploaded_by text,
    ADD COLUMN IF NOT EXISTS uploaded_at timestamptz;

GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.extracted_financial_metrics TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.extracted_financial_metrics_id_seq TO service_role;
