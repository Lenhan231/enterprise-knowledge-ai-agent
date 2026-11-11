CREATE TABLE public.extracted_metric_candidates (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id text NOT NULL REFERENCES public.documents(document_id) ON DELETE CASCADE,
    metric_name text NOT NULL,
    metric_label text NOT NULL,
    candidate_values jsonb NOT NULL,
    normalized_value numeric,
    unit text,
    fiscal_year integer,
    page_number integer NOT NULL CHECK (page_number > 0),
    source_quote text NOT NULL,
    source_quote_hash text NOT NULL,
    status text NOT NULL DEFAULT 'needs_review'
        CHECK (status IN ('needs_review', 'verified', 'rejected')),
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, metric_name, page_number, source_quote_hash)
);
CREATE INDEX extracted_metric_candidates_review_idx
    ON public.extracted_metric_candidates (status, document_id);
ALTER TABLE public.extracted_metric_candidates ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.extracted_metric_candidates FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.extracted_metric_candidates TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.extracted_metric_candidates_id_seq TO service_role;
