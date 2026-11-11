alter table public.invoice_extractions
    drop constraint invoice_extractions_processing_status_check;
alter table public.invoice_extractions
    add constraint invoice_extractions_processing_status_check
    check (processing_status in ('processing', 'review_required', 'failed', 'approved', 'rejected'));
alter table public.invoice_extractions
    add constraint invoice_extractions_rejection_check
    check (processing_status <> 'rejected' or review_required = false);
