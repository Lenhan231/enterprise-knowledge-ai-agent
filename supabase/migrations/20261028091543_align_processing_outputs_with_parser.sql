ALTER TABLE public.document_processing_outputs
    RENAME COLUMN text_elements TO elements;

ALTER TABLE public.document_processing_outputs
    RENAME COLUMN structured_tables TO tables;

-- Older rows split figures and omitted table markers. Preserve their payloads;
-- their original cross-type order cannot be recovered from the old columns.
UPDATE public.document_processing_outputs AS output
SET elements = COALESCE(output.elements, '[]'::jsonb)
    || COALESCE(output.figures, '[]'::jsonb)
    || COALESCE((
        SELECT jsonb_agg(
            jsonb_build_object(
                'table_ref', table_item.ordinality - 1,
                'metadata', COALESCE(table_item.value->'metadata', '{}'::jsonb)
                    || jsonb_build_object(
                        'element_type', 'table',
                        'layout_type', 'table',
                        'table_index', COALESCE(
                            table_item.value->'table_index',
                            to_jsonb(table_item.ordinality - 1)
                        )
                    )
            ) ORDER BY table_item.ordinality
        )
        FROM jsonb_array_elements(output.tables)
             WITH ORDINALITY AS table_item(value, ordinality)
    ), '[]'::jsonb);

ALTER TABLE public.document_processing_outputs
    ALTER COLUMN elements SET DEFAULT '[]'::jsonb;

ALTER TABLE public.document_processing_outputs
    DROP COLUMN figures;
