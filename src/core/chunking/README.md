# Parser chunking

`ChunkingProcessor` converts normalized parser elements and structured tables
into the parser chunks that Upload Test displays and production persists in
`document_parser_chunks`. It does not tokenize or embed them.

## Text chunks

Sentence mode is the default. It groups paragraph and sentence boundaries up
to the configured character ceiling. Fixed mode makes overlapping character
windows for comparison. The current defaults are 1,100 characters and 120
characters of overlap. Sentence boundaries normally have no overlap; its
oversized-sentence fallback uses the configured overlap even though the
current sentence-mode metadata records zero. Size, strategy, and
actual character count are recorded in chunk metadata.

## Table chunks

Tables stay structured in parser output and also produce row-aware text chunks.
Each fragment repeats the section context, table title, and column headers;
rows remain whole. The metadata records table identity and row ranges so a
chunk can be traced to its source table.

## Code path and configuration

- `chunking/processor.py` orders text and table chunks from parser output.
- `chunking/text/` contains the fixed and sentence strategies.
- `chunking/table/chunker.py` groups structured rows into chunks.
- `chunking/config.py` owns shared character size, overlap, and strategy.
- Uploads read `DOCUMENT_CHUNKING_STRATEGY` (`sentence` by default; `fixed` is
  the comparison option).

The parser-chunk output is the end of this module's responsibility. Model-
specific token limits and retrieval indexing are handled downstream.

## Chunking worker service

The `chunking` Compose service polls documents whose `processing_status` is
`parsed` and which have a row in `document_processing_outputs`. It reuses the
same stored-output mapper as the dry-run script and runs `ChunkingProcessor`.
It writes only `document_parser_chunks` and the document processing status.

```text
parsed + stored parser output
  -> transaction locks document and parser output (FOR UPDATE SKIP LOCKED)
  -> map text/tables, chunk, replace document_parser_chunks
  -> commit chunks + status chunked together

processing/chunk-write error -> rollback replacement, keep old chunks, status failed
worker interruption/connection loss before commit -> rollback, document remains parsed
```

The claim is the database row lock, held until commit; there is no separately
committed `chunking` status or lease to expire. Other workers skip the locked
document and may process another one. The parser-output row is locked too,
preventing a concurrent source replacement midway through processing.

Apply `supabase/migrations/20261028090548_add_chunking_document_statuses.sql`
and `supabase/migrations/20261028091543_align_processing_outputs_with_parser.sql`
through the normal migration process **before starting the service**. The
worker checks the canonical `elements`/`tables` columns and that the status constraint allows `chunked` before claiming
documents. No migration is applied automatically.

Start from the repository root:

```sh
docker compose up -d --build chunking
docker compose logs -f chunking
```

For local development with `.env` and the migration already applied:

```sh
PYTHONPATH=src .venv/bin/python -m core.chunking.worker --once
```

`--once` processes at most one document, returns 1 on processing/database
failure, and returns 0 on success or an empty queue. Without it the worker
polls continuously; `CHUNKING_POLL_INTERVAL_SECONDS` defaults to 5. It uses
`DATABASE_URL` and the existing `DOCUMENT_CHUNKING_STRATEGY` setting. SIGTERM
stops polling and lets the current transaction finish; forced termination
rolls back uncommitted work. Failures are logged with document ID, marked
`failed`, and are not automatically retried. A reviewed retry must explicitly
return the document to `parsed`.

No tokenization, model download, embedding, structured analytics-store write,
or retrieval activation is performed. Company, allowed roles, and
`knowledge_base_active` are not changed. `chunked` is an intermediate handoff,
not `ready`; a separate embedding stage is still needed. Documents without
parser output are skipped. Existing inline upload chunking is unchanged, so
parser-handoff uploads can be re-chunked by this worker after becoming `parsed`.

Figures are retained in parser output but excluded from chunking. Missing
context and approximate page/bbox ordering are logged rather than silently
repaired. Known OCR and table-boundary quality issues remain.

The Docker image contains chunking plus the two database helpers it needs,
with psycopg/python-dotenv and no model dependencies or exposed HTTP port.

Worker integration tests create and drop a unique database on **local**
PostgreSQL; the supplied role must have CREATEDB permission:

```sh
CHUNKING_TEST_DATABASE_URL='host=localhost dbname=postgres user=TEST_ROLE' \
  .venv/bin/python -m unittest discover -s tests -p test_chunking_worker.py -v
```

These tests cover concurrent claims, source locking, savepoint rollback,
interruption recovery, status migration checks, and repeated polls. They do
not use the project's `DATABASE_URL` or Supabase.

## Preview a stored parser output

From the repository root, with `DATABASE_URL` in `.env` and the pinned E5
tokenizer already cached locally:

```sh
.venv/bin/python scripts/chunking/preview_processing_output.py DOCUMENT_ID \
  --output artifacts/local/chunking-preview/document.json
```

This command always performs a read-only dry run. It writes local JSON and
Markdown reports, never database rows, model embeddings, or document status.
It does not download models/tokenizers. Reports contain source document content;
the default preview directory above is excluded from Git. Existing files are
not overwritten.

The JSON retains the full stored parser output, parser chunks, token-bounded
passages, and warnings. Canonical `elements`/`tables` inputs retain the parser's
stored element order, including table references and section context. Legacy
snapshots with split text/table arrays use a complete unique `source_order`
when available, otherwise approximate page/bbox order. Coordinates cannot
guarantee reading order in multi-column layouts; migration of older rows
cannot recover their original cross-type order. Figures
remain in the source output and are excluded from the embedding preview.

Each chunk carries `source_elements` references into the original element/table
arrays. References cover its contributing parser group, not exact character
spans for each token fragment. Existing chunking boundaries are unchanged.
Roles come from the document record; empty roles stay empty (deny access).
Missing company/roles and inactive documents are reported, never auto-filled
or activated. The command uses the E5 tokenizer and checks `passage: ` plus
special tokens against 512 tokens, without loading the embedding model.
