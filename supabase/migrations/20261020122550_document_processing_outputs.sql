-- Preserve normalized parser output separately from downstream chunks.
CREATE TABLE public.document_processing_outputs (
    document_id text PRIMARY KEY
        REFERENCES public.documents(document_id) ON DELETE CASCADE,
    pipeline_id text NOT NULL,
    elements jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(elements) = 'array'),
    structured_tables jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(structured_tables) = 'array'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.document_processing_outputs ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON public.document_processing_outputs FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.document_processing_outputs TO service_role;
