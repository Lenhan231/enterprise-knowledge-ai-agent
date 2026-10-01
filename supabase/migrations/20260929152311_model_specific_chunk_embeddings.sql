-- Keep one row per model and canonical processed chunk for embedding benchmarks.
-- The unconstrained vector column intentionally supports models with different
-- dimensions; benchmark evaluation scans exact vectors rather than ANN indexes.
CREATE TABLE public.document_chunk_embeddings (
    document_id text NOT NULL,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    model_name text NOT NULL CHECK (btrim(model_name) <> ''),
    embedding extensions.vector NOT NULL,
    embedding_dimension integer NOT NULL CHECK (embedding_dimension > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, chunk_index, model_name),
    FOREIGN KEY (document_id, chunk_index)
        REFERENCES public.processed_document_chunks(document_id, chunk_index)
        ON DELETE CASCADE,
    CHECK (extensions.vector_dims(embedding) = embedding_dimension)
);

CREATE INDEX document_chunk_embeddings_model_idx
    ON public.document_chunk_embeddings (model_name, document_id);

CREATE TABLE public.document_embedding_runs (
    document_id text NOT NULL REFERENCES public.documents(document_id) ON DELETE CASCADE,
    model_name text NOT NULL CHECK (btrim(model_name) <> ''),
    status text NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    embedded_count integer NOT NULL DEFAULT 0 CHECK (embedded_count >= 0),
    error text,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, model_name),
    CHECK (embedded_count <= chunk_count)
);

-- Preserve existing retrieval vectors for chunks that still match the parsed
-- output. The app's document_chunks table remains the active retrieval index.
INSERT INTO public.document_chunk_embeddings
    (document_id, chunk_index, model_name, embedding, embedding_dimension)
SELECT c.metadata->>'document_id', c.chunk_index,
       c.metadata->>'embedding_model', c.embedding,
       extensions.vector_dims(c.embedding)
FROM public.document_chunks AS c
JOIN public.processed_document_chunks AS p
  ON p.document_id = c.metadata->>'document_id'
 AND p.chunk_index = c.chunk_index
WHERE nullif(btrim(c.metadata->>'embedding_model'), '') IS NOT NULL
ON CONFLICT (document_id, chunk_index, model_name) DO NOTHING;

INSERT INTO public.document_embedding_runs
    (document_id, model_name, status, chunk_count, embedded_count, completed_at)
SELECT document_id, model_name, 'completed', count(*), count(*), now()
FROM public.document_chunk_embeddings
GROUP BY document_id, model_name
ON CONFLICT (document_id, model_name) DO NOTHING;

ALTER TABLE public.document_chunk_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_embedding_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.document_chunk_embeddings FROM anon, authenticated;
REVOKE ALL ON public.document_embedding_runs FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.document_chunk_embeddings TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.document_embedding_runs TO service_role;
