# Active benchmark plan

## Source of truth

All active labels come from the shared local review UI in [`data/review.html`](data/review.html). The review server regenerates the OCR, layout, table, and end-to-end references from pages marked `owner_reviewed`. Pending or structurally incomplete records are not exported.

## Cohorts

- OCR: page-level full-page Vietnamese transcripts.
- Layout: normalized boxes for `title`, `text`, `table`, and `figure`.
- Tables: reviewed cell grids and their corresponding layout boxes; multiple tables per page are supported.
- End-to-end: pages with reviewed OCR, layout, and one or more reviewed tables. It scores all tables on each selected page.

The current Kaggle snapshot contains 50 owner-reviewed page identities and runs Docling only. Track references continue to be regenerated from the HTML review state.

## Running

Inference and scoring are separate:

- Run parser: [`tools/runners/run_shared_benchmark.py`](tools/runners/run_shared_benchmark.py)
- Evaluate normalized output: [`tools/evaluators/evaluate_shared_benchmark.py`](tools/evaluators/evaluate_shared_benchmark.py)
- Results: `results/shared-html/<run-id>/`

Metrics remain separate by layer: OCR reports CER, PyVi WER, and whitespace-token error; layout reports per-class and micro P/R/F1 at IoU 0.5; tables report detection, cell CER/WER, exact-cell, shape, and exact-grid metrics. E2E reports the same layer metrics over its complete-reference cohort. Reading order is not scored until reviewed order labels are present.

Legacy datasets and historical pipeline comparisons are excluded from the active Docling benchmark. They do not participate in the HTML-driven run.
