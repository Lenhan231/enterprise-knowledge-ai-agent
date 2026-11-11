-- Upload Test stores normalized parser elements; chunking belongs to downstream owners.
ALTER TABLE document_preprocessing_test.upload_test_parser_chunks
    RENAME TO upload_test_elements;
ALTER TABLE document_preprocessing_test.upload_test_elements
    RENAME COLUMN chunk_index TO element_index;
ALTER INDEX document_preprocessing_test.upload_test_parser_chunks_page_idx
    RENAME TO upload_test_elements_page_idx;
ALTER TABLE document_preprocessing_test.upload_test_runs
    RENAME COLUMN chunk_count TO element_count;
