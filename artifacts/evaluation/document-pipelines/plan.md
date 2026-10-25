# Active benchmark plan

## Source of truth

All active labels come from the shared local review UI in [`data/review.html`](data/review.html). The review server regenerates the OCR, layout, table, and end-to-end references from pages marked `owner_reviewed`. Pending or structurally incomplete records are not exported.

## Cohorts

- OCR: page-level full-page Vietnamese transcripts.
- Layout: normalized boxes for scored classes `title`, `title_table`, `text`, `table`, and `figure`.
- Tables: reviewed cell grids and their corresponding layout boxes; multiple tables per page are supported.
- End-to-end: pages with reviewed OCR, layout, and one or more reviewed tables. It scores all tables on each selected page.

Current counts: 51 OCR pages, 51 layout pages, 60 tables, and 38 end-to-end pages. The E2E reference omits pages that have no reviewed table grid.

## Running

Inference and scoring are separate:

- Run parser: [`tools/runners/run_shared_benchmark.py`](tools/runners/run_shared_benchmark.py)
- Evaluate normalized output: [`tools/evaluators/evaluate_shared_benchmark.py`](tools/evaluators/evaluate_shared_benchmark.py)
- Results: `results/shared-html/<run-id>/`

Metrics remain separate by layer: OCR reports CER, PyVi WER, and whitespace-token error; layout reports per-class and micro P/R/F1 at IoU 0.5; tables report detection, cell CER/WER, exact-cell, shape, and exact-grid metrics. E2E reports the same layer metrics over its complete-reference cohort. Reviewed reading-order labels are present, but the evaluator does not yet report a separate reading-order metric.

Older datasets and their associated runners, evaluators, and reports are preserved under [`archive/README.md`](archive/README.md). They do not participate in the active HTML-driven benchmark.
