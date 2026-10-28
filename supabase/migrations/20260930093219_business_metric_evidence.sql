CREATE TABLE public.business_metric_evidence (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company text NOT NULL,
    domain text NOT NULL,
    metric_name text NOT NULL,
    metric_label text NOT NULL,
    fiscal_year integer NOT NULL CHECK (fiscal_year BETWEEN 1900 AND 2100),
    metric_value numeric NOT NULL,
    unit text NOT NULL,
    scope text NOT NULL,
    source_document_id text NOT NULL,
    page_number integer NOT NULL CHECK (page_number > 0),
    source_quote text NOT NULL,
    source_url text NOT NULL,
    status text NOT NULL DEFAULT 'needs_review'
        CHECK (status IN ('needs_review', 'verified', 'rejected')),
    allowed_roles text[] NOT NULL DEFAULT '{}',
    entered_by text NOT NULL,
    verified_by text,
    verified_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company, metric_name, fiscal_year, source_document_id, page_number)
);

CREATE INDEX business_metric_evidence_dashboard_idx
    ON public.business_metric_evidence (company, domain, metric_name, fiscal_year)
    WHERE status = 'verified';
CREATE INDEX business_metric_evidence_review_idx
    ON public.business_metric_evidence (company, status, created_at DESC)
    WHERE status = 'needs_review';
CREATE UNIQUE INDEX business_metric_evidence_verified_period_uq
    ON public.business_metric_evidence (company, domain, metric_name, fiscal_year)
    WHERE status = 'verified';

ALTER TABLE public.business_metric_evidence ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.business_metric_evidence FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.business_metric_evidence TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.business_metric_evidence_id_seq TO service_role;


-- Retired source observations are intentionally not seeded.
