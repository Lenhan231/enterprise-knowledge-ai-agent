-- Keep historical parser candidates without presenting stale evidence as pending review.
ALTER TABLE public.extracted_metric_candidates
    DROP CONSTRAINT extracted_metric_candidates_status_check;

ALTER TABLE public.extracted_metric_candidates
    ADD CONSTRAINT extracted_metric_candidates_status_check
    CHECK (status IN ('needs_review', 'verified', 'rejected', 'superseded'));
