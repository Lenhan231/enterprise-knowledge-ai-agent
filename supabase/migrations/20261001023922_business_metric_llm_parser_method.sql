ALTER TABLE public.business_metric_evidence
    DROP CONSTRAINT business_metric_extraction_method_check;

ALTER TABLE public.business_metric_evidence
    ADD CONSTRAINT business_metric_extraction_method_check
    CHECK (extraction_method IN ('source_research', 'manual', 'parser_rule', 'llm_parser'));
