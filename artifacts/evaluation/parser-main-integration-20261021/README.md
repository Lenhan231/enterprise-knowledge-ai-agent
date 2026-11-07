# Main parser adaptation — scope and checks

2026-10-21. User authorized adapting main parser first, then asked to keep scope narrow and avoid conflicts with teammates. Main re-fetched at7c2162624c161a97c4a5d97b432089cf2ba2f489 (7e3b483 parser/chunker split +7c21626 docs). Main's parser files were ported into the Huy WORKING TREE; no history merge, commit or push has been performed. Huy HEAD remains279be53. No teammate branch, database or stored vectors changed.

## Why the source-control view shows many files

The bulk is the upstream parser refactor already written on main, including format readers, optional pipeline mappers and package documentation. It is not a new parallel parser design. A narrower explicit parser-only patch was used after automatic approval review rejected a broad src patch. Existing source files were checked for overlapping local modifications and682 existing artifact/tokenizer/retrieval files were hashed and verified unchanged before the handoff update. Backups are ignored under .venv/parser-main-integration-20261021/. Main's metadata.md move was completed only after verifying the old file had no local edits.

## Our additions beyond main

Only THREE parser files differ from upstream main; see main-relative-fixes.patch:

1. document_processor.py: top-level element_type is honored when normalizing element metadata, and table layout type is consistent. This preserves explicit table references instead of treating them as text and appending tables at the end.
2. chunking/processor.py: only an actual heading-only chunk can be skipped. A first line matching the section title no longer causes the attached body/facts to disappear.
3. pipelines/built_in/scanned/pdf_ocr.py: use the existing table OCR defaults when collecting metadata with OCR fallback disabled; native parsing no longer fails because OCR settings were not initialized.

No new strategies, dependencies, embedding/reranking methods or parser engines were added. Upload and Upload Test explicitly call DocumentProcessor then ChunkingProcessor, as main's architecture requires. Upload Test's existing embedding_status/embedding_error response fields were preserved rather than copying unrelated API field removals. Huy's translated_hybrid request/response support was preserved. Two direct extraction benchmark callers were updated to the canonical imports and explicit chunking step. Tokenization implementation and ACL logic were not changed.

## Before and after

- DOCX [prose before][table][prose after]: main regressed to joined before/after text followed by the table. Adapted pipeline keeps all three chunks in source order and retains document, paragraph, section and role metadata.
- Markdown heading with body spanning chunks: before could silently discard the first fact; now all body text remains.
- Native PDF with ocr_fallback=False: before could raise a KeyError for tesseract_table_psm; now parses without invoking OCR.
- Upload: parse elements/tables -> shared parser chunks -> independently persisted parser chunks/tables -> existing Huy bounded token passages and vectors. Parser-handoff remains a parser-only path. No embedding/index rebuild occurred.

## Validation

21 targeted unittest checks passed:

    PYTHONPATH=src:tests HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m unittest test_parser_chunking_integration test_embedding_chunker test_token_counter test_evidence_metrics

The8 new integration checks cover DOCX table order and stage separation, heading/body retention, top-level table_ref/table_data from a mocked optional pipeline, XLSX/CSV row/sheet metadata, native PDF page and mocked image OCR metadata, exact token/source-span coverage and ACL retention, actual production upload flow with storage/database/embedding mocked, and Upload Test's output/response contract. No inference, new weights, external APIs, live DB writes or upload/storage mutations were performed by these tests. Both migrated processing scripts pass --help; modified caller Python syntax and git diff --check pass.

The full legacy suite was not certified: existing tests still reference pre-existing removed core.document_processing.processors/core.chunking paths and old API/repository behavior. They were not rewritten wholesale, to keep this task scoped. Optional Docling/MinerU/Paddle engines were not downloaded or executed; the shared table contract was checked through a mocked optional pipeline. PDF native extraction still has its existing flat-text/separately extracted-table representation; this work does not redesign PDF duplicate-table handling.

## Collaboration and publication

Only the local Huy workspace changed. A future merge can conflict if a teammate changes the same three shared parser files; absence of remote impact does not guarantee zero merge conflicts. Keep upstream synchronization and our focused fixes distinguishable during publication; do not push the current collection of benchmark artifacts and parser work blindly as one unrelated change. Record actual main ancestry when preparing the eventual integration commit, rather than treating this worktree port as an already completed Git merge.

The frozen fresh-reviewed-v1 labels/corpus, baseline results and translated-hybrid results remain intact; current21 tests do not constitute a new retrieval benchmark on newly parsed documents. A new parser output snapshot would require its own provenance/vector validation before a new benchmark. The application translated-hybrid + BGE reranker integration is still NEXT, not part of this parser task.
