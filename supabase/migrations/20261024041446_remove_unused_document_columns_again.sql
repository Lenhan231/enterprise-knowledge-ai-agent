ALTER TABLE public.documents
    DROP COLUMN IF EXISTS company,
    DROP COLUMN IF EXISTS fiscal_year,
    DROP COLUMN IF EXISTS source_url;
