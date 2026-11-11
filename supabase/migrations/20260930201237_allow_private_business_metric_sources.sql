-- Business metrics from user-uploaded files link to an authorized internal document
-- route; they do not require a public HTTPS source URL.
ALTER TABLE public.business_metric_evidence
    ALTER COLUMN source_url DROP NOT NULL;
