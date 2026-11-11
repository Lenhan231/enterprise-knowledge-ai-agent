# docling benchmark: shared-html-owner-reviewed

**Run:** `docling-html-baseline` · **Predictions:** 10 pages · **Inference success:** 10
**Runtime:** 171.67s on CPU · peak process RSS 1733.0 MiB

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 10 pages | CER 16.56%; WER (PyVi) 39.47%; whitespace error 30.83% |
| Layout | 10 pages | micro P/R/F1 9.42% / 30.59% / 14.40% |
| Table | 12 tables on 9 pages | detection P/R/F1 100.00% / 91.67% / 95.65%; cell CER 35.81%; cell WER (whitespace) 48.85%; exact grids 0.00% |

## End-to-end cohort

9 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 16.96%; WER (PyVi) 37.69% |
| Layout | micro P/R/F1 8.00% / 28.17% / 12.46% |
| Table | detection P/R 100.00% / 91.67%; cell CER 35.81%; cell WER (whitespace) 48.85% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- Reading order is not scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
