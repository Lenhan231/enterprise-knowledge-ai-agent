# Frozen embedding benchmark — 2026-10-01

`corpus.jsonl` is a byte-for-byte snapshot of the existing public Vinamilk
embedding corpus: 4,750 chunks from 25 documents. No documents were reparsed
or rechunked. This is a saved historical corpus, not a fresh database export.

`cases.json` freezes the existing 12 document-labeled retrieval questions.
Five questions are in Vietnamese: 2020, 2021, 2022 and 2024 financial results,
and the nutrition content of ADM low-sugar milk. The manifest records both
input SHA-256 hashes and verifies that every target document exists and is
visible to the case's role. Existing passage labels are not scored here.

## Protocol

- Baseline: the environment-configured `sentence-transformers/all-MiniLM-L6-v2`.
- Comparators: `BAAI/bge-m3`, `Qwen/Qwen3-Embedding-0.6B`, `intfloat/e5-large-v2`.
- Full frozen corpus for every model; no per-document sampling.
- Baseline and BGE-M3: laptop CPU, four compute threads. Qwen3 and e5:
  RTX 2060 in WSL 2 on the user's PC. Batch size eight, normalized cosine scoring.
- Apply role eligibility before ranking; document score is its best chunk score.
- Use each model's native sequence limit capped at 512: baseline is 256 tokens.
  Model tokenizers, query instructions, prefixes and truncation differ; the
  saved chunk text remains identical. This compares configured model behavior,
  not equal tokenization or equal training data.
- Report document Recall@1/3/5, MRR, nDCG, model revisions, input hashes and
  timings. Embedding and model-loading time are separate from query latency.
- Finish BGE-M3 on the laptop; transfer the frozen inputs and completed reports
  to the PC, then run Qwen3 and e5 sequentially with `--device cuda`.

From the repository root, with `OMP_NUM_THREADS=4` and `MKL_NUM_THREADS=4`:

```text
python -X utf8 scripts/retrieval/evaluate_embeddings.py --model baseline --model-id sentence-transformers/all-MiniLM-L6-v2 --corpus data/evaluation/embedding_benchmark_20261001/corpus.jsonl --cases data/evaluation/embedding_benchmark_20261001/cases.json --max-chunks-per-document 100000 --batch-size 8 --device cpu --output artifacts/evaluation/embedding_benchmark_20261001/baseline.json
```

For each comparator, replace `--model baseline --model-id ...` with
`--model bge-m3`, `--model qwen3-embedding`, or `--model e5-large-v2`, and
choose the corresponding output filename. On the GPU PC use `--device cuda`;
the other arguments stay fixed. See the artifact folder's `GPU_HANDOFF.md`.

## Limits

This small, existing question set is document-level evidence, not an independent
test of answer faithfulness or passage recall. The source labels and role
assignments are inherited from the demo. CPU and GPU timings are specific to
their hardware and do not establish relative speed on identical hardware.
No production embeddings or database records are modified.
