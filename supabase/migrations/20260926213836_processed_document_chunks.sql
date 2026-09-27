-- Retain parsed/layout-aware chunks so embedding can be retried independently.
CREATE TABLE public.processed_document_chunks (
    document_id text NOT NULL REFERENCES public.documents(document_id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    content text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    processing_status text NOT NULL DEFAULT 'extracted'
        CHECK (processing_status IN ('extracted', 'embedding', 'embedded', 'failed')),
    processing_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, chunk_index)
);

CREATE INDEX processed_document_chunks_status_idx
    ON public.processed_document_chunks (processing_status, document_id);

ALTER TABLE public.processed_document_chunks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.processed_document_chunks FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.processed_document_chunks TO service_role;
