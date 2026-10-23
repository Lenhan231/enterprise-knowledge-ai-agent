# Shared review data

[`review.html`](review.html) is the single intake and owner-review UI for OCR, layout, table, and end-to-end references.

## Files

- `raw/`: original page images. Keep these unchanged.
- `local-review-state.json`: local review state saved by `review_server.py`.
- `agents/`: task-specific Codex agents for page draft, transcript, table, and bbox. Each agent owns its instructions, schema, and output checks; `agents/codex_cli.py` is the shared CLI adapter.
- `{ocr,layout,table,end-to-end}/reference.jsonl`: generated references for the active benchmark. Saves to the server rebuild these from pages marked `owner_reviewed`.
- `auto_review_tracks.py`: routes reviewed annotations independently to each track. End-to-end rows include every reviewed table on a page; a page with no reviewed table grid is not in the E2E cohort.

Previous pilot references and the manual promoter are stored under `../archive/legacy/data/`.

## Review locally

Run from `artifacts/evaluation/document-pipelines/`:

```bash
../../../.venv/bin/uvicorn review_server:app --app-dir data --host 127.0.0.1 --port 8767
```

Open `http://127.0.0.1:8767`. The server writes changes to `local-review-state.json` and refreshes all four references. Pending pages are excluded. Structural checks only ensure that a record can be formed; owner approval comes from the review status you set after comparing with the source image.

If opening `review.html` as a file, edits stay in that browser. Use **Tải backup JSON** and **Nạp backup** to transfer them to the server-backed review.

## Current counts

The local store has 15 pages: 10 owner-reviewed and five pending. The active references currently contain 10 OCR pages, 10 layout pages, 12 tables, and nine end-to-end pages. E2E uses pages with reviewed OCR, layout, and table labels; it supports multiple tables on one page. The page without a reviewed table grid is omitted from E2E pending an explicit table annotation.
