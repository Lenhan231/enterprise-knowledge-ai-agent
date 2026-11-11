CREATE TABLE public.document_processing_text_elements (
    document_id text NOT NULL
        REFERENCES public.documents (document_id) ON DELETE CASCADE,
    element_index integer NOT NULL CHECK (element_index >= 0),
    element_type text NOT NULL CHECK (element_type IN (
        'title', 'title_table', 'section_header', 'text',
        'page_header', 'page_footer'
    )),
    text text,
    page_number integer,
    bbox jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (document_id, element_index)
);

CREATE TABLE public.document_processing_figures (
    document_id text NOT NULL
        REFERENCES public.documents (document_id) ON DELETE CASCADE,
    element_index integer NOT NULL CHECK (element_index >= 0),
    element_type text NOT NULL CHECK (element_type IN ('figure', 'seal')),
    text text,
    page_number integer,
    bbox jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (document_id, element_index)
);

CREATE TABLE public.document_processing_table_elements (
    document_id text NOT NULL
        REFERENCES public.documents (document_id) ON DELETE CASCADE,
    element_index integer NOT NULL CHECK (element_index >= 0),
    element_type text NOT NULL CHECK (element_type = 'table'),
    text text,
    page_number integer,
    bbox jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (document_id, element_index)
);

COMMENT ON TABLE public.document_processing_text_elements IS
    'Parser text and layout labels before chunking or embeddings.';
COMMENT ON TABLE public.document_processing_figures IS
    'Parser figure and seal regions before downstream processing.';
COMMENT ON TABLE public.document_processing_table_elements IS
    'Parser table regions and geometry; extracted_tables and extracted_records store structured table content.';

ALTER TABLE public.document_processing_text_elements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_processing_figures ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_processing_table_elements ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.document_processing_text_elements,
    public.document_processing_figures,
    public.document_processing_table_elements FROM anon, authenticated;
GRANT ALL ON TABLE public.document_processing_text_elements,
    public.document_processing_figures,
    public.document_processing_table_elements TO service_role;

INSERT INTO public.document_processing_text_elements
    (document_id, element_index, element_type, text, page_number, bbox, metadata)
SELECT document_id, element_index, element_type, text, page_number, bbox, metadata
FROM public.document_processing_elements
WHERE element_type NOT IN ('figure', 'seal', 'table');

INSERT INTO public.document_processing_figures
    (document_id, element_index, element_type, text, page_number, bbox, metadata)
SELECT document_id, element_index, element_type, text, page_number, bbox, metadata
FROM public.document_processing_elements
WHERE element_type IN ('figure', 'seal');

INSERT INTO public.document_processing_table_elements
    (document_id, element_index, element_type, text, page_number, bbox, metadata)
SELECT document_id, element_index, element_type, text, page_number, bbox, metadata
FROM public.document_processing_elements
WHERE element_type = 'table';

DROP TABLE public.document_processing_elements;
