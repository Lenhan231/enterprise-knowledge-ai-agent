ALTER TABLE public.documents
    DROP CONSTRAINT documents_processing_status_check;

ALTER TABLE public.documents
    ADD CONSTRAINT documents_processing_status_check
    CHECK (processing_status IN (
        'uploaded',
        'processing',
        'parsed',
        'chunking',
        'chunked',
        'ready',
        'failed'
    ));
