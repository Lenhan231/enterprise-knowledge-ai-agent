-- OCR-only inspection data stays separate from production corpus and vectors.
CREATE TABLE public.ocr_test_runs (
    run_id uuid PRIMARY KEY,
    source_filename text NOT NULL,
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    uploaded_by text NOT NULL,
    processor_config jsonb NOT NULL,
    runtime_info jsonb NOT NULL DEFAULT '{}'::jsonb,
    page_count integer NOT NULL CHECK (page_count > 0),
    chunk_count integer NOT NULL CHECK (chunk_count >= 0),
    table_count integer NOT NULL CHECK (table_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.ocr_test_pages (
    run_id uuid NOT NULL REFERENCES public.ocr_test_runs(run_id) ON DELETE CASCADE,
    page_number integer NOT NULL CHECK (page_number > 0),
    preview_png bytea NOT NULL,
    PRIMARY KEY (run_id, page_number)
);

CREATE TABLE public.ocr_test_chunks (
    run_id uuid NOT NULL REFERENCES public.ocr_test_runs(run_id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    content text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (run_id, chunk_index)
);

CREATE TABLE public.ocr_test_tables (
    run_id uuid NOT NULL REFERENCES public.ocr_test_runs(run_id) ON DELETE CASCADE,
    table_index integer NOT NULL CHECK (table_index >= 0),
    page_number integer,
    table_data jsonb NOT NULL,
    PRIMARY KEY (run_id, table_index)
);

CREATE INDEX ocr_test_runs_created_idx ON public.ocr_test_runs (created_at DESC);
CREATE INDEX ocr_test_chunks_page_idx
    ON public.ocr_test_chunks (run_id, ((metadata->>'page_number')));

ALTER TABLE public.ocr_test_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ocr_test_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ocr_test_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ocr_test_tables ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ocr_test_runs, public.ocr_test_pages,
    public.ocr_test_chunks, public.ocr_test_tables FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ocr_test_runs, public.ocr_test_pages,
    public.ocr_test_chunks, public.ocr_test_tables TO service_role;
