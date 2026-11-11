ALTER TABLE public.business_metric_evidence
    ADD COLUMN extraction_method text NOT NULL DEFAULT 'source_research',
    ADD COLUMN extractor_version text NOT NULL DEFAULT 'catalog-v1',
    ADD COLUMN extraction_config jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN source_chunk_index integer,
    ADD COLUMN source_content_hash text;

ALTER TABLE public.business_metric_evidence
    ADD CONSTRAINT business_metric_extraction_method_check
    CHECK (extraction_method IN ('source_research', 'manual', 'parser_rule'));

ALTER TABLE public.business_metric_evidence
    ADD CONSTRAINT business_metric_source_chunk_fk
    FOREIGN KEY (source_document_id, source_chunk_index)
    REFERENCES public.processed_document_chunks (document_id, chunk_index)
    ON DELETE SET NULL (source_chunk_index);

CREATE INDEX business_metric_source_chunk_idx
    ON public.business_metric_evidence (source_document_id, source_chunk_index)
    WHERE source_chunk_index IS NOT NULL;
