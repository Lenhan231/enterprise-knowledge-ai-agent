# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-heron-threshold05-kaggle-owner-reviewed-51-20261025` · **Predictions:** 51 pages · **Inference success:** 51
**Runtime:** 1109.097s on Tesla T4 · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 51 pages | CER 11.65%; WER (PyVi) 22.85%; whitespace error 17.84% |
| Layout | 51 pages | micro P/R/F1 32.89% / 40.12% / 36.14% |
| Table | 60 tables on 38 pages | detection P/R/F1 89.58% / 71.67% / 79.63%; cell CER 61.12%; cell WER (whitespace) 69.50%; exact grids 1.67% |

## End-to-end cohort

38 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 13.18%; WER (PyVi) 24.13% |
| Layout | micro P/R/F1 32.77% / 36.48% / 34.52% |
| Table | detection P/R 89.58% / 71.67%; cell CER 61.12%; cell WER (whitespace) 69.50% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
