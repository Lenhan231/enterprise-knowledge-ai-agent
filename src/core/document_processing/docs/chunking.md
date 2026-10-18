# Chunking

## Active path

Upload keeps parser elements and source metadata, then splits text downstream of
parsing. Sentence mode is the default. It groups paragraph
and sentence boundaries up to a character ceiling; fixed mode provides
overlapping character windows for comparison. Current upload chunks target
1,100 characters with no sentence-mode overlap. Fixed-mode sizes and overlap
are recorded in each chunk's metadata.

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
the comparison baseline).
`src/core/document_processing/chunking/router.py` routes text and structured tables.
Text chunking lives in `src/core/document_processing/chunking/text/`, where its router selects
fixed or sentence-aware splitting from `text/strategies/`. Table chunking lives in
`src/core/document_processing/chunking/table/chunker.py` and groups whole rows while repeating
the table title and headers. Shared size/overlap settings live in
`src/core/document_processing/chunking/config.py`.
Embedding-token splitting is implemented in `src/core/tokenization/token_counter.py`.
Upload currently uses the character-based `fixed` and `sentence` strategies.

Focused regression checks:

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_text_processor_chunking tests.test_document_processor \
  tests.test_pdf_upload_processing -q
```

No chunking strategy is declared best for Commerce yet. Use the active
Commerce retrieval cases and independently review source passages before
changing production defaults. See [retrieval](../../../../docs/technical/retrieval-rbac.md) and
[embeddings/tokenization](../../../../docs/technical/embeddings-tokenization.md).
