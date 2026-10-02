# Frozen embedding benchmark — 2026-10-01

All four reports use the same verified input hashes: 4,750 saved chunks, 25 documents,
and 12 labeled questions (five Vietnamese). All chunks were included; none were rechunked.

The configured baseline is `sentence-transformers/all-MiniLM-L6-v2`, using the local backend.

## All 12 questions

| Model | Device | Recall@1 | Recall@5 | MRR | nDCG@5 | Corpus embedding seconds | Mean query ms |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | cpu | 0.6667 | 0.9167 | 0.7597 | 0.7874 | 229.69 | 17.20 |
| bge-m3 | cpu | 0.7500 | 0.9167 | 0.8176 | 0.8348 | 5233.79 | 143.10 |
| qwen3-embedding | cuda | 0.7500 | 0.9167 | 0.8028 | 0.8239 | 892.70 | 70.80 |
| e5-large-v2 | cuda | 0.6667 | 0.9167 | 0.7583 | 0.7917 | 341.22 | 30.90 |

## Five Vietnamese questions

| Model | Recall@1 | Recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|---:|
| baseline | 0.6000 | 1.0000 | 0.6900 | 0.7635 |
| bge-m3 | 0.8000 | 1.0000 | 0.9000 | 0.9262 |
| qwen3-embedding | 0.8000 | 1.0000 | 0.8667 | 0.9000 |
| e5-large-v2 | 0.6000 | 1.0000 | 0.7333 | 0.8000 |

## Verification and limits

Prior handoff regression suite: 487 tests, exit code 0, 10 skips. See `regression.log`.
The initial merged checkout failed; corrections restore main's RAG test mock,
update the moved Apple evaluator import/root and explicit dense selection, and
handle Windows resource telemetry, permissions and optional source fixtures.
Tests ran in UTF-8 mode with a test-only authentication secret; `.env` was not changed.

This measures role-filtered dense document retrieval using maximum chunk cosine per
document. It does not measure hybrid search, year boosting, reranking, passage relevance,
or generated answers. The labels are inherited from a small demo set, not independent review.

The baseline retains its native 256-token limit; the other runs cap their limits at 512.
All receive identical saved text, but model tokenizers, truncation and recommended prefixes
differ. All runs use four compute threads and batch size eight. Qwen3/e5 completed
on an RTX 2060 in WSL: accuracy can be compared on the frozen inputs, but CPU/GPU
timings are not a controlled speed comparison. Model loading may include downloads
and differs with cache state. No database embeddings were modified.

Input provenance and reproduction commands: `data/evaluation/embedding_benchmark_20261001/README.md`.
