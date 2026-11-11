-- Keep parser output as a stable handoff; ingestion/embedding state lives on
-- documents and embedding-run records rather than parser-owned chunk rows.
DROP INDEX public.document_parser_chunks_status_idx;
ALTER TABLE public.document_parser_chunks
    DROP COLUMN processing_status,
    DROP COLUMN processing_error;
ALTER TABLE public.document_parser_chunks
    RENAME CONSTRAINT processed_document_chunks_document_id_fkey
    TO document_parser_chunks_document_id_fkey;
