# Review of main after freezing fresh-reviewed-v1

Reviewed 2026-10-21. main: 7c2162624c161a97c4a5d97b432089cf2ba2f489. Huy: 279be53005b61b692e2cbcf08208fb21fd177b9b. Main contains two commits absent from Huy: 7e3b483 (separate parsing from document chunking) and 7c21626 (documentation ownership alignment). Compared against 298be61, their previous main commit already present in Huy. Fetched only: no merge, checkout switch, document upload or re-index.

## What changed

Previously DocumentProcessor.process returned chunks and tables. It now returns ordered elements and structured tables. The caller then invokes ChunkingProcessor(config).process(parsed) to obtain chunks. Both production upload (src/app/main.py) and Upload Test (src/app/upload_test.py) were updated. Native readers and optional OCR pipeline mappers return blocks/table references rather than independently splitting them. ChunkingProcessor centrally groups text, builds row-aware table chunks, orders chunks and folds short fragments. Docs now place the package boundary at parser chunks; tokenizer, embeddings, persistence/indexing remain downstream. The unused semantic strategy file is removed; the router still supports sentence/fixed. No new tests are included in these two commits.

## Confirmed regression: table references lose source ordering

DocumentProcessor determines element type only from metadata.element_type/layout_type. Several readers, including DOCX, emit element_type='table' at the element's TOP LEVEL, with table_ref and metadata containing table_index but not the nested type. The normalized metadata therefore says 'text'. ChunkingProcessor also checks only nested metadata and fails to register those references. _table_entries falls back to appending unreferenced tables after all elements. _text_groups fails to flush at the misclassified table; the short-text merge can also join prose from opposite sides of that table.

Verified with exact old/new source archives in isolated /tmp directories and the existing virtualenv. A synthetic DOCX with [Before table evidence.] -> [one-column Field/Table evidence table] -> [After table evidence.] produced:

- 298be61: before-text, table, after-text; three chunks in source order.
- 7c21626: before+after merged into one text chunk, followed by the table; two chunks. The merged text retains paragraph_index=2 although it also contains paragraph0 text. The raw table element says table, its normalized metadata says text.

The table content is still emitted; this is an ordering/provenance regression, not complete table loss. CSV is a passing control: its reader supplies nested table metadata, so parsing/chunking produced the expected row chunk and document_id. Other adapters using the same top-level-only convention are exposed to the same contract mismatch; no full OCR engine execution was performed.

Effect on our work: conservative predecessor reranking assumes chunk order/source-parser order describes actual adjacency. After reprocessing affected documents, the table may become an unrelated neighbor and paragraph metadata can describe only part of merged text. Fix the shared normalization contract before adopting this processing behavior for new snapshots. Recommended fix: use the top-level element_type when normalizing metadata, preserving table_ref; add a before/table/after integration check. No fix was applied as part of this read-only main review.

## Carried-over issue, not introduced by these commits

A Markdown section starting '# Policy', then 'UNIQUE_FIRST_FACT.', followed by enough other sentences to split into multiple chunks loses the first fact. The short-chunk cleanup skips any chunk whose first line matches the heading, without verifying the rest contains no body. Reproduced on BOTH 298be61 and new main; do not attribute it as a new regression. The new ChunkingProcessor carries the issue forward. Keep it on the processing cleanup list; our frozen inputs were not rebuilt.

## Effect on the frozen experiments

- fresh-reviewed-v1 and historical benchmark snapshots are unchanged. They read frozen parser/indexed JSONL and saved vectors, not live DocumentProcessor calls. Existing rankings and the new label freeze remain reproducible under their recorded inputs.
- The two main commits do not modify embedding_service.py, tokenizer code, production retrieval methods, our evidence scorer, benchmark labels, vectors or database migrations. Fetching commits does not modify stored database data.
- Any code expecting DocumentProcessor.process(...)["chunks"] must explicitly add ChunkingProcessor. The upload routes have been adapted; direct scripts/test callers should be checked before use. Several legacy processing tests/scripts still import the removed processors.document_processor path; this stale import is already present in 298be61, not new in these commits.
- If we later rebuild the corpus using main, chunk counts, texts, indexes, section assignment and source order may differ. Create a new corpus/version and rebuild the corresponding vectors and evidence mappings; never reuse old vector row alignment or chunk IDs against that new output.
- Keep this freeze and next reranker comparison on the existing 1,063 frozen passages. Integrate processing changes separately after fixing source ordering and validating representative Office/PDF tables.

## Validation limits

processing-checks.json records source commit IDs and full outputs for DOCX/CSV/Markdown fixtures. Smoke checks used local source archives, no services, network APIs or downloads. Existing main processing unit tests were not run as a suite; some use a pre-existing stale import. No OCR/model inference, production upload, database mutation or deployment was attempted.
