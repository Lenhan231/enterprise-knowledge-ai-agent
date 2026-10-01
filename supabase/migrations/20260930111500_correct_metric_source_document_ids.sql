-- Align source document IDs with the English report URL used by these observations.
UPDATE public.business_metric_evidence
SET source_document_id = 'VNM-AR-2024-EN'
WHERE company = 'Công ty Cổ phần Sữa Việt Nam (Vinamilk)'
  AND source_document_id = 'VNM-AR-2024-VI'
  AND (
      (metric_name IN ('supply_chain_customer_satisfaction', 'purchasing_cost_savings') AND page_number = 60)
      OR (metric_name IN ('production_cost_savings', 'production_lines_meeting_oee_target') AND page_number = 85)
      OR (metric_name = 'new_or_relaunched_products' AND page_number = 89)
  );

UPDATE public.business_metric_evidence
SET source_quote = '125 new and re-launched products across 10 product lines'
WHERE company = 'Công ty Cổ phần Sữa Việt Nam (Vinamilk)'
  AND source_document_id = 'VNM-AR-2024-EN'
  AND metric_name = 'new_or_relaunched_products'
  AND fiscal_year = 2024
  AND page_number = 89;
