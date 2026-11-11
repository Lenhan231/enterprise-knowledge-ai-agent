ALTER TABLE public.documents RENAME COLUMN official_url TO source_url;
ALTER TABLE public.documents ALTER COLUMN source_url DROP NOT NULL;
UPDATE public.documents SET source_url = NULL WHERE source_url = '';
