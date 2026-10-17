ALTER TABLE public.extracted_metric_candidates
    ADD COLUMN IF NOT EXISTS source_chunk_id bigint
        REFERENCES public.document_chunks(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS source_chunk_index integer,
    ADD COLUMN IF NOT EXISTS source_content_hash text;

ALTER TABLE public.extracted_financial_metrics
    ADD COLUMN IF NOT EXISTS source_chunk_id bigint
        REFERENCES public.document_chunks(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS source_chunk_index integer,
    ADD COLUMN IF NOT EXISTS source_content_hash text;
