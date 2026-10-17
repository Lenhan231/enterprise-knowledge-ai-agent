-- Keep document processing state separate from whether its passages are searchable.
ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS knowledge_base_active boolean NOT NULL DEFAULT true;
