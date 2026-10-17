-- Token counts and embedding identifiers describe a model run, not the
-- extracted chunk. Keep the parser corpus reusable across embedding models.
UPDATE public.processed_document_chunks
SET metadata = metadata - ARRAY['embedding_model', 'token_count']::text[]
WHERE metadata ?| ARRAY['embedding_model', 'token_count'];
