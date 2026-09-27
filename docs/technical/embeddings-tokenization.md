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
