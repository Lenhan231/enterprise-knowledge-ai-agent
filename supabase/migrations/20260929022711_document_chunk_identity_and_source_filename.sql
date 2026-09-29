-- Source labels may repeat across uploads; stable document identity lives in metadata.
CREATE UNIQUE INDEX IF NOT EXISTS document_chunks_document_id_chunk_index_key
    ON public.document_chunks ((metadata->>'document_id'), chunk_index);

UPDATE public.document_chunks AS chunks
SET document_name = regexp_replace(documents.storage_path, '^.*/', '')
FROM public.documents AS documents
WHERE documents.document_id = chunks.metadata->>'document_id'
  AND documents.source_type = 'user_upload'
  AND chunks.document_name = documents.document_id
  AND documents.storage_path IS NOT NULL;

DROP INDEX IF EXISTS public.document_chunks_document_name_chunk_index_key;
