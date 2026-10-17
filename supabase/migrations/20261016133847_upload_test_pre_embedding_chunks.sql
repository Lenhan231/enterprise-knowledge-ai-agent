-- Upload Test stores the chunks that would be sent to embedding, without vectors.
ALTER TABLE public.upload_test_runs
    RENAME COLUMN embedding_chunk_count TO token_bounded_chunk_count;

ALTER TABLE public.upload_test_embedding_chunks
    RENAME TO upload_test_token_chunks;
ALTER INDEX public.upload_test_embedding_chunks_page_idx
    RENAME TO upload_test_token_chunks_page_idx;
ALTER TABLE public.upload_test_token_chunks
    ALTER COLUMN embedding DROP NOT NULL;
