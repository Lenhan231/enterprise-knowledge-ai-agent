# docling benchmark: shared-html-owner-reviewed

**Run:** `docling-kaggle-owner-reviewed-51-20261024` · **Predictions:** 51 pages · **Inference success:** 51
**Runtime:** 520.772s on Tesla T4 · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 51 pages | CER 16.57%; WER (PyVi) 42.57%; whitespace error 30.16% |
| Layout | 51 pages | micro P/R/F1 16.43% / 42.06% / 23.63% |
| Table | 60 tables on 38 pages | detection P/R/F1 89.58% / 71.67% / 79.63%; cell CER 63.61%; cell WER (whitespace) 77.84%; exact grids 0.00% |

## End-to-end cohort

38 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 17.28%; WER (PyVi) 43.56% |
| Layout | micro P/R/F1 16.91% / 38.92% / 23.57% |
| Table | detection P/R 89.58% / 71.67%; cell CER 63.61%; cell WER (whitespace) 77.84% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
