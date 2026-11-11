CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

CREATE TABLE public.documents (
    document_id text PRIMARY KEY,
    domain text NOT NULL,
    title text NOT NULL,
    year_or_version text,
    format text NOT NULL,
    ingestion_format text NOT NULL,
    official_url text NOT NULL,
    verification text NOT NULL,
    rag_value text NOT NULL,
    document_type text,
    fiscal_year text
);
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

CREATE TABLE public.document_chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_name text NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding extensions.vector(384) NOT NULL,
    created_at timestamptz DEFAULT now(),
    UNIQUE (document_name, chunk_index)
);
ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;
CREATE INDEX document_chunks_embedding_hnsw_idx
    ON public.document_chunks USING hnsw (embedding extensions.vector_cosine_ops);
