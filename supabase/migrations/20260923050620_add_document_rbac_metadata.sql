ALTER TABLE public.documents
    ADD COLUMN company text,
    ADD COLUMN source_type text,
    ADD COLUMN allowed_roles text[] NOT NULL DEFAULT '{}'::text[],
    ADD COLUMN access_scope text;
