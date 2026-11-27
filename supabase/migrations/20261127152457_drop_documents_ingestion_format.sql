-- Align fresh installs with the current documents schema and upload code.
ALTER TABLE public.documents
    DROP COLUMN IF EXISTS ingestion_format;
