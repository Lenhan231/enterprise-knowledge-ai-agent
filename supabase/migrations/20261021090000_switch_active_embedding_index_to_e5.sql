-- The populated MiniLM index requires matching E5 vectors, not a dimension cast.
-- First run scripts/retrieval/migrate_e5_index.py for the verified existing corpus.
-- Fresh empty installations can adopt E5 dimensions directly.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.document_chunks)
       AND EXISTS (
           SELECT 1 FROM public.document_chunks
           WHERE vector_dims(embedding) <> 768
              OR metadata->>'embedding_model' IS DISTINCT FROM 'intfloat/multilingual-e5-base'
       ) THEN
        RAISE EXCEPTION 'Migrate populated document_chunks with verified E5 vectors before applying this migration';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.document_chunks) THEN
        ALTER TABLE public.document_chunks
            ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768);
    END IF;
END $$;
