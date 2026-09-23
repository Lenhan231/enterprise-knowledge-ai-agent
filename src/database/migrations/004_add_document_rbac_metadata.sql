alter table public.documents
    add column if not exists company text,
    add column if not exists source_type text,
    add column if not exists allowed_roles text[] not null default '{}'::text[],
    add column if not exists access_scope text;
