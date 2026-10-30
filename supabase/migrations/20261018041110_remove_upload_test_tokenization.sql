-- Upload Test ends at parser output; tokenization and embeddings belong downstream.
UPDATE document_preprocessing_test.upload_test_runs
SET runtime_info = runtime_info - ARRAY[
    'embedding_backend',
    'embedding_max_sequence_length',
    'embedding_model',
    'tokenization_status',
    'tokenizer_model'
]::text[]
WHERE runtime_info ?| ARRAY[
    'embedding_backend',
    'embedding_max_sequence_length',
    'embedding_model',
    'tokenization_status',
    'tokenizer_model'
];

DROP TABLE document_preprocessing_test.upload_test_token_chunks;

ALTER TABLE document_preprocessing_test.upload_test_runs
    DROP COLUMN token_bounded_chunk_count,
    DROP COLUMN embedding_status,
    DROP COLUMN embedding_model,
    DROP COLUMN embedding_backend,
    DROP COLUMN embedding_max_sequence_length,
    DROP COLUMN embedding_error;
