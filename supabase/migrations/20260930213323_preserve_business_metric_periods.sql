-- Keep full-year and partial-year evidence for the same metric/year distinct.
DROP INDEX IF EXISTS public.business_metric_evidence_verified_period_uq;

CREATE UNIQUE INDEX business_metric_evidence_verified_period_uq
    ON public.business_metric_evidence (
        company,
        domain,
        metric_name,
        fiscal_year,
        (COALESCE(NULLIF(extraction_config->>'period', ''), 'FY'))
    )
    WHERE status = 'verified';
