# Continue the frozen benchmark on the GPU PC

## Resume from the Huy branch

In your WSL checkout, fetch and switch to the existing `Huy` branch (capital H),
then pull it:

```bash
git fetch origin
git switch Huy
git pull --ff-only origin Huy
```

Run the commands below from the repository root. You do not need to extract
the ZIP when using this checkout. Use a fresh Linux virtual environment;
the laptop's Windows `.venv` is not portable.

## Current state and next task

- Main was merged into Huy at `a0fc63e`; retrieval uses main's implementation.
- Regression verification completed: 487 tests, 10 skipped, exit code zero.
  It used UTF-8 mode and a test-only authentication secret; `.env` was unchanged.
- Configured baseline: local `sentence-transformers/all-MiniLM-L6-v2`.
- Baseline and BGE-M3 CPU runs are complete, with committed JSON reports.
  Overall Recall@1 / Recall@5 / MRR: baseline 0.6667 / 0.9167 / 0.7597;
  BGE-M3 0.7500 / 0.9167 / 0.8176.
- Remaining work: run Qwen3-Embedding-0.6B and e5-large-v2 on the RTX 2060,
  then generate the four-model comparison. Neither remaining run is complete.
- Reuse all 4,750 frozen chunks and 12 labeled questions (five Vietnamese).
  Do not parse or chunk documents again, change labels, or write to the database.
- Baseline uses its native 256-token limit; other models are capped at 512.
  This scores dense document retrieval, not hybrid search or answer quality.
- Previous fixes cover Windows memory telemetry, moved evaluator paths,
  explicit dense evaluation and regression test fixtures. They are included here.

## Optional standalone bundle

Extract `embedding_benchmark_20261001_gpu.zip` into a separate folder. It is
a standalone public-data benchmark bundle, not the full application. It
contains the frozen corpus/questions/manifest, minimal evaluator code, CPU
reports and the comparison script. It contains no `.env`, database credentials,
virtual environment or downloaded model weights.

## WSL environment and remaining runs

Use WSL 2 on the RTX 2060 PC, Python 3.11 or newer, CUDA-enabled PyTorch,
and the benchmark dependencies. In WSL, run `nvidia-smi` to check that the
Windows NVIDIA driver exposes the GPU. WSL uses the Windows driver;
do not install a Linux NVIDIA display driver inside WSL.
See [NVIDIA's WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/).

Create a Linux virtual environment (`python3 -m venv .venv`, then
`source .venv/bin/activate`). Install CUDA-enabled PyTorch using the
[official installer](https://pytorch.org/get-started/locally/), selecting
Linux, Pip, Python and a CUDA version supported by your driver. Then install
the other benchmark dependencies:

```bash
python -m pip install sentence-transformers==6.0.1 transformers==5.17.0 numpy==2.4.6 huggingface-hub==1.31.0
```

The laptop's package versions are recorded in the input manifest. Keep batch
size eight, the full-corpus cap, the same questions and the model-specific
prefixes/instructions implemented by the evaluator. Do not regenerate inputs.

From the extracted folder, first verify GPU availability:

```bash
python -c "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA-enabled PyTorch is required')"
```

Run the remaining models sequentially:

```bash
python -X utf8 scripts/retrieval/evaluate_embeddings.py --model qwen3-embedding --device cuda --batch-size 8 --top-k 30 --max-chunks-per-document 100000 --corpus data/evaluation/embedding_benchmark_20261001/corpus.jsonl --cases data/evaluation/embedding_benchmark_20261001/cases.json --output artifacts/evaluation/embedding_benchmark_20261001/qwen3-embedding.json
python -X utf8 scripts/retrieval/evaluate_embeddings.py --model e5-large-v2 --device cuda --batch-size 8 --top-k 30 --max-chunks-per-document 100000 --corpus data/evaluation/embedding_benchmark_20261001/corpus.jsonl --cases data/evaluation/embedding_benchmark_20261001/cases.json --output artifacts/evaluation/embedding_benchmark_20261001/e5-large-v2.json
```

After both reports exist, verify all four runs and generate the comparison:

```bash
python -X utf8 artifacts/evaluation/embedding_benchmark_20261001/summarize.py
```

This produces `comparison.json` and `report.md`. The verification rejects
changed input hashes, missing model revisions, mismatched labels, or differing
role-visible chunk counts. Transfer both GPU reports back to the laptop's
corresponding artifact folder if you want the same comparison there.

Compare document retrieval scores across all four runs. CPU and GPU timings
must remain hardware-specific; these runs do not establish relative speed on
identical hardware. The benchmark does not modify a database or evaluate
hybrid retrieval, reranking, or generated answers.
