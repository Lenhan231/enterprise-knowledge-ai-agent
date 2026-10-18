# Benchmark database restored — 2026-10-18

All five VietStyle documents are ready. The production index contains 532
finite, nonzero 384-dimensional vectors from local all-MiniLM-L6-v2 at an
explicit 512-token encoder limit, generated on cuda:0. Parser text, parser
metadata, structured tables and authoritative document access roles were
retained; no database migration or OCR rerun occurred. The parser snapshot
SHA-256 is unchanged. No hosted embedding/translation/generation calls ran.

| Source | Indexed chunks |
| --- | ---: |
| Policy rules CSV | 12 |
| Inventory planner XLSX | 485 |
| Cycle count SOP PDF | 9 |
| Inventory policy manual DOCX | 18 |
| Training deck PPTX | 8 |

## Fixes

- Local EmbeddingService now applies EMBEDDING_MAX_SEQUENCE_LENGTH to the
  underlying Sentence Transformers encoder and rejects limits above a known
  architectural maximum. Restart already running app processes to load it.
- The retry CLI now uses ParserChunksRepository and the same bounded chunk
  builder as upload/retry. Removed repository imports and obsolete parser
  status calls were replaced. It never overwrites retained parser output.
- Explicit failed/parsed upload IDs can be retried together, loading the model
  once. Ready documents are refused, and ready status follows vector storage.

The original historical upload failures are not attributed to these fixes:
only status was stored, so their exact cause was not established. The old
CLI was broken after main's repository reorganization; direct local recovery
now succeeds using the supported repositories.

## Verification

- All 532 actual encoder inputs retain their full tokenizer length. Maximum
  observed input: 402 tokens including special tokens. Zero truncations.
- A 400-word probe produces 402 input tokens, demonstrating that the encoder
  is no longer cutting at its packaged 256-token default.
- Dense, BM25 and hybrid each returned ten scoped chunks for Q01, Q05 and Q15:
  nine live retrieval checks. These are availability checks, not quality scores.
- 28 targeted tests passed: embeddings 5, retry 2, translated hybrid 9,
  document scope 2, retrieval service 10. Compilation and diff checks passed.

Use benchmark-config.json for current IDs/model/settings. indexed-corpus.jsonl
and baseline-vectors.npy freeze the indexed baseline for offline comparison.
The new model/limit and parser output differ from historical benchmarks;
do not compare old scores as if only one variable changed. Other embedding
models must generate their own vectors, even when dimensions match.
README.txt is still missing, and document language labels remain unchanged.

Code changes and these new reports have not been committed or pushed.
