# Shared review data

[`review.html`](review.html) is the single intake and owner-review UI for OCR, layout, table, and end-to-end references.

## Files

- `raw/`: original page images. Keep these unchanged.
- `local-review-state.json`: local review state saved by [`../review_server.py`](../review_server.py).
- `agents/`: task-specific Codex agents for page draft, transcript, table, and bbox. Each agent owns its instructions, schema, and output checks; `agents/codex_cli.py` is the shared CLI adapter.
- `{ocr,layout,table,end-to-end}/reference.jsonl`: generated references for the active benchmark. Saves to the server rebuild these from pages marked `owner_reviewed`.
- `auto_review_tracks.py`: routes reviewed annotations independently to each track. End-to-end rows include every reviewed table on a page; a page with no reviewed table grid is not in the E2E cohort.

Previous pilot references and the manual promoter are stored under `../archive/legacy/data/`.

## Review locally

Run from `artifacts/evaluation/document-pipelines/`:

```bash
../../../.venv/bin/uvicorn review_server:app --host 127.0.0.1 --port 8767
```

Open `http://127.0.0.1:8767`. The server writes changes to `local-review-state.json` and refreshes all four references. Pending pages are excluded. Structural checks only ensure that a record can be formed; owner approval comes from the review status you set after comparing with the source image.

If opening `review.html` as a file, edits stay in that browser. Use **Tải backup JSON** and **Nạp backup** to transfer them to the server-backed review.

## Counts and duplicate protection

Read live page counts from the review UI or `local-review-state.json`; approved and pending pages are counted separately. Track references contain approved pages only.

PDF intake checks the full source PDF SHA-256 plus page number, then the rendered image SHA-256. Re-uploading a renamed PDF or an identical rendered page opens the existing annotation and reports it as skipped. Matching is exact: a rescan or different rendering may have another hash. The save API rejects stale duplicate page aliases, and the browser resolves cached aliases to the canonical server page on reload.

Historical duplicate review rows are preserved in `../archive/duplicate-review-pages-20261023T092149Z.json`; the active store retains the newest explicit owner-reviewed copy for each source page.

## Additional scanned sources

These pages are original scans downloaded from the companies' websites. Each uploaded page stores `source_url`, original PDF/page/image SHA-256, scan notes, and the native-text character count. They enter review as `needs_owner_review`.

| Source | Selected PDF pages (1-based) | Scan characteristics |
| --- | --- | --- |
| [Kinh Bắc: audited consolidated financial statements 2008](https://kinhbaccity.vn/pic/FileLibrary/bao-cao-tai-chinh-2008.pdf) | 4, 10–14, 24, 35 | Image-only pages; faint small type, slight skew, scan-edge artifacts, tables and stamps/signatures. |
| [Vinaconex: annual report 2008, financial-statement section](https://vinaconex.com.vn/storage/bao-cao-thuong-nien/bao-cao-thuong-nien-vinaconex-2008.pdf) | 39–44, 46 | Scanned body with a small native report header; small type, thin table rules, stamps/signatures, sideways statement on PDF page 46. |
