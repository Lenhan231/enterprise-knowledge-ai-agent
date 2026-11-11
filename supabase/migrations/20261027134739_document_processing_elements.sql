CREATE TABLE public.document_processing_elements (
    document_id text NOT NULL
        REFERENCES public.documents (document_id) ON DELETE CASCADE,
    element_index integer NOT NULL CHECK (element_index >= 0),
    element_type text NOT NULL CHECK (element_type IN (
        'title', 'title_table', 'section_header', 'text', 'table',
        'figure', 'seal', 'page_header', 'page_footer'
    )),
    text text,
    page_number integer,
    bbox jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (document_id, element_index)
);

COMMENT ON TABLE public.document_processing_elements IS
    'One row per normalized parser element before chunking or embeddings.';

ALTER TABLE public.document_processing_elements ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.document_processing_elements FROM anon, authenticated;
GRANT ALL ON TABLE public.document_processing_elements TO service_role;
