-- Apply separately after approval. Verify vector is in extensions, no duplicate
-- document/chunk keys or SQL NULL metadata, and any existing named index has
-- the intended definition: IF NOT EXISTS only checks names.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

ALTER TABLE public.document_chunks
    ALTER COLUMN metadata SET DEFAULT '{}'::jsonb,
    ALTER COLUMN metadata SET NOT NULL;

-- Same name as the constraint-generated index in migration 001.
CREATE UNIQUE INDEX IF NOT EXISTS document_chunks_document_name_chunk_index_key
    ON public.document_chunks (document_name, chunk_index);

CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw_idx
    ON public.document_chunks USING hnsw (embedding extensions.vector_cosine_ops);

COMMIT;
