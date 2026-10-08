# Chunking

## Active path

The upload and seed-ingestion paths keep parser pages and source metadata, then
split text before embedding. Sentence mode is the default. It groups paragraph
and sentence boundaries up to a character ceiling; fixed mode provides
overlapping character windows for comparison. Current upload chunks target
1,100 characters with no sentence-mode overlap; seed PDFs target 1,200
characters. Fixed-mode sizes and overlap are recorded in each chunk's metadata.

Character length is only a first-stage bound. Before embedding, `TokenCounter`
uses the tokenizer for the selected embedding model and splits any passage that
exceeds `EMBEDDING_MAX_SEQUENCE_LENGTH` (default 512 tokens). Each saved chunk
records its actual token count, strategy, character size, and overlap. This
keeps the stored passage within the model input limit without pretending that
a fixed number of characters always corresponds to the same token count.

PDF pages retain page number, section title, and layout metadata. Structured
table output is persisted for inspection; parser layout and OCR details are
documented in [document processing](document-processing.md). Changing the
strategy or model does not update existing vectors: reprocess and re-embed the
matching passages, then compare retrieval results.

## Configuration and checks

Uploads read `DOCUMENT_CHUNKING_STRATEGY` (`sentence` by default; `fixed` is
the comparison baseline). Seed PDF ingestion accepts `--chunking-strategy`.
The implementation is in `src/core/document_processing/processors/` and
`src/core/document_processing/ingest_documents.py`; the separate experimental
semantic chunker is in `src/core/chunking/semantic_chunker.py`.

Focused regression checks:

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_text_processor_chunking tests.test_document_processor \
  tests.test_pdf_upload_processing tests.test_seed_ingestion -q
```

No chunking strategy is declared best for Commerce yet. Use the active
Commerce retrieval cases and independently review source passages before
changing production defaults. See [retrieval](retrieval-rbac.md) and
[embeddings/tokenization](embeddings-tokenization.md).
