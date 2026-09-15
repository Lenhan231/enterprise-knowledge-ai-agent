create extension if not exists vector
with schema extensions;

create table document_chunks (
    id bigint generated always as identity primary key,
    document_name text not null,
    chunk_index integer not null,
    content text not null,
    metadata jsonb default '{}'::jsonb,
    embedding extensions.vector(384) not null,
    created_at timestamptz default now()
);