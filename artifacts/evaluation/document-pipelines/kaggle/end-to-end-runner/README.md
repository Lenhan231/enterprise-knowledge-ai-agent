# Kaggle end-to-end runner

This folder contains the Kaggle Docling + Tesseract kernel. The local orchestration script is at `kaggle/run.py`. The kernel runs OCR, layout detection, and table extraction on page images. `--pilot-5` tests changes on five fixed owner-reviewed pages; `--all-reviewed` runs all pages currently marked `owner_reviewed` in `data/local-review-state.json`. Newly reviewed pages join the full cohort automatically.

From `artifacts/evaluation/document-pipelines`, run `../../../.venv/bin/python kaggle/run.py --pilot-5` or `--all-reviewed`. The runner refreshes the label-free Kaggle image dataset only when its content hash changes, pushes the T4 kernel, waits for completion, downloads raw page outputs, normalizes them to `page-prediction-v1`, evaluates locally, and saves the run under `results/shared-html/`.

Kaggle receives page images and a manifest with page IDs, dimensions, and image hashes. OCR transcripts and layout/table references remain local. The Results dashboard discovers saved runs through the review server.
