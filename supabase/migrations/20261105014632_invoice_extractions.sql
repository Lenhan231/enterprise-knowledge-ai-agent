CREATE TABLE public.invoice_extractions (
    invoice_id text PRIMARY KEY,
    source_filename text NOT NULL,
    source_format text NOT NULL CHECK (source_format IN ('PDF', 'PNG', 'JPG', 'JPEG', 'TIF', 'TIFF')),
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    storage_path text NOT NULL,
    uploaded_by text NOT NULL,
    processing_status text NOT NULL DEFAULT 'processing'
        CHECK (processing_status IN ('processing', 'review_required', 'failed')),
    schema_version text NOT NULL DEFAULT 'invoice.v1',
    invoice_data jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(invoice_data) = 'object'),
    ocr_elements jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(ocr_elements) = 'array'),
    ocr_tables jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(ocr_tables) = 'array'),
    extraction_model text,
    extraction_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(extraction_metadata) = 'object'),
    review_required boolean NOT NULL DEFAULT true,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.invoice_extractions IS
    'Invoice uploads and OCR-to-JSON drafts, kept separate from the searchable documents corpus.';

ALTER TABLE public.invoice_extractions ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON public.invoice_extractions FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.invoice_extractions TO service_role;

CREATE INDEX invoice_extractions_uploaded_by_created_at_idx
    ON public.invoice_extractions (uploaded_by, created_at DESC);

CREATE INDEX invoice_extractions_status_created_at_idx
    ON public.invoice_extractions (processing_status, created_at DESC);
