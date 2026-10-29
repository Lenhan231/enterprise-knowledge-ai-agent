# Kaggle runs

`end-to-end-runner/` contains the active Kaggle document-processing flow. Older kernel snapshots and input packages live under `archive/` for reference.

Smoke-test Docling + Tesseract on the fixed five-page cohort:

```bash
../../../.venv/bin/python kaggle/run.py --pilot-5
```

When ready, run the full currently reviewed cohort:

```bash
../../../.venv/bin/python kaggle/run.py --all-reviewed
```

The command creates an inference-only image package, updates the stable private dataset `letrongnhan/vietnamese-enterprise-e2e-hard-scans` only when its content hash changes, pushes the T4 kernel, waits for completion, downloads OCR/layout/table outputs, scores CER/WER, reading order, layout, and tables locally, and saves a dashboard run. Newly approved pages are picked up on the next run. OCR/layout/table references stay local and are never uploaded.

To smoke-test the same end-to-end pipeline with VietOCR, run `../../../.venv/bin/python kaggle/run.py --pilot-5 --ocr-engine vietocr`. The runner packages `tools/runners/docling_vietocr.py` and `line_detection.py` into the private Kaggle input dataset, then downloads and scores the five-page run locally.
