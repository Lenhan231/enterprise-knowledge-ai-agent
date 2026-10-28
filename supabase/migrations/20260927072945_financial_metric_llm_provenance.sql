ALTER TABLE public.extracted_metric_candidates
    ADD COLUMN IF NOT EXISTS extraction_method text NOT NULL DEFAULT 'rule_based_page_evidence',
    ADD COLUMN IF NOT EXISTS extractor_model text,
    ADD COLUMN IF NOT EXISTS prompt_version text,
    ADD COLUMN IF NOT EXISTS selection_evidence jsonb NOT NULL DEFAULT '{}'::jsonb;
