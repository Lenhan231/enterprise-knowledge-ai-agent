# Document pipeline benchmark

The active benchmark uses only owner-reviewed data entered through [`data/review.html`](data/review.html). Its **Results dashboard** tab shows saved pipeline outputs from every run folder. The page images and local review state live under `data/`; each approved save refreshes references for OCR, layout, tables, and end-to-end.


## Run and score

Run commands from this directory. The current local runner uses Docling on CPU:

```bash
../../../.venv/bin/python tools/runners/run_shared_benchmark.py --run-id docling-html-baseline
../../../.venv/bin/python tools/evaluators/evaluate_shared_benchmark.py \
  --predictions results/shared-html/docling-html-baseline/predictions.jsonl
```

The runner writes normalized `page-prediction-v1` JSONL, raw page output, and run metadata to `results/shared-html/<run-id>/`. The evaluator writes `evaluation.json` and `report.md` beside the predictions. The local CPU smoke baseline is in [`results/shared-html/docling-html-baseline/`](results/shared-html/docling-html-baseline/); the latest full 51-page T4 runs are [`Docling + Tesseract`](results/shared-html/docling-kaggle-owner-reviewed-51-20261024/) and [`Docling + VietOCR`](results/shared-html/docling-vietocr-kaggle-owner-reviewed-51-20261024/).

Metric implementations live in `tools/metrics/` (`ocr_metrics.py`, `layout_metrics.py`, `reading_order_metrics.py`, and `table_metrics.py`); `tools/evaluators/evaluate_shared_benchmark.py` selects cohorts and assembles the report.

The runner records high-resolution page OSD for both OCR engines. The evaluator uses that page angle (confidence ≥ 5.0), or the highest-confidence OCR-region OSD as fallback, to sort blocks in upright reading order before full-page CER/WER. Without confident orientation evidence it keeps top-to-bottom, left-to-right order. Full-page CER/WER include recognition, detection, table extraction, and ordering errors. Reading order is also reported as a separate pairwise order accuracy over regions matched by box IoU 0.50 regardless of label, with matched-region recall.

OCR reports use full-page CER/WER as the primary OCR metrics. Reading order is a separate layout benchmark. True recognizer-only CER/WER needs transcript references aligned to recognized regions.

For a recognizer-only OCR run using RapidOCR detection plus VietOCR, run `PYTHONPATH=/tmp/vietocr-benchmark-packages ../../../.venv/bin/python tools/runners/run_vietocr_benchmark.py`. It writes per-line and per-page predictions, OCR metrics, and runtime metadata to `results/shared-html/vietocr-html-<timestamp>/`; it does not create a Markdown report. VietOCR must be installed in the Python environment or added to `PYTHONPATH`.

To keep the Docling pipeline and replace its OCR model with RapidOCR detection plus VietOCR recognition, while retaining Tesseract OSD on each OCR crop, run `PYTHONPATH=/tmp/vietocr-benchmark-packages:tools/runners ../../../.venv/bin/python tools/runners/run_shared_benchmark.py --ocr-engine vietocr --page-id E2E-LONG-HAU-2008-p17 --run-id docling-vietocr-osd-longhau-p17`, then score it with `tools/evaluators/evaluate_shared_benchmark.py --predictions results/shared-html/docling-vietocr-osd-longhau-p17/predictions.jsonl --page-id E2E-LONG-HAU-2008-p17`. This experiment does not rotate the source image.

To handle tables with different orientations, add `--table-rotation auto` to the command above and choose a new `--run-id`. Tesseract OSD estimates each detected table crop independently; confidence below 5.0 falls back to 0°. Fixed angles (`0`, `90`, `180`, `270`) are also available for controlled comparisons. Trials: [sideways p17](results/shared-html/docling-vietocr-osd-longhau-p17-table-auto/) and [upright p15](results/shared-html/docling-vietocr-osd-longhau-p15-table-auto/). This is an experimental benchmark option, not enabled in the production ingestion pipeline.

To test orientation-aware layout inference, add `--layout-rotation auto`. OSD runs on a larger page render; only the layout model receives the rotated image, and its detected boxes are mapped back to source coordinates. On p17 the rotated layout trial had lower F1 than baseline (15.38% vs 22.22%); after correcting OCR block order, CER was 8.92% vs 9.08%. See [the p17 trial](results/shared-html/docling-vietocr-osd-longhau-p17-layout-rotation-auto-hires/).

## Active data

- [`data/local-review-state.json`](data/local-review-state.json) stores edits from the local review server.
- `data/raw/` holds original page images for review and inference.
- `data/{ocr,layout,table,end-to-end}/reference.jsonl` are generated from pages marked `owner_reviewed` in the HTML workflow.
- OCR, layout, and table scores use all records in their reviewed track references. End-to-end scores use pages with reviewed OCR, layout, and one or more reviewed table grids; multiple tables on a page are supported.
- Each table draft has an editable `table_name`; the table and end-to-end references carry it as descriptive metadata. Existing drafts default to an empty name until the source caption is checked. The table evaluator scores bbox and cell grids, so this metadata does not change benchmark scores.

Start the review UI with `../../../.venv/bin/uvicorn review_server:app --host 127.0.0.1 --port 8767`, then open `http://127.0.0.1:8767`.

For Kaggle end-to-end runs, use `../../../.venv/bin/python kaggle/run.py --pilot-5` to smoke-test Docling + Tesseract OCR, layout, and table extraction on five fixed pages. Once it is ready, use `--all-reviewed` to run all currently approved pages; new reviews are picked up automatically. Both modes refresh Kaggle inputs when hashes change, run the T4 kernel, download outputs, score CER/WER, reading order, layout, and tables locally, and register a run for the Results dashboard.

To add pages from another source, use **Thêm PDF** in the review UI and enter page numbers or ranges such as `1,3-5`. The local server stores the PDF, renders selected pages into `data/raw/`, and adds blank `needs_owner_review` drafts; only pages explicitly checked as reviewed enter the benchmark references. Uploads are limited to 50 MiB and 100 selected pages per request.

For source-based AI drafts, select a page that still needs review and choose a Codex action. **Tạo nháp bằng Codex CLI** regenerates OCR, layout boxes, reading order, and table grids. **Codex CLI: chỉ transcript** regenerates only the full-page OCR text and keeps table grids unchanged. **Codex CLI: chỉ fill bảng** asks Codex CLI for the page orientation, rotates the source and existing table boxes to upright coordinates, then sends separate crops of the table regions. It returns only cell grids (preserving any existing table names), checks each row and numeric string in a second visual pass, and marks unreadable cells `[unclear]`; it keeps OCR text and layout unchanged. Edit grid dimensions with the add/remove row and column controls. **Codex CLI: chỉ chỉnh bbox** refines existing region boxes and keeps OCR, labels, reading order, and table grids. Each action uses the installed `codex` CLI with its existing ChatGPT login and configured model, in an ephemeral read-only session. Generated drafts remain `needs_owner_review`; compare them with the original image and edit before approving. The page image is sent for processing only when a Codex action is clicked. The review chat uses Codex CLI to route one prompt to bbox, transcript, or table, then passes the prompt to that specialist; ambiguous or unsupported requests ask for clarification without changing the draft.

Older crop, 200-page layout, 150-table, and five-page E2E datasets, along with their scripts and historical results, are kept under [`archive/`](archive/README.md). They are not inputs to the active benchmark.
