ALTER TABLE public.document_processing_outputs
    ADD COLUMN document_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(document_metadata) = 'object');
