create schema if not exists extensions;
create extension if not exists vector with schema extensions;

create table document_chunks (
    id bigint generated always as identity primary key,
    document_name text not null,
    chunk_index integer not null,
    content text not null,
    metadata jsonb default '{}'::jsonb,
    embedding extensions.vector(384) not null,
    created_at timestamptz default now(),
    unique (document_name, chunk_index)
);

create index if not exists document_chunks_embedding_hnsw_idx
on document_chunks using hnsw (embedding extensions.vector_cosine_ops);
