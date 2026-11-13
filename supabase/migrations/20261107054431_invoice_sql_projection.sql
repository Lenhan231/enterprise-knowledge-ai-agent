-- Raw extractions remain private; only explicitly reviewed data is published.
-- Requires public.invoice_extractions, owned by the existing extraction system.
alter table public.invoice_extractions
    drop constraint invoice_extractions_processing_status_check;
alter table public.invoice_extractions
    add constraint invoice_extractions_processing_status_check
    check (processing_status in ('processing', 'review_required', 'failed', 'approved'));
alter table public.invoice_extractions
    add constraint invoice_extractions_approval_check
    check (processing_status <> 'approved' or review_required = false);

create table commerce.invoices (
    invoice_id text primary key references public.invoice_extractions(invoice_id) on delete cascade,
    source_filename text not null,
    source_sha256 text not null unique,
    invoice_no text,
    invoice_date date,
    buyer text,
    seller text,
    subtotal numeric check (subtotal >= 0 and subtotal < 'Infinity'::numeric),
    tax_amount numeric check (tax_amount >= 0 and tax_amount < 'Infinity'::numeric),
    total_amount numeric check (total_amount >= 0 and total_amount < 'Infinity'::numeric),
    currency text check (currency ~ '^[A-Z]{3}$')
);
create index invoices_invoice_date_idx on commerce.invoices(invoice_date);

create table commerce.invoice_items (
    invoice_id text not null references commerce.invoices(invoice_id) on delete cascade,
    line_no integer not null check (line_no > 0),
    description text,
    unit text,
    quantity numeric check (quantity >= 0 and quantity < 'Infinity'::numeric),
    unit_price numeric check (unit_price >= 0 and unit_price < 'Infinity'::numeric),
    amount numeric check (amount >= 0 and amount < 'Infinity'::numeric),
    primary key (invoice_id, line_no)
);

alter table commerce.invoices enable row level security;
alter table commerce.invoice_items enable row level security;
revoke all on commerce.invoices, commerce.invoice_items from public, anon, authenticated;
grant all on commerce.invoices, commerce.invoice_items to service_role;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'commerce_analytics_reader') then
        create role commerce_analytics_reader nologin
            nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls;
    end if;
end
$$;
grant usage on schema commerce to commerce_analytics_reader;
grant select (invoice_id, source_filename, invoice_no, invoice_date, buyer, seller,
              subtotal, tax_amount, total_amount, currency)
    on commerce.invoices to commerce_analytics_reader;
grant select (invoice_id, line_no, description, unit, quantity, unit_price, amount)
    on commerce.invoice_items to commerce_analytics_reader;

-- shortcut: all analytics:read users see all published invoices; replace with scoped policies when RBAC exists.
create policy invoice_reader_temporary_all on commerce.invoices
    for select to commerce_analytics_reader using (true);
create policy invoice_item_reader_temporary_all on commerce.invoice_items
    for select to commerce_analytics_reader using (true);
comment on policy invoice_reader_temporary_all on commerce.invoices is
    'TEMPORARY: shared read access for every analytics:read user until invoice RBAC is established.';
comment on policy invoice_item_reader_temporary_all on commerce.invoice_items is
    'TEMPORARY: shared read access for every analytics:read user until invoice RBAC is established.';

-- Existing deployment uses a NOINHERIT commerce_reader login; inherit this read-only membership explicitly.
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'commerce_reader') then
        grant commerce_analytics_reader to commerce_reader with inherit true;
    end if;
end
$$;

-- Reprocessing or edits withdraw the approved snapshot until it is published again.
create function commerce.invalidate_invoice_projection() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    delete from commerce.invoices where invoice_id = old.invoice_id;
    return new;
end
$$;
revoke all on function commerce.invalidate_invoice_projection() from public, anon, authenticated;
create trigger invalidate_invoice_projection
after update of invoice_data, source_filename, source_sha256, schema_version,
                processing_status, review_required on public.invoice_extractions
for each row execute function commerce.invalidate_invoice_projection();
