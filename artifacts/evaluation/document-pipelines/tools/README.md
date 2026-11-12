# Benchmark scripts

Run these from `artifacts/evaluation/document-pipelines/`.

- [`runners/run_shared_benchmark.py`](runners/run_shared_benchmark.py) runs Docling on the current HTML-reviewed page set and writes normalized `page-prediction-v1` JSONL, raw outputs, and metadata.
- The same runner accepts `--ocr-engine vietocr` for an experimental Docling OCR adapter: Docling keeps layout/table processing, Tesseract OSD checks each OCR crop's orientation, RapidOCR detects text lines, and VietOCR recognizes each line. Use `--page-id` to run one reviewed page and `--layout-model egret-medium` to compare Docling's alternate Egret layout model with the default Heron.
- [`runners/run_vietocr_benchmark.py`](runners/run_vietocr_benchmark.py) runs the older shared-detector recognizer setup (RapidOCR detection + VietOCR line recognition) on the current HTML-reviewed OCR pages. It writes `predictions.jsonl`, `evaluation.json`, and `run-metadata.json`, without a Markdown report.
- [`evaluators/evaluate_shared_benchmark.py`](evaluators/evaluate_shared_benchmark.py) evaluates OCR, layout, table, and end-to-end cohorts from that JSONL. It supports multiple reviewed tables per page.
- [`metrics/text_metrics.py`](metrics/text_metrics.py) provides shared Levenshtein, CER, and token error primitives.
- [`metrics/iou_metrics.py`](metrics/iou_metrics.py) provides box IoU and one-to-one matching used by layout and table scoring.
- [`metrics/table_metrics.py`](metrics/table_metrics.py) scores table detection and cell grids.

Example:

```bash
../../../.venv/bin/python tools/runners/run_shared_benchmark.py --run-id docling-html-baseline
../../../.venv/bin/python tools/evaluators/evaluate_shared_benchmark.py \
  --predictions results/shared-html/docling-html-baseline/predictions.jsonl
PYTHONPATH=/tmp/vietocr-benchmark-packages ../../../.venv/bin/python tools/runners/run_vietocr_benchmark.py --run-id vietocr-html-baseline
PYTHONPATH=/tmp/vietocr-benchmark-packages:tools/runners ../../../.venv/bin/python tools/runners/run_shared_benchmark.py \
  --ocr-engine vietocr --page-id E2E-LONG-HAU-2008-p17 --run-id docling-vietocr-osd-longhau-p17
../../../.venv/bin/python tools/evaluators/evaluate_shared_benchmark.py \
  --predictions results/shared-html/docling-vietocr-osd-longhau-p17/predictions.jsonl \
  --page-id E2E-LONG-HAU-2008-p17
```

The VietOCR runner requires `vietocr` runtime packages to be installed in the Python environment or added to `PYTHONPATH`. It uses the `vgg_seq2seq` checkpoint, greedy decoding, and a 512-pixel maximum input width by default.

Use a new `--run-id` for each inference run so output directories stay separate. Existing track-specific benchmark scripts are archived under `archive/legacy/`.
