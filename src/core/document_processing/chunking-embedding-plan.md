# OCR, chunking, and embedding: short plan

## The current flow

```text
PDF → DocumentProcessor/parser → parser chunks + table rows
    → save parser output → split to embedding token limit
    → EmbeddingService → save vectors for retrieval
```

Production upload and OCR Lab already call the same `DocumentProcessor` and
parser code. They differ in parser configuration and destination: production
continues to embedding/indexing; OCR Lab saves an isolated run for inspection.
The Lab should stay isolated.

## Do these three things

1. **One parser setting.** Add `DOCUMENT_PARSER_ENGINE` for production and make
   OCR Lab use that as its default. Keep the Lab's per-run override for testing.
   Leave PyMuPDF/Tesseract as the default; MinerU stays opt-in until reviewed.

2. **One common metadata contract.** Keep shared fields such as `filename`,
   `format`, `page_number`, and `chunk_index` consistent. `parser`, `bbox`, and
   MinerU tier are provenance and can differ by engine. Keep table rows as
   structured data alongside readable chunk text. `ChunkMetadata` in
   `src/core/models/document.py` currently serves seed ingestion only; do not
   symlink it into processors. Update the shared type only if code needs it.

3. **One token-splitting path.** Production upload and embedding retry both use
   `TokenCounter` but duplicate metadata handling. Extract that bounded-text
   preparation once and use it in both paths. Keep parser chunks unchanged for
   review/retry. Consider seed ingestion after upload and retry agree.

## Ownership

| Stage | Owner |
| --- | --- |
| Parse files, layout, tables, character chunks | `src/core/document_processing/processors/` |
| Save parser output and orchestrate upload/retry | `src/app/main.py`, `ProcessedChunksRepository` |
| Enforce embedding model token limit | `src/core/tokenization/token_counter.py` |
| Select/load model and create vectors | `src/core/embeddings/embedding_service.py` |
| Save retrieval vectors | `DocumentChunkRepository` |

## Completion checks

- Production and OCR Lab default to the same configured parser; Lab overrides
  affect only that test run.
- Upload and retry turn the same saved parser chunks into the same bounded
  embedding inputs and preserve their source metadata.
- Every embedding input respects the configured model token limit. OCR Lab
  remains parser-only and does not create vectors.

Start with item 1. Do not change the production parser default or move the model
file as part of this cleanup.
