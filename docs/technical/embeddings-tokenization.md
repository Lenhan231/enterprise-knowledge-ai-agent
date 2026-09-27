# Embeddings and tokenization

## Active configuration

- Environment setting: `EMBEDDING_MODEL`.
- Input cap: `EMBEDDING_MAX_SEQUENCE_LENGTH` (default `512`, including special
  tokens required by the model).
- Default in `.env.example` and `EmbeddingService`:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- The same local Hugging Face Sentence Transformers model embeds document
  passages and user queries through `EmbeddingService`.
- PostgreSQL stores `vector(384)` and ranks cosine distance with pgvector.
- `TokenCounter` loads `AutoTokenizer` for the same model and records token
  counts in chunk metadata. It does not truncate or reject overlength text.

The configured model is the only model currently used by the app. Proposal
models are evaluated offline by `scripts/evaluate_embeddings.py`; its
same-sample smoke reports live under `artifacts/evaluation/` and do not change
the production vectors. Changing the app model requires matching vector
dimensions and re-embedding every stored chunk before search.

The original three-model paired smoke uses 38 of 3,785 ready Vinamilk chunks
(up to three per document). An expanded paired run uses 93 chunks (up to eight
per document); all models share the same corpus SHA-256 and nine-case hash.
On CPU, corpus embedding took 103 s for BGE-M3, 1,325 s for Qwen3 Embedding
0.6B, and 134 s for e5-large-v2. Mean query time was 171, 1,355 and 219 ms,
respectively; peak RSS was 2,434, 2,637 and 2,189 MiB. Scores and limits are in
the expanded-run artifacts linked from the [evaluation matrix](agents-and-evaluation.md).
Batch sizes were 1/8/4, so measured throughput reflects each recorded CPU
configuration and is not a batch-controlled speed ranking.

A separate e5-large-v2 scaling run uses 181 chunks (up to 16 per document):
peak RSS 2,228 MiB, corpus embedding 236 s, mean query 207 ms. Its ranking
scores are not directly comparable with the paired runs because the sample
differs. All these runs are nine-query, document-level smoke evaluations; none
uses the full ready corpus or passage-level judgments.

### Refreshed 12-case embedding comparison

After adding three governance queries, BGE-M3 and e5-large-v2 were rerun on the
same 173 evenly sampled chunks across all 25 ready documents, with the same
case hash, CPU, batch 8 and 512-token input limit. BGE/e5 MRR is 0.606/0.706,
Recall@3 is 0.750/0.833, and nDCG@3 is 0.616/0.719. Corpus embedding took
223/281 seconds; mean query encoding/scoring took 187/224 ms. The sample is 173
of 4,750 chunks, so this is not full-corpus model selection. Qwen3-Embedding
did not complete on this CPU: its first batch took about 200 seconds. Full
metrics, case-level ranks, hashes and this limitation are in
[`vinamilk-embedding-three-model-expanded-25docs-12cases-20260927.json`](../../artifacts/evaluation/vinamilk-embedding-three-model-expanded-25docs-12cases-20260927.json).

### Cloud run on the full public corpus

The local evaluator now accepts `--corpus` JSONL as well as the live database.
`uv run python scripts/export_public_embedding_corpus.py` exports only ready
document IDs present in the public manifest, preserves their `allowed_roles`,
and writes a SHA-256 metadata sidecar. The committed 2026-09-27 snapshot has
4,750 passages from 25 public Vinamilk sources; no database credential is
needed in a hosted runtime. The loader rejects any document ID outside the
manifest allowlist. `notebooks/kaggle_embedding_benchmark.ipynb` runs BGE-M3,
Qwen3-Embedding-0.6B and e5-large-v2 separately on the exact same complete
corpus and twelve cases with CUDA and batch size 4. It records each model
revision, data hashes, peak RAM/VRAM and per-case rankings. This is a larger
paired smoke benchmark, not final selection: the twelve document-level labels
remain sparse and do not replace passage-level judgments or human QA review.

## Input-length constraint

The model reports a 512-token maximum sequence length. Seed PDF chunks target
1,200 characters and upload chunks 1,100; character limits do not guarantee a
token limit, especially for Vietnamese text. `TokenCounter.split_text` now
splits overlength chunks before embedding and stores the recalculated token
count. The 11-report corpus has been re-ingested with this guard; a read-only
database check found no stored report chunk above the configured sequence limit.

Useful source: `src/core/embeddings/embedding_service.py`,
`src/core/utils/token_counter.py`, `.env.example`, and
`src/database/migrations/001_create_document_chunks.sql`.
