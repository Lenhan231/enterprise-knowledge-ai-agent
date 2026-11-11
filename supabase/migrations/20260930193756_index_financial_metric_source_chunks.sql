CREATE INDEX IF NOT EXISTS extracted_metric_candidates_source_chunk_id_idx
    ON public.extracted_metric_candidates (source_chunk_id)
    WHERE source_chunk_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS extracted_financial_metrics_source_chunk_id_idx
    ON public.extracted_financial_metrics (source_chunk_id)
    WHERE source_chunk_id IS NOT NULL;
