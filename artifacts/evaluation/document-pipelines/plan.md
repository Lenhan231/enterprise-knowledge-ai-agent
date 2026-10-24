# Active benchmark plan

## Source of truth

All active labels come from the shared local review UI in [`data/review.html`](data/review.html). The review server regenerates the OCR, layout, table, and end-to-end references from pages marked `owner_reviewed`. Pending or structurally incomplete records are not exported.

## Cohorts

- OCR: page-level full-page Vietnamese transcripts.
- Layout: normalized boxes for `title`, `text`, `table`, and `figure`.
- Tables: reviewed cell grids and their corresponding layout boxes; multiple tables per page are supported.
- End-to-end: pages with reviewed OCR, layout, and one or more reviewed tables. It scores all tables on each selected page.

The 2026-10-23 checkpoint recorded 30 owner-reviewed pages: 30 OCR pages, 30 layout pages, 38 table grids, and 23 end-to-end pages. The current Kaggle snapshot contains 51 unique owner-reviewed page identities and runs Docling only.

At that checkpoint, the latest addition was 13 pages from PHR's audited 2009 financial statements (source PDF pages 4, 5, and 7–17). All 13 contributed OCR and layout references; 12 reviewed table grids covered eight pages, so eight pages entered the E2E cohort. The other five pages had no reviewed table grid. The 30-page checkpoint comprised Bao Ho Lao Dong (9), Long Hau (8), and PHR (13).

## Running

Inference and scoring are separate:

- Run parser: [`tools/runners/run_shared_benchmark.py`](tools/runners/run_shared_benchmark.py)
- Evaluate normalized output: [`tools/evaluators/evaluate_shared_benchmark.py`](tools/evaluators/evaluate_shared_benchmark.py)
- Results: `results/shared-html/<run-id>/`

Metrics remain separate by layer: OCR reports CER, PyVi WER, and whitespace-token error; layout reports per-class and micro P/R/F1 at IoU 0.5; tables report detection, cell CER/WER, exact-cell, shape, and exact-grid metrics. E2E reports the same layer metrics over its complete-reference cohort. Reading order is not scored until reviewed order labels are present.

Legacy datasets and large runtime artifacts remain in the local archive and do not participate in the active Docling benchmark.
