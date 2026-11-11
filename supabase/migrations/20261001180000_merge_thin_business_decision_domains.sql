-- Fold the two single-purpose domains into their natural management decisions.
-- No metric values, source links, verification status, or RBAC rules change.
UPDATE public.business_metric_evidence
SET domain = 'market_performance'
WHERE domain = 'distribution_reach';

UPDATE public.business_metric_evidence
SET domain = 'manufacturing_efficiency'
WHERE domain = 'manufacturing_quality';
