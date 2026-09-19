# Apple corpus

The raw Apple corpus is reproducible from the committed manifest at
`data/manifests/apple/FA26AI69_Apple_Corpus_Manifest_v1.xlsx`. Large downloaded PDFs
and generated Markdown files are intentionally ignored by Git.

## Five-document vertical slice

Download the initial corpus:

```bash
python scripts/download_apple_corpus.py
```

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

With `DATABASE_URL` pointing to a PostgreSQL database with pgvector and the
schema in `src/database/migrations/001_create_document_chunks.sql` applied, run:

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
