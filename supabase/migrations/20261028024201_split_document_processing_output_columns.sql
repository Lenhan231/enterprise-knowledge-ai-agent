ALTER TABLE public.document_processing_outputs
    ADD COLUMN figures jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(figures) = 'array');

UPDATE public.document_processing_outputs AS output
SET figures = COALESCE((
        SELECT jsonb_agg(element.value - 'text' ORDER BY element.ordinality)
        FROM jsonb_array_elements(COALESCE(output.elements, '[]'::jsonb))
             WITH ORDINALITY AS element(value, ordinality)
        WHERE COALESCE(
            element.value->'metadata'->>'element_type',
            element.value->>'element_type',
            element.value->'metadata'->>'layout_type'
        ) IN ('figure', 'seal')
    ), '[]'::jsonb),
    elements = COALESCE((
        SELECT jsonb_agg(element.value ORDER BY element.ordinality)
        FROM jsonb_array_elements(COALESCE(output.elements, '[]'::jsonb))
             WITH ORDINALITY AS element(value, ordinality)
        WHERE COALESCE(
            element.value->'metadata'->>'element_type',
            element.value->>'element_type',
            element.value->'metadata'->>'layout_type'
        ) NOT IN ('figure', 'seal', 'table')
    ), '[]'::jsonb);

ALTER TABLE public.document_processing_outputs
    RENAME COLUMN elements TO text_elements;
