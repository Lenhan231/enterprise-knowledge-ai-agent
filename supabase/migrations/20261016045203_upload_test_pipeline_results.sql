-- Keep existing isolated OCR runs while broadening the lab to the full upload path.
ALTER TABLE public.ocr_test_runs RENAME TO upload_test_runs;
ALTER TABLE public.ocr_test_pages RENAME TO upload_test_pages;
ALTER TABLE public.ocr_test_chunks RENAME TO upload_test_parser_chunks;
ALTER TABLE public.ocr_test_tables RENAME TO upload_test_tables;

ALTER TABLE public.upload_test_runs
    ADD COLUMN embedding_chunk_count integer NOT NULL DEFAULT 0 CHECK (embedding_chunk_count >= 0),
    ADD COLUMN embedding_status text NOT NULL DEFAULT 'not_run'
        CHECK (embedding_status IN ('embedded', 'failed', 'not_run')),
    ADD COLUMN embedding_model text,
    ADD COLUMN embedding_backend text,
    ADD COLUMN embedding_max_sequence_length integer,
    ADD COLUMN embedding_error text;

ALTER TABLE public.upload_test_tables
    ADD COLUMN columns jsonb NOT NULL DEFAULT '[]'::jsonb;
UPDATE public.upload_test_tables
SET columns = coalesce(structured_data->'columns', '[]'::jsonb);

CREATE TABLE public.upload_test_records (
    run_id uuid NOT NULL,
    table_index integer NOT NULL,
    row_index integer NOT NULL CHECK (row_index >= 0),
    data jsonb NOT NULL,
    PRIMARY KEY (run_id, table_index, row_index),
    FOREIGN KEY (run_id, table_index)
        REFERENCES public.upload_test_tables(run_id, table_index) ON DELETE CASCADE
);

INSERT INTO public.upload_test_records (run_id, table_index, row_index, data)
SELECT t.run_id, t.table_index, rows.ordinality - 1, rows.data
FROM public.upload_test_tables AS t
CROSS JOIN LATERAL jsonb_array_elements(coalesce(t.structured_data->'rows', '[]'::jsonb))
    WITH ORDINALITY AS rows(data, ordinality);
ALTER TABLE public.upload_test_tables DROP COLUMN structured_data;

CREATE TABLE public.upload_test_embedding_chunks (
    run_id uuid NOT NULL REFERENCES public.upload_test_runs(run_id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    content text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding extensions.vector(384) NOT NULL,
    PRIMARY KEY (run_id, chunk_index)
);

ALTER INDEX public.ocr_test_runs_created_idx RENAME TO upload_test_runs_created_idx;
ALTER INDEX public.ocr_test_chunks_page_idx RENAME TO upload_test_parser_chunks_page_idx;
CREATE INDEX upload_test_embedding_chunks_page_idx
    ON public.upload_test_embedding_chunks (run_id, ((metadata->>'page_number')));
CREATE INDEX upload_test_records_table_idx ON public.upload_test_records (run_id, table_index);

ALTER TABLE public.upload_test_embedding_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.upload_test_records ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.upload_test_embedding_chunks FROM anon, authenticated;
REVOKE ALL ON public.upload_test_records FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.upload_test_embedding_chunks TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.upload_test_records TO service_role;
