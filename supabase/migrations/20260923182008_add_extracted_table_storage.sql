CREATE TABLE public.extracted_tables (
    id text PRIMARY KEY,
    document_id text NOT NULL,
    document_name text NOT NULL,
    page_number integer NOT NULL,
    table_index integer NOT NULL,
    columns jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_extracted_table_source UNIQUE (document_id, page_number, table_index)
);
CREATE INDEX ix_extracted_tables_document_id ON public.extracted_tables (document_id);
ALTER TABLE public.extracted_tables ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.extracted_tables FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.extracted_tables TO service_role;

CREATE TABLE public.extracted_records (
    id text PRIMARY KEY,
    table_id text NOT NULL REFERENCES public.extracted_tables(id) ON DELETE CASCADE,
    row_index integer NOT NULL,
    data jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_extracted_record_row UNIQUE (table_id, row_index)
);
CREATE INDEX ix_extracted_records_table_id ON public.extracted_records (table_id);
ALTER TABLE public.extracted_records ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.extracted_records FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.extracted_records TO service_role;
