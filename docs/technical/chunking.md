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
`src/core/document_processing/chunking/router.py` only routes character-based splitting to
the fixed and sentence-aware implementations in
`src/core/document_processing/chunking/strategies/`. Shared size/overlap settings live in
`src/core/document_processing/chunking/config.py`; `chunk_builder.py` attaches parser chunk metadata.
Embedding-token splitting is implemented in `src/core/tokenization/token_counter.py`.
The embedding-based semantic strategy is in
`src/core/document_processing/chunking/strategies/semantic.py`; seed ingestion currently routes it
for HTML documents. PDF and upload chunking support the character-based
`fixed` and `sentence` strategies.

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
