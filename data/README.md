# Apple corpus

The `documents` table in Supabase is the source of truth for the Apple corpus
manifest. Raw downloads and generated Markdown are local artifacts and are not
committed.

## Prerequisites

- Set `DATABASE_URL` in `.env`.
- Apply the SQL migrations in `src/database/migrations/`.
- Configure the embedding model required by the ingestion pipeline.

## Review 1 corpus

`scripts/download_apple_corpus.py` downloads these default document IDs:

- `APL-CMP-003`
- `APL-CMP-004`
- `APL-PRC-002`
- `APL-PRC-015`
- `APL-ENV-002`

Download the frozen subset into a dedicated directory:

```bash
python scripts/download_apple_corpus.py \
  --output data/raw/apple_review1
```

The downloader reads metadata from Supabase, validates the PDF signature, and
skips existing files. Use `--force` to replace existing downloads.

Download specific document IDs when needed:

```bash
python scripts/download_apple_corpus.py \
  --ids APL-CMP-003 APL-PRC-002 \
  --output data/raw/apple_review1
```

## Ingestion

Parse, chunk, embed, and persist the Review 1 subset:

```bash
python scripts/ingest_apple_corpus.py \
  --input data/raw/apple_review1 \
  --output data/processed/apple_review1
```

For a small metadata check, ingest one file:

```bash
python scripts/ingest_apple_corpus.py \
  --file data/raw/apple_review1/compliance/apl-cmp-003_anti_corruption_policy.pdf \
  --output data/processed/apple_review1
```

Re-ingestion is idempotent by `document_name`: existing chunks for that file
are deleted and replaced in one transaction, and each document starts at
`chunk_index = 0`.

## Evidence checks

Summarize chunk coverage:

```sql
select
    metadata->>'document_id' as document_id,
    count(*) as chunk_count,
    min(chunk_index) as first_index,
    max(chunk_index) as last_index,
    min((metadata->>'page_number')::int) as first_page,
    max((metadata->>'page_number')::int) as last_page
from document_chunks
group by metadata->>'document_id'
order by document_id;
```

Inspect representative provenance:

```sql
select
    chunk_index,
    metadata->>'document_id' as document_id,
    metadata->>'source_document' as source_document,
    metadata->>'page_number' as page_number,
    metadata->>'token_count' as token_count,
    metadata->>'section_title' as section_title,
    metadata->>'parent_id' as parent_id
from document_chunks
where metadata->>'document_id' = 'APL-CMP-003'
order by chunk_index
limit 5;
```

## Known limitations

- The verified ingestion path currently supports PDF files only.
- Section-title extraction is not integrated, so `section_title` is `null`.
- Hierarchical parent sections are not persisted, so `parent_id` is `null`.
- OCR, layout-aware parsing, and table extraction are not part of the Review 1
  baseline.

## Retrieval checkpoint

Run the existing retrieval check after ingestion:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/check_apple_retrieval.py
```

Inspect `document_name`, `chunk_index`, `similarity_score`, metadata, and chunk
content before expanding beyond the Review 1 subset.
