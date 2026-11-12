# docling benchmark: shared-html-owner-reviewed

**Run:** `docling-kaggle-shared-html-13p-20261022` · **Predictions:** 13 pages · **Inference success:** 13
**Runtime:** 123.331s on Tesla T4 (Kaggle) · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 13 pages | CER 14.54%; WER (PyVi) 35.67%; whitespace error 27.16% |
| Layout | 13 pages | micro P/R/F1 9.76% / 29.51% / 14.66% |
| Table | 17 tables on 11 pages | detection P/R/F1 92.31% / 70.59% / 80.00%; cell CER 40.47%; cell WER (whitespace) 50.67%; exact grids 0.00% |

## End-to-end cohort

11 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 16.04%; WER (PyVi) 36.98% |
| Layout | micro P/R/F1 6.83% / 23.66% / 10.60% |
| Table | detection P/R 92.31% / 70.59%; cell CER 40.47%; cell WER (whitespace) 50.67% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
