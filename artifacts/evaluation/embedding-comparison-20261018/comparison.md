# VietStyle embedding comparison — 2026-10-18

Same five documents, 532 unchanged chunks and 20 Vietnamese questions. All models ran locally on RTX 2060. No inference API calls or database writes. Hugging Face HTTP access only downloads model metadata, tokenizers and weights; document text stays local.

| Model | Source recall@10 | Full-source cases | Gain over MiniLM | Dimensions |
| --- | ---: | ---: | ---: | ---: |
| all-MiniLM-L6-v2 | 80.00% | 10/20 | — | 384 |
| multilingual-e5-base | 93.33% | 16/20 | +13.33 percentage points | 768 |
| bge-m3 | 89.17% | 15/20 | +9.17 percentage points | 1024 |
| qwen3-embedding-0.6b | 86.67% | 13/20 | +6.67 percentage points | 1024 |
| e5-large-v2 | 78.33% | 10/20 | -1.67 percentage points | 1024 |

E5-base has the highest expected-source coverage in this pilot. This is not passage relevance or answer accuracy, and does not establish performance on unseen or cross-language questions. Missing README.txt for Q01/Q18/Q19 remains in the denominator; the available-source ceiling is 95%.

## Code: before and after

Before: evaluate_vietstyle_dense.py queries the existing Supabase MiniLM index. The older evaluate_embeddings.py assumes the old public corpus and ranks documents rather than chunks.

After: added scripts/retrieval/evaluate_embedding_candidates.py. One script selects all three models, reuses the existing BGE/Qwen recipes and role filter, adds E5-base, validates frozen hashes and input lengths, pins model/tokenizer revision, creates normalized vectors and searches them locally. E5 uses query:/passage: prefixes; Qwen uses an English retrieval instruction only on questions; BGE-M3 has no extra prefix. Saved chunk text and questions are unchanged.

embedding_service.py was not modified further in this task. Supabase still uses its working MiniLM index. Candidate files are separate: config.json, vectors.npy, query-vectors.npy, results.json. Their row order follows indexed-corpus.jsonl and is recorded by hash.

## Validation

Three focused unit checks passed: correct model formatting; role filtering and missing-README scoring; fail-closed overlength detection. Local MiniLM replay reproduced exact database top-ten orders for all 20 cases. All 60 candidate scores and complete top-ten lists were independently regenerated from saved passage/query vectors. Each candidate has 532 finite normalized vectors and identical corpus/case hashes. All candidates used float32 and a 512-token limit; no prefixed input exceeded it.

## Cost and paired changes

| Candidate | Corpus encoding | Peak PyTorch allocated VRAM | Batch | Better / worse / same vs MiniLM |
| --- | ---: | ---: | ---: | ---: |
| multilingual-e5-base | 14.15 s | 1105 MiB | 2 | 7 / 0 / 13 |
| bge-m3 | 29.05 s | 2220 MiB | 2 | 7 / 2 / 11 |
| qwen3-embedding-0.6b | 56.44 s | 2398 MiB | 1 | 5 / 1 / 14 |

Single-run timings and different batch sizes do not establish a controlled speed ranking. Local timings exclude SQL/network and cannot be compared directly with the database baseline latency. Peak allocated VRAM measures this process, not total desktop/driver usage.

| Case | MiniLM | E5-base | BGE-M3 | Qwen3-0.6B |
| --- | ---: | ---: | ---: | ---: |
| Q01 | 33.33% | 66.67% | 66.67% | 66.67% |
| Q02 | 100.00% | 100.00% | 100.00% | 100.00% |
| Q03 | 100.00% | 100.00% | 100.00% | 100.00% |
| Q04 | 100.00% | 100.00% | 100.00% | 100.00% |
| Q05 | 50.00% | 100.00% | 100.00% | 100.00% |
| Q06 | 100.00% | 100.00% | 100.00% | 100.00% |
| Q07 | 66.67% | 100.00% | 100.00% | 66.67% |
| Q08 | 66.67% | 66.67% | 100.00% | 100.00% |
| Q09 | 100.00% | 100.00% | 100.00% | 100.00% |
| Q10 | 100.00% | 100.00% | 100.00% | 50.00% |
| Q11 | 100.00% | 100.00% | 50.00% | 100.00% |
| Q12 | 66.67% | 100.00% | 66.67% | 66.67% |
| Q13 | 100.00% | 100.00% | 100.00% | 100.00% |
| Q14 | 100.00% | 100.00% | 100.00% | 100.00% |
| Q15 | 100.00% | 100.00% | 100.00% | 100.00% |
| Q16 | 66.67% | 100.00% | 100.00% | 100.00% |
| Q17 | 50.00% | 100.00% | 100.00% | 50.00% |
| Q18 | 66.67% | 66.67% | 33.33% | 66.67% |
| Q19 | 66.67% | 66.67% | 66.67% | 66.67% |
| Q20 | 66.67% | 100.00% | 100.00% | 100.00% |

## Reproduce

```bash
.venv/bin/python scripts/retrieval/evaluate_embedding_candidates.py \
  --snapshot artifacts/evaluation/embedding-comparison-20261018 \
  --model multilingual-e5-base --device cuda --batch-size 2 \
  --output-dir artifacts/evaluation/embedding-comparison-20261018/candidates/e5-repeat
```

Use --revision with the recorded commit to pin the same model version. Existing vectors/results are protected; choose a new --output-dir for repeats. No new dependencies were needed. No commit or push performed.

## Additional proposal model: e5-large-v2

Added one model configuration to evaluate_embedding_candidates.py with query:/passage: prefixes; no new retrieval logic or embedding_service.py changes. Same frozen corpus/questions, CUDA, float32, batch 2, cap 512. Cached revision ran offline. Maximum passage length 404 tokens, zero truncation. Three existing unit checks passed; independently reproduced all 20 top-ten rankings and scores from finite normalized saved vectors (532 x 1024 passages, 20 x 1024 queries). Database unchanged.

Model card: https://huggingface.co/intfloat/e5-large-v2 states English-only support. This run retains Vietnamese inputs to measure suitability for this corpus; it does not measure English retrieval or answer accuracy. Detailed outputs: candidates/e5-large-v2/results.json.
