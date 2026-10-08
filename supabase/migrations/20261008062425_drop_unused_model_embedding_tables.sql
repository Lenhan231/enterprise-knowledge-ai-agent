-- The model-specific embedding experiment tables were never wired into the
-- application or benchmark tools and contain no data. Production retrieval
-- currently stores its active vector in public.document_chunks.embedding.
-- Keep the default RESTRICT behavior so unexpected dependencies stop the drop.
DROP TABLE IF EXISTS public.document_chunk_embeddings;
DROP TABLE IF EXISTS public.document_embedding_runs;
