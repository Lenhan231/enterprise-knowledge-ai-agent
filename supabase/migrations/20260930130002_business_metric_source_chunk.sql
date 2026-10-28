-- Business KPI evidence points at the indexed corpus chunk used by retrieval.
-- `processed_document_chunks` contains ingestion/OCR workflow rows, but the
-- Existing application documents are stored in the active `document_chunks` table.
ALTER TABLE public.business_metric_evidence
    DROP CONSTRAINT business_metric_source_chunk_fk;

ALTER TABLE public.business_metric_evidence
    ADD COLUMN source_chunk_id bigint;

ALTER TABLE public.business_metric_evidence
    ADD CONSTRAINT business_metric_source_chunk_fk
    FOREIGN KEY (source_chunk_id)
    REFERENCES public.document_chunks (id)
    ON DELETE SET NULL;

CREATE INDEX business_metric_source_chunk_id_idx
    ON public.business_metric_evidence (source_chunk_id)
    WHERE source_chunk_id IS NOT NULL;
