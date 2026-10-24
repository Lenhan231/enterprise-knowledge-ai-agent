# Document pipeline benchmark

The active benchmark uses only owner-reviewed data entered through [`data/review.html`](data/review.html). The page images and local review state live under `data/`; each approved save refreshes references for OCR, layout, tables, and end-to-end.

## Run and score

Run commands from this directory. The current local runner uses Docling on CPU:

```bash
../../../.venv/bin/python tools/runners/run_shared_benchmark.py --run-id docling-html-baseline
../../../.venv/bin/python tools/evaluators/evaluate_shared_benchmark.py \
  --predictions results/shared-html/docling-html-baseline/predictions.jsonl
```

The runner writes normalized `page-prediction-v1` JSONL, raw page output, and run metadata to `results/shared-html/<run-id>/`. The evaluator writes `evaluation.json` and `report.md` beside the predictions. The current baseline is in [`results/shared-html/docling-html-baseline/`](results/shared-html/docling-html-baseline/).

The runner records high-resolution page OSD for both OCR engines. The evaluator uses that page angle (confidence ≥ 5.0), or the highest-confidence OCR-region OSD as fallback, to sort blocks in upright reading order before OCR CER/WER. Without confident orientation evidence it keeps top-to-bottom, left-to-right order. This page-level sort assumes one dominant orientation per page.

For a recognizer-only OCR run using RapidOCR detection plus VietOCR, run `PYTHONPATH=/tmp/vietocr-benchmark-packages ../../../.venv/bin/python tools/runners/run_vietocr_benchmark.py`. It writes per-line and per-page predictions, OCR metrics, and runtime metadata to `results/shared-html/vietocr-html-<timestamp>/`; it does not create a Markdown report. VietOCR must be installed in the Python environment or added to `PYTHONPATH`.

To keep the Docling pipeline and replace its OCR model with RapidOCR detection plus VietOCR recognition, while retaining Tesseract OSD on each OCR crop, run `PYTHONPATH=/tmp/vietocr-benchmark-packages:tools/runners ../../../.venv/bin/python tools/runners/run_shared_benchmark.py --ocr-engine vietocr --page-id E2E-LONG-HAU-2008-p17 --run-id docling-vietocr-osd-longhau-p17`, then score it with `tools/evaluators/evaluate_shared_benchmark.py --predictions results/shared-html/docling-vietocr-osd-longhau-p17/predictions.jsonl --page-id E2E-LONG-HAU-2008-p17`. This experiment does not rotate the source image.

To handle tables with different orientations, add `--table-rotation auto` to the command above and choose a new `--run-id`. Tesseract OSD estimates each detected table crop independently; confidence below 5.0 falls back to 0°. Fixed angles (`0`, `90`, `180`, `270`) are also available for controlled comparisons. Trials: [sideways p17](results/shared-html/docling-vietocr-osd-longhau-p17-table-auto/) and [upright p15](results/shared-html/docling-vietocr-osd-longhau-p15-table-auto/). This is an experimental benchmark option, not enabled in the production ingestion pipeline.

To test orientation-aware layout inference, add `--layout-rotation auto`. OSD runs on a larger page render; only the layout model receives the rotated image, and its detected boxes are mapped back to source coordinates. On p17 the rotated layout trial had lower F1 than baseline (15.38% vs 22.22%); after correcting OCR block order, CER was 8.92% vs 9.08%. See [the p17 trial](results/shared-html/docling-vietocr-osd-longhau-p17-layout-rotation-auto-hires/).

## Active data

- [`data/local-review-state.json`](data/local-review-state.json) stores edits from the local review server.
- `data/raw/` holds original page images for review and inference.
- `data/{ocr,layout,table,end-to-end}/reference.jsonl` are generated from pages marked `owner_reviewed` in the HTML workflow.
- OCR, layout, and table scores use all records in their reviewed track references. End-to-end scores use pages with reviewed OCR, layout, and one or more reviewed table grids; multiple tables on a page are supported.
- Layout region labels are `title`, `title_table` (a printed table title or caption), `text`, `table`, `figure` (including standalone long bars, decorative separators, and scan-edge/binder strips outside table grids), and `seal` (a stamped seal or partial stamp impression). The region list and reading order follow numeric region IDs (`R01`, `R02`, `R03`, …). Dragging moves region data (label and bbox) between fixed ID slots and updates table-grid links to follow the moved regions. Changing layout data or dragging a region marks a reviewed page as needing review again.
- Each table draft has an editable `table_name`; the table and end-to-end references carry it as descriptive metadata. Existing drafts default to an empty name until the source caption is checked. The table evaluator scores bbox and cell grids, so this metadata does not change benchmark scores.

Start the review UI with `../../../.venv/bin/uvicorn review_server:app --app-dir data --host 127.0.0.1 --port 8767`, then open `http://127.0.0.1:8767`.

To add pages from another source, use **Thêm PDF** in the review UI and enter page numbers or ranges such as `1,3-5`. The local server stores the PDF, renders selected pages into `data/raw/`, and adds blank `needs_owner_review` drafts; only pages explicitly checked as reviewed enter the benchmark references. Uploads are limited to 50 MiB and 100 selected pages per request. Uploads skip existing pages using the full source PDF SHA-256 plus page number, then the rendered page-image SHA-256. Renaming a PDF does not create duplicate review rows; a matching page opens its existing annotations. Exact image hashing also catches the same rendered page uploaded as a separate PDF; a rescan or different rendering can have a different hash. The upload status reports new and skipped pages.

For source-based AI drafts, select a page that still needs review and choose a Codex action. **Tạo nháp bằng Codex CLI** regenerates OCR, layout boxes, reading order, and table grids. **Codex CLI: chỉ transcript** regenerates only the full-page OCR text and keeps table grids unchanged. **Codex CLI: chỉ fill bảng** sends separate crops of the existing table regions, returns only cell grids (preserving any existing table names), asks for literal visual transcription, and marks unreadable cells `[unclear]`; it keeps OCR text and layout unchanged. This action also works on reviewed pages after confirmation: a successful refill marks the page as needing review; failed requests preserve the existing review and grids. Edit grid dimensions with the add/remove row and column controls. **Codex CLI: chỉ chỉnh bbox** refines existing region boxes and keeps OCR, labels, reading order, and table grids. Each action uses the installed `codex` CLI with its existing ChatGPT login and configured model, in an ephemeral read-only session. Generated drafts remain `needs_owner_review`; compare them with the original image and edit before approving. The page image is sent for processing only when a Codex action is clicked.

Legacy datasets and large runtime artifacts remain in the local archive and are excluded from the active Docling benchmark.
