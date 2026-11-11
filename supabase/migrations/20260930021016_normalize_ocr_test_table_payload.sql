ALTER TABLE public.ocr_test_tables
    ADD COLUMN structured_data jsonb,
    ADD COLUMN context jsonb,
    ADD COLUMN metadata jsonb;

UPDATE public.ocr_test_tables AS test_table
SET structured_data = jsonb_build_object(
        'columns', COALESCE(test_table.table_data->'columns', '[]'::jsonb),
        'rows', COALESCE(test_table.table_data->'rows', '[]'::jsonb)
    ),
    context = COALESCE(test_table.table_data->'context', '{}'::jsonb)
        || jsonb_build_object(
            'source_filename', test_run.source_filename,
            'page_number', test_table.page_number,
            'section_title', (
                SELECT chunk.metadata->>'section_title'
                FROM public.ocr_test_chunks AS chunk
                WHERE chunk.run_id = test_table.run_id
                  AND chunk.metadata->>'page_number' = test_table.page_number::text
                  AND NULLIF(chunk.metadata->>'section_title', '') IS NOT NULL
                ORDER BY chunk.chunk_index
                LIMIT 1
            )
        ),
    metadata = COALESCE(test_table.table_data->'metadata', '{}'::jsonb)
        - 'filename' - 'format' - 'source_type' - 'source_sha256'
FROM public.ocr_test_runs AS test_run
WHERE test_run.run_id = test_table.run_id;

ALTER TABLE public.ocr_test_tables
    ALTER COLUMN structured_data SET NOT NULL,
    ALTER COLUMN context SET NOT NULL,
    ALTER COLUMN metadata SET NOT NULL,
    ALTER COLUMN context SET DEFAULT '{}'::jsonb,
    ALTER COLUMN metadata SET DEFAULT '{}'::jsonb,
    DROP COLUMN table_data;
