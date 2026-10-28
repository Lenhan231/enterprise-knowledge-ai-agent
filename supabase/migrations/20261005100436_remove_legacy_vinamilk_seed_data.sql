-- Keep historical migrations immutable while ensuring a fresh database does not
-- reintroduce the retired Vinamilk corpus or its source-linked metric rows.
DELETE FROM public.business_metric_evidence
WHERE company ILIKE '%vinamilk%'
   OR source_document_id LIKE 'VNM-%'
   OR source_url ILIKE '%vinamilk.%';

DELETE FROM public.extracted_financial_metrics
WHERE company ILIKE '%vinamilk%'
   OR document_id LIKE 'VNM-%';

DELETE FROM public.extracted_metric_candidates
WHERE document_id LIKE 'VNM-%';

DELETE FROM public.extracted_tables
WHERE document_id LIKE 'VNM-%'
   OR document_name ILIKE '%vinamilk%';

DELETE FROM public.ocr_test_runs
WHERE source_filename ILIKE '%vinamilk%'
   OR source_filename ILIKE '%vnm-%';

DELETE FROM public.document_chunks
WHERE metadata->>'document_id' LIKE 'VNM-%'
   OR metadata::text ILIKE '%vinamilk%'
   OR document_name ILIKE '%vinamilk%';

DELETE FROM public.documents
WHERE document_id LIKE 'VNM-%'
   OR company ILIKE '%vinamilk%';
