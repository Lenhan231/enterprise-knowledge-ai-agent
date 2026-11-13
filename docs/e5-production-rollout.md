# Production embedding switch to multilingual E5-base

On 2026-10-21, the user requested a complete switch from MiniLM to the E5 model
used in the successful frozen retrieval experiments. The active index is still
`public.document_chunks`, now `vector(768)`. There is no sidecar index or live
MiniLM fallback.

## Before / after

- Before: `sentence-transformers/all-MiniLM-L6-v2`, 384-dimensional vectors, no E5 prefixes.
- After: `intfloat/multilingual-e5-base`, revision `d128750597153bb5987e10b1c3493a34e5a4502a`,
  768 dimensions, normalized vectors, `query: ` / `passage: ` prefixes, encoder cap 512.
- The same 532 texts, five document IDs, chunk indices, ACL metadata, row IDs,
  status fields, and timestamps are retained. Embedding provenance/token counts
  were updated. Parser output and frozen benchmark labels were not changed.
- Future chunking reserves four tokens for the passage prefix; the E5 tokenizer
  revision is pinned to the encoder revision.

## Teammate setup after pulling Huy

Existing `.env` files override code defaults, so update them explicitly and restart:

```bash
EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBEDDING_BACKEND=local
EMBEDDING_MAX_SEQUENCE_LENGTH=512
```

Use the configured production model for both ingestion and queries. Existing
MiniLM clients cannot query a 768-dimensional E5 index. Download/provision E5 on
the actual app compute host if it is not already cached. The cached model was
available locally for this rollout; no new model download was needed.

For translated hybrid plus BGE, select `translated_hybrid_rerank`; the default
retrieval strategy is still `hybrid`. Configure BGE separately as documented in
[the integration guide](translated-hybrid-rerank.md). Updating embeddings does not
by itself certify LLM answers or repeat the complete frozen benchmark.

## Migration procedure and safeguards

`scripts/retrieval/migrate_e5_index.py` is an operational migration for this exact
corpus, not an automatically applied Supabase schema migration. Dry-run by default.
It checks the cached vector SHA256, E5 configuration, dimensions, normalization,
all live chunk identities/names/texts, and actual E5-prefixed token lengths. It
refuses a different corpus/model. An existing recovery backup is reused only if
its hash exactly matches the current pre-migration source index.

With `--apply`, a single transaction locks the index, saves a restricted local
recovery snapshot under ignored `.venv/e5-migration-recovery/`, changes the vector
column to 768, populates every verified E5 vector, restores NOT NULL, rebuilds the
cosine HNSW index, and verifies source identity/content and all vectors before commit.
Any exception rolls back the database transaction. The first attempt rolled back
on a pgvector adapter conversion in the final verification; that check was fixed
and the retry completed successfully. The local recovery snapshot is
not committed or pushed. It is for emergency recovery only, not a live MiniLM path.
Do not rerun the migration against the now-E5 index. Future content changes require
fresh E5 embeddings through the regular ingestion path.

Rollout/preflight/smoke results are under
`artifacts/evaluation/e5-production-rollout-20261021/`.

## Checks

57 targeted tests passed with `EMBEDDING_MODEL=intfloat/multilingual-e5-base`, including
prefixes, normalization, revision pinning, chunk budget, existing SQL filters,
parser integration, translation/reranking provenance, and API dispatch. The legacy
`test_app_request_models` import drift noted in the handoff remains outside this
passing suite. Live smoke results verify actual E5 inference and dense database
retrieval; they do not call Groq or the generation LLM.

The guarded Supabase migration `20261021090000_switch_active_embedding_index_to_e5.sql`
allows fresh empty databases to adopt vector(768), accepts an already verified E5
index, and refuses to cast a populated MiniLM index without E5 vectors.
