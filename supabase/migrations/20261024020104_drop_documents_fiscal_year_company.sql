-- IF EXISTS also supports the project where these columns were dropped directly.
ALTER TABLE public.documents
    DROP COLUMN IF EXISTS fiscal_year,
    DROP COLUMN IF EXISTS company;
