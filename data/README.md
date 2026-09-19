# Apple corpus

The raw Apple corpus is reproducible from the project Google Sheet. A local
snapshot is also committed at
`data/manifests/apple/FA26AI69_Apple_Corpus_Manifest_v1.xlsx`. Large downloaded
PDFs and generated Markdown files are intentionally ignored by Git.

## Five-document vertical slice

Download the initial corpus:

```bash
python scripts/download_apple_corpus.py
```

Download all rows from the manifest instead of the default five-document
vertical slice:

```bash
python scripts/download_apple_corpus.py --all
```

Download one or more specific document IDs:

```bash
python scripts/download_apple_corpus.py --ids APL-PRC-013
```

The project Google Sheet is the default manifest. Another public sheet or the
local snapshot can be selected explicitly:

```bash
python scripts/download_apple_corpus.py --manifest path/to/manifest.xlsx
```

The sheet must be accessible to anyone with the link. The downloader uses
Google's XLSX export endpoint, preferring a worksheet named `Manifest` and
otherwise reading the first worksheet. Restricted sheets require an
authenticated Google API integration and are not supported by this command.

This creates:

```text
data/raw/apple/
├── compliance/
├── procurement/
├── finance/
├── supply_chain/
└── environment/
```

The default selection is Business Conduct Policy, Anti-Corruption Policy,
Third Party Code of Conduct, Apple Purchase Order Terms, and Supplier Code of
Conduct. The downloader validates the PDF signature and skips existing files;
pass `--force` to download them again.

Manifest rows declared as HTML (or multi-format landing pages ending in
`.html`/`.aspx`) are saved as `.html`; PDF rows retain signature validation.
Image rows support JPEG, PNG, GIF, WebP, TIFF, and SVG with signature
validation. Format handling is split into independent modules under
`scripts/source_downloaders/`; register additional source types in
`registry.py` without changing the command-line workflow.
When using `--all`, a failed source is reported and the remaining documents are
still attempted. The command exits with status 1 if any downloads failed and
prints a summary when complete.

With `DATABASE_URL` pointing to a PostgreSQL database with pgvector and the
schema in `src/database/migrations/001_create_document_chunks.sql` applied, set
`EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` and run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/ingest_apple_corpus.py
```

Generated Markdown is written below `data/processed/apple/`. Re-running the
command atomically replaces chunks for each source document, so ingestion is
idempotent by document name.

## Retrieval checkpoint

Use `RAGService.retrieve()` with these cross-document questions:

```text
What standards must third parties working with Apple follow?
What obligations does a supplier have regarding subcontractors?
What requirements apply to supplier personnel?
How does Apple's anti-corruption policy relate to third parties?
```

Inspect `document_name`, `chunk_index`, `similarity_score`, and the full chunk
content returned for each result before expanding to the rest of the manifest.
The repeatable checkpoint command is:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/check_apple_retrieval.py
```
