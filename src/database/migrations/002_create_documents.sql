create table documents (
    document_id text primary key,
    domain text not null,
    title text not null,
    year_or_version text,
    format text not null,
    ingestion_format text not null,
    official_url text not null,
    verification text not null,
    rag_value text not null,
    document_type text,
    fiscal_year text
);

alter table documents enable row level security;