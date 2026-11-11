-- Name the persisted parser/chunking output by its responsibility and owner.
-- PostgreSQL updates dependent foreign keys when the referenced table is renamed.
ALTER TABLE public.processed_document_chunks RENAME TO document_parser_chunks;
ALTER INDEX public.processed_document_chunks_status_idx RENAME TO document_parser_chunks_status_idx;
