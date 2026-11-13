# Run the source-context reranker experiment on free Colab

1. Open https://colab.research.google.com/ and choose File → Upload notebook.
   Upload `reranker_context_colab.ipynb` from this folder.
2. Choose Runtime → Change runtime type → T4 GPU (or another available free GPU).
   Stay on the free tier; do not purchase compute units. If unavailable, wait
   or use the home RTX 2060. Free GPU access is not guaranteed.
3. Run notebook cells from top to bottom. If the dependency installer requests
   a runtime restart, restart and continue with the GPU-check cell.
4. The upload cell opens a file picker. Select `reranker_colab_inputs.zip`
   (about 22 MB). No GitHub or Hugging Face credentials are needed.
5. Run inference. The pinned ~2.3 GB BGE reranker downloads into Colab's storage,
   not your laptop. Both plain and source-context conditions run on that GPU.
6. Run verification and summary, then the final cell to download
   `reranker_context_results.zip`. Send that ZIP back for findings/regression
   analysis. It excludes model weights. Keep the browser connected while running.

The standalone bundle includes canonical committed source data, evidence labels,
saved E5 candidate vectors and the small evaluator code subset. It contains
neither `.env` nor API keys nor model weights. The original app/database is not
used. Uploading this bundle sends the simulated benchmark data to your Colab VM.

No total context-token budget is imposed. The 1,024-token per-pair limit is
validated before scoring; inputs exceeding it fail rather than truncate.
The source-context treatment applies uniformly to passages of at most 800
characters. Returned/scored passages remain the original text.

Before: the new experimental runner only ran on local CPU and required a Git
checkout. After: `--input-root`, `--output-dir`, `--device cuda` and explicit
`--allow-download` support an uploaded bundle in Colab. Defaults still use CPU
and offline model loading. Production retrieval is unchanged.

The packaged input loader has been run locally: all strict input/source/vector
hashes and original dense orders passed for 1,063 passages and 80 cases under
evidence v3. Notebook Python cells passed syntax checks. Colab GPU execution has
not been performed from this laptop; no new inference results exist yet.

If a run fails, the final download cell can save partial checkpoints, but they
are not completed results. Do not rerun a completed output folder; choose a
fresh output path to preserve it. A disconnected Colab VM may lose its files.

References: [Colab limits](https://research.google.com/colaboratory/faq.html).
