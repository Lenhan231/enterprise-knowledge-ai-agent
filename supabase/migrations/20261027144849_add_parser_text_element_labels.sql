ALTER TABLE public.document_processing_text_elements
    DROP CONSTRAINT document_processing_text_elements_element_type_check;

ALTER TABLE public.document_processing_text_elements
    ADD CONSTRAINT document_processing_text_elements_element_type_check
    CHECK (element_type IN (
        'title', 'title_table', 'section_header', 'text',
        'footnote', 'document_index', 'formula',
        'page_header', 'page_footer'
    ));
