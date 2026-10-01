CREATE TABLE public.business_metric_extraction_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id text NOT NULL REFERENCES public.documents(document_id) ON DELETE CASCADE,
    company text NOT NULL,
    decision_domain text NOT NULL,
    extractor_version text NOT NULL,
    prompt_version text NOT NULL,
    model_name text NOT NULL,
    status text NOT NULL CHECK (status IN (
        'completed', 'no_chunks_selected', 'partial', 'failed',
        'provider_unavailable', 'unsupported_format'
    )),
    input_chunk_count integer NOT NULL CHECK (input_chunk_count >= 0),
    selected_chunk_count integer NOT NULL CHECK (selected_chunk_count >= 0),
    candidate_count integer NOT NULL CHECK (candidate_count >= 0),
    audit jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX business_metric_extraction_runs_document_idx
    ON public.business_metric_extraction_runs (document_id, decision_domain, created_at DESC);

ALTER TABLE public.business_metric_extraction_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.business_metric_extraction_runs FROM anon, authenticated;
GRANT SELECT, INSERT ON public.business_metric_extraction_runs TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.business_metric_extraction_runs_id_seq TO service_role;
