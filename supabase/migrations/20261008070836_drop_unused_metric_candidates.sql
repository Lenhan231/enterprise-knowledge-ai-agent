-- Remove the legacy review queue; the application no longer writes or reads it.
DROP TABLE IF EXISTS public.extracted_metric_candidates;
