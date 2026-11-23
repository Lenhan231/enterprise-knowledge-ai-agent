CREATE TABLE public.document_pdf_jobs (
    document_id text PRIMARY KEY REFERENCES public.documents(document_id) ON DELETE CASCADE,
    lock_id integer GENERATED ALWAYS AS IDENTITY UNIQUE,
    filename text NOT NULL,
    source_sha256 text NOT NULL,
    parser_config jsonb NOT NULL,
    document_metadata jsonb NOT NULL,
    parser_handoff boolean NOT NULL,
    page_count integer NOT NULL CHECK (page_count > 0),
    pages_processed integer NOT NULL DEFAULT 0 CHECK (pages_processed BETWEEN 0 AND page_count),
    batch_size integer NOT NULL CHECK (batch_size > 0),
    attempt integer NOT NULL DEFAULT 1,
    queued_at timestamptz NOT NULL DEFAULT now(),
    failed_page integer,
    result jsonb
);

CREATE TABLE public.document_pdf_checkpoints (
    document_id text NOT NULL REFERENCES public.document_pdf_jobs(document_id) ON DELETE CASCADE,
    first_page integer NOT NULL CHECK (first_page > 0),
    output jsonb NOT NULL,
    PRIMARY KEY (document_id, first_page)
);

ALTER TABLE public.document_pdf_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_pdf_checkpoints ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.document_pdf_jobs, public.document_pdf_checkpoints FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.document_pdf_jobs, public.document_pdf_checkpoints TO service_role;
