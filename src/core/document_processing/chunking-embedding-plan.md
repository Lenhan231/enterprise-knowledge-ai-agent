# OCR, chunking, and embedding: current flow

## Data path

```text
PDF → DocumentProcessor/parser → parser chunks + table rows
    → save parser output → build token-bounded embedding chunks
    → EmbeddingService → save vectors for retrieval
```

Production upload, embedding retry, and Upload Test share
`build_embedding_chunks()` so they use the same tokenizer limit and final
chunk metadata. Upload and retry write production repositories; Upload Test
writes `upload_test_*` tables and never creates a searchable production document.
Upload Test stores both parser chunks and final embedding chunks so their
boundaries can be compared directly.

## Remaining work

Production upload uses PyMuPDF/native text with Tesseract fallback by default;
Upload Test can select PyMuPDF/Tesseract, PP-StructureV3, or MinerU per run.
Keep the test override. Consider a shared production parser setting only when
production parser selection itself becomes configurable.

## Ownership

| Stage | Owner |
| --- | --- |
| Shared native readers for files, layout, tables, and text | `src/core/document_processing/readers/` |
| Save parser output and orchestrate upload/retry | `src/app/main.py`, `ParserChunksRepository` |
| Split and count tokenizer tokens | `src/core/tokenization/token_counter.py` |
| Build final bounded chunks and metadata | `src/core/tokenization/embedding_chunker.py` |
| Select model and create vectors | `src/core/embeddings/embedding_service.py` |
| Save retrieval vectors | `DocumentChunkRepository` |

## Checks

- Upload and retry turn the same parser text into the same bounded chunks and metadata.
- Upload Test records parser chunks, token-bounded chunks, vectors, and structured table rows in isolated tables.
- No Upload Test document or vector is visible to production retrieval.
